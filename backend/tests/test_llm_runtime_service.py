from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.llm_runtime_service import LLMRuntimeService


def test_secret_round_trip_and_masking() -> None:
    encrypted, masked = LLMRuntimeService.encrypt_secret("super-secret-token")

    assert encrypted is not None
    assert masked is not None
    assert masked.startswith("supe")
    assert LLMRuntimeService.decrypt_secret(encrypted) == "super-secret-token"


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

    assert "LLM" in str(exc_info.value)
