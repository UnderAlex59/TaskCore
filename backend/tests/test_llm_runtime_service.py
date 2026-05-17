from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.chat_agents.llm import ChatAgentLLMProfile
from app.core.config import get_settings
from app.services.llm_runtime_service import LLMRuntimeService


def test_secret_round_trip_and_masking() -> None:
    encrypted, masked = LLMRuntimeService.encrypt_secret("super-secret-token")

    assert encrypted is not None
    assert masked is not None
    assert masked.startswith("supe")
    assert LLMRuntimeService.decrypt_secret(encrypted) == "super-secret-token"


def test_decrypt_secret_invalid_token_raises_readable_error() -> None:
    foreign_token = Fernet(Fernet.generate_key()).encrypt(b"foreign-secret").decode("utf-8")

    with pytest.raises(ValueError) as exc_info:
        LLMRuntimeService.decrypt_secret(foreign_token)

    assert "расшифровать" in str(exc_info.value)


@pytest.mark.asyncio
async def test_gigachat_token_exchange_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    LLMRuntimeService._gigachat_token_cache.clear()

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"access_token": "gigachat-access-token"}

    async def fake_post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)

    first = await LLMRuntimeService._get_gigachat_access_token("provider-1", "encoded-auth-key")
    second = await LLMRuntimeService._get_gigachat_access_token("provider-1", "encoded-auth-key")

    assert first == "gigachat-access-token"
    assert second == "gigachat-access-token"
    assert calls == 1


def test_gigachat_ssl_verify_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIGACHAT_VERIFY_SSL", "false")
    monkeypatch.delenv("GIGACHAT_CA_BUNDLE_FILE", raising=False)
    get_settings.cache_clear()

    try:
        assert LLMRuntimeService._get_gigachat_ssl_verify() is False
    finally:
        get_settings.cache_clear()


def test_gigachat_ssl_verify_loads_custom_ca_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    bundle_path = tmp_path / "russian-root.crt"
    bundle_path.write_text("placeholder", encoding="utf-8")
    loaded_paths: list[str] = []

    class FakeSSLContext:
        def load_verify_locations(self, cafile: str) -> None:
            loaded_paths.append(cafile)

    monkeypatch.setenv("GIGACHAT_VERIFY_SSL", "true")
    monkeypatch.setenv("GIGACHAT_CA_BUNDLE_FILE", str(bundle_path))
    monkeypatch.setattr("ssl.create_default_context", lambda: FakeSSLContext())
    get_settings.cache_clear()

    try:
        context = LLMRuntimeService._get_gigachat_ssl_verify()
    finally:
        get_settings.cache_clear()

    assert isinstance(context, FakeSSLContext)
    assert loaded_paths == [str(bundle_path)]


def test_gigachat_ssl_verify_loads_custom_ca_bundle_from_pem_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded_cadata: list[str] = []

    class FakeSSLContext:
        def load_verify_locations(
            self,
            cafile: str | None = None,
            cadata: str | None = None,
        ) -> None:
            if cadata is not None:
                loaded_cadata.append(cadata)

    monkeypatch.setenv("GIGACHAT_VERIFY_SSL", "true")
    monkeypatch.delenv("GIGACHAT_CA_BUNDLE_FILE", raising=False)
    monkeypatch.setenv(
        "GIGACHAT_CA_BUNDLE_PEM",
        "-----BEGIN CERTIFICATE-----\\nMIIB\\n-----END CERTIFICATE-----",
    )
    monkeypatch.setattr("ssl.create_default_context", lambda: FakeSSLContext())
    get_settings.cache_clear()

    try:
        context = LLMRuntimeService._get_gigachat_ssl_verify()
    finally:
        get_settings.cache_clear()

    assert isinstance(context, FakeSSLContext)
    assert loaded_cadata == ["-----BEGIN CERTIFICATE-----\\nMIIB\\n-----END CERTIFICATE-----"]


@pytest.mark.asyncio
async def test_build_profile_creates_custom_clients_for_gigachat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_sync_kwargs: list[dict[str, object]] = []
    captured_async_kwargs: list[dict[str, object]] = []

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured_sync_kwargs.append(kwargs)

        def close(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            captured_async_kwargs.append(kwargs)

        async def aclose(self) -> None:
            return None

    async def fake_get_token(*args, **kwargs):  # type: ignore[no-untyped-def]
        return "gigachat-access-token"

    monkeypatch.setattr(LLMRuntimeService, "decrypt_secret", lambda value: "encoded-auth-key")
    monkeypatch.setattr(LLMRuntimeService, "_get_gigachat_ssl_verify", lambda: False)
    monkeypatch.setattr(LLMRuntimeService, "_get_gigachat_access_token", fake_get_token)
    monkeypatch.setattr("httpx.Client", FakeClient)
    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    profile = await LLMRuntimeService._build_profile(
        SimpleNamespace(
            id="provider-1",
            provider_kind="gigachat",
            encrypted_secret="encrypted",
            model="GigaChat-Max",
            temperature=0.2,
            base_url="https://gigachat.devices.sberbank.ru/api/v1",
        )
    )

    assert profile.api_key == "gigachat-access-token"
    assert profile.http_client is not None
    assert profile.http_async_client is not None
    assert captured_sync_kwargs[0]["verify"] is False
    assert captured_async_kwargs[0]["verify"] is False


@pytest.mark.asyncio
async def test_resolve_provider_requires_admin_configured_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_bootstrap() -> None:
        return None

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            if getattr(model, "__name__", "") == "LLMRuntimeSettings":
                return SimpleNamespace(default_provider_config_id=None)
            return None

    monkeypatch.setattr(LLMRuntimeService, "ensure_bootstrap", fake_ensure_bootstrap)

    with pytest.raises(RuntimeError) as exc_info:
        await LLMRuntimeService.resolve_provider(FakeDB(), agent_key=None)  # type: ignore[arg-type]

    assert str(exc_info.value) == (
        "Не настроен LLM-провайдер. Добавьте профиль и выберите профиль "
        "по умолчанию в админ-панели."
    )


@pytest.mark.asyncio
async def test_invoke_chat_returns_error_result_when_provider_resolution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve_provider(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise ValueError("provider secret is invalid")

    monkeypatch.setattr(LLMRuntimeService, "resolve_provider", fake_resolve_provider)

    result = await LLMRuntimeService.invoke_chat(  # type: ignore[arg-type]
        db=object(),
        agent_key="task-validation",
        actor_user_id=None,
        task_id=None,
        project_id=None,
        system_prompt="system",
        user_prompt="user",
    )

    assert result.ok is False
    assert result.error_message == "provider secret is invalid"


def test_normalize_messages_for_gemma_moves_system_prompt_into_user_text() -> None:
    profile = ChatAgentLLMProfile(provider="openai", model="models/gemma-3-12b-it")
    normalized = LLMRuntimeService._normalize_messages_for_model(
        profile,
        [
            SystemMessage(content="Извлеки текст без пояснений."),
            HumanMessage(content="Что на картинке?"),
        ],
    )

    assert len(normalized) == 1
    assert isinstance(normalized[0], HumanMessage)
    assert normalized[0].content == "Извлеки текст без пояснений.\n\nЧто на картинке?"


def test_normalize_messages_for_gemma_moves_system_prompt_into_multimodal_user_message() -> None:
    profile = ChatAgentLLMProfile(provider="openai", model="google/gemma-3-12b-it")
    normalized = LLMRuntimeService._normalize_messages_for_model(
        profile,
        [
            SystemMessage(content="Извлеки текст строго по порядку."),
            HumanMessage(
                content=[
                    {"type": "text", "text": "Распознай скан."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
                ]
            ),
        ],
    )

    assert len(normalized) == 1
    assert isinstance(normalized[0], HumanMessage)
    assert normalized[0].content == [
        {"type": "text", "text": "Извлеки текст строго по порядку.\n\nРаспознай скан."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
    ]


def test_normalize_messages_for_non_gemma_keeps_system_message() -> None:
    profile = ChatAgentLLMProfile(provider="openai", model="gpt-4o")
    original = [
        SystemMessage(content="System prompt"),
        HumanMessage(content="User prompt"),
    ]

    normalized = LLMRuntimeService._normalize_messages_for_model(profile, original)

    assert normalized == original


def test_build_vision_messages_can_inline_system_prompt_and_put_image_first() -> None:
    messages = LLMRuntimeService._build_vision_messages(
        data_url="data:image/png;base64,AAA",
        prompt="Извлеки текст",
        system_prompt="Не добавляй пояснения.",
        vision_system_prompt_mode="inline_user",
        vision_message_order="image_first",
        vision_detail="high",
    )

    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == [
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,AAA",
                "detail": "high",
            },
        },
        {
            "type": "text",
            "text": "Не добавляй пояснения.\n\nИзвлеки текст",
        },
    ]


@pytest.mark.asyncio
async def test_execute_gigachat_vision_uses_files_attachments_and_deletes_file() -> None:
    requests: list[dict[str, object]] = []
    logs: list[object] = []

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(prompt_log_mode="full")

        def add(self, item: object) -> None:
            logs.append(item)

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeAsyncClient:
        async def post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
            requests.append({"url": url, **kwargs})
            if url.endswith("/files"):
                return FakeResponse({"id": "real-gigachat-file-id"})
            if url.endswith("/chat/completions"):
                return FakeResponse(
                    {
                        "choices": [{"message": {"content": "Счет №42"}}],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 3,
                            "total_tokens": 13,
                        },
                    }
                )
            return FakeResponse({"deleted": True})

        async def aclose(self) -> None:
            return None

    result = await LLMRuntimeService._execute_gigachat_vision(
        FakeDB(),  # type: ignore[arg-type]
        config=SimpleNamespace(
            id="provider-1",
            provider_kind="gigachat",
            base_url="https://gigachat.devices.sberbank.ru/api/v1",
            model="GigaChat-2-Max",
            input_cost_per_1k_tokens=None,
            output_cost_per_1k_tokens=None,
        ),
        profile=ChatAgentLLMProfile(
            provider="gigachat",
            model="GigaChat-2-Max",
            api_key="access-token",
            base_url="https://gigachat.devices.sberbank.ru/api/v1",
            http_async_client=FakeAsyncClient(),
        ),
        actor_user_id="user-1",
        task_id="task-1",
        project_id="project-1",
        agent_key="rag-vision",
        image_bytes=b"image bytes",
        content_type="image/png",
        prompt="Извлеки текст",
        system_prompt="Ты OCR агент.",
    )

    assert result.ok is True
    assert result.text == "Счет №42"
    assert [request["url"] for request in requests] == [
        "https://gigachat.devices.sberbank.ru/api/v1/files",
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        "https://gigachat.devices.sberbank.ru/api/v1/files/real-gigachat-file-id/delete",
    ]
    upload_request = requests[0]
    assert upload_request["data"] == {"purpose": "general"}
    assert upload_request["files"] == {
        "file": ("vision-upload.png", b"image bytes", "image/png")
    }
    chat_payload = requests[1]["json"]
    assert chat_payload == {
        "model": "GigaChat-2-Max",
        "messages": [
            {
                "role": "user",
                "content": "Ты OCR агент.\n\nИзвлеки текст",
                "attachments": ["real-gigachat-file-id"],
            }
        ],
        "temperature": 0.1,
        "stream": False,
        "update_interval": 0,
    }
    assert logs[0].request_messages == [
        {
            "role": "user",
            "content": "Ты OCR агент.\n\nИзвлеки текст",
            "attachments": ["[gigachat file id omitted]"],
        }
    ]
    assert "real-gigachat-file-id" not in str(logs[0].request_messages)


@pytest.mark.asyncio
async def test_execute_gigachat_vision_deletes_file_when_completion_fails() -> None:
    requests: list[str] = []

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(prompt_log_mode="metadata_only")

        def add(self, item: object) -> None:
            return None

    class FakeResponse:
        def __init__(self, payload: dict[str, object], should_fail: bool = False) -> None:
            self.payload = payload
            self.should_fail = should_fail

        def raise_for_status(self) -> None:
            if self.should_fail:
                raise RuntimeError("completion failed")

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeAsyncClient:
        async def post(self, url: str, **kwargs):  # type: ignore[no-untyped-def]
            requests.append(url)
            if url.endswith("/files"):
                return FakeResponse({"id": "file-to-clean"})
            if url.endswith("/chat/completions"):
                return FakeResponse({}, should_fail=True)
            return FakeResponse({"deleted": True})

        async def aclose(self) -> None:
            return None

    result = await LLMRuntimeService._execute_gigachat_vision(
        FakeDB(),  # type: ignore[arg-type]
        config=SimpleNamespace(
            id="provider-1",
            provider_kind="gigachat",
            base_url="https://gigachat.devices.sberbank.ru/api/v1",
            model="GigaChat-2-Max",
            input_cost_per_1k_tokens=None,
            output_cost_per_1k_tokens=None,
        ),
        profile=ChatAgentLLMProfile(
            provider="gigachat",
            model="GigaChat-2-Max",
            api_key="access-token",
            http_async_client=FakeAsyncClient(),
        ),
        actor_user_id=None,
        task_id=None,
        project_id=None,
        agent_key="rag-vision",
        image_bytes=b"image bytes",
        content_type="image/png",
        prompt="Извлеки текст",
        system_prompt="Ты OCR агент.",
    )

    assert result.ok is False
    assert result.error_message == "completion failed"
    assert requests[-1] == "https://gigachat.devices.sberbank.ru/api/v1/files/file-to-clean/delete"
