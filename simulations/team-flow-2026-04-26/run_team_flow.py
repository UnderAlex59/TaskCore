from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError as exc:  # pragma: no cover - runtime guard for local execution
    raise SystemExit("Для запуска сценария нужен пакет httpx.") from exc


REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = REPO_ROOT / "simulations" / "team-flow-2026-04-26"
TASKS_DIR = SIM_DIR / "tasks"
HISTORY_DIR = SIM_DIR / "history"
ATTACHMENTS_DIR = SIM_DIR / "attachments"
SUMMARY_PATH = SIM_DIR / "summary.json"
README_PATH = SIM_DIR / "README.md"

API_BASE_URL = "http://127.0.0.1:8080/api"
PASSWORD = "Password1"
PROJECT_NAME = "Командная эмуляция магистерской 2026-04-26"
PROJECT_DESCRIPTION = (
    "Связный backlog корпоративной системы заявок и согласований для проверки "
    "валидации, RAG-контекста, чатов задач, change proposals и post-approval revalidation."
)
REQUIRED_AGENT_PROVIDER_KEYS = {
    "change-tracker",
    "chat-routing",
    "qa",
    "qa-answer",
    "qa-planner",
    "qa-verifier",
    "task-validation",
}
DEFAULT_TIMEOUT = 600.0
WAIT_TIMEOUT_SECONDS = 420.0
WAIT_INTERVAL_SECONDS = 2.0
ADMIN_USER = {
    "email": "admin@example.com",
    "password": PASSWORD,
    "full_name": "Администратор системы",
}
TEAM_USERS = [
    {
        "email": "analyst@example.com",
        "password": PASSWORD,
        "full_name": "Анна Аналитик",
        "role": "ANALYST",
    },
    {
        "email": "developer@example.com",
        "password": PASSWORD,
        "full_name": "Дмитрий Разработчик",
        "role": "DEVELOPER",
    },
    {
        "email": "tester@example.com",
        "password": PASSWORD,
        "full_name": "Татьяна Тестировщик",
        "role": "TESTER",
    },
]
TAG_NAMES = [
    "workflow",
    "roles",
    "forms",
    "attachments",
    "validation",
    "notifications",
    "import",
    "reports",
    "integration",
    "audit",
    "dashboard",
    "security",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str) -> str:
    normalized = []
    for char in value.lower():
        if char.isascii() and (char.isalnum() or char == "-"):
            normalized.append(char)
        elif char in {" ", "_", "/"}:
            normalized.append("-")
    slug = "".join(normalized).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "task"


def ensure_dirs() -> None:
    for path in (SIM_DIR, TASKS_DIR, HISTORY_DIR, ATTACHMENTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


STRICT_SPEC_MARKER = "## Машиночитаемая спецификация для validation"


def build_improvement_appendix(title: str, tags: list[str]) -> str:
    tag_set = set(tags)
    lines = [
        STRICT_SPEC_MARKER,
        "",
        f"### Scope задачи «{title}»",
        "",
        "- Проверка этой задачи выполняется по API, данным БД и журналам событий; UI и визуальные экраны не входят в критерии приёмки.",
        "- Каждое правило ниже трактуется как обязательное и должно быть проверяемо без ручных визуальных шагов.",
        "",
    ]

    if "workflow" in tag_set:
        lines.extend(
            [
                "### Workflow и роли",
                "",
                "- Состояния процесса фиксированы: `draft`, `submitted`, `manager_review`, `finance_review`, `needs_rework`, `approved`, `cancelled`.",
                "- Допустимые переходы: `draft -> submitted`, `submitted -> manager_review`, `manager_review -> finance_review`, `manager_review -> needs_rework`, `manager_review -> cancelled`, `finance_review -> approved`, `finance_review -> needs_rework`, `finance_review -> cancelled`, `needs_rework -> submitted`.",
                "- Инициатор создаёт заявку и повторно отправляет её после доработки; руководитель подразделения переводит `manager_review -> finance_review|needs_rework|cancelled`; финансовый контролёр переводит `finance_review -> approved|needs_rework|cancelled`; администратор может перевести любую незавершённую заявку в `cancelled` с обязательным комментарием.",
                "- Повторная отправка после `needs_rework` сохраняет историю предыдущих циклов и не удаляет старые комментарии согласующих.",
                "- Максимально допустимое число циклов `needs_rework -> submitted` равно 5; шестая попытка возвращает 409 с кодом `rework_limit_exceeded`, а заявка остаётся в статусе `needs_rework` до ручного решения аналитика.",
                "",
            ]
        )

    if "roles" in tag_set:
        lines.extend(
            [
                "### Role matrix",
                "",
                "- Пользователь не может согласовывать собственную заявку.",
                "- Временный заместитель может действовать только в пределах периода делегирования и только для подразделения, указанного в настройке делегирования.",
                "- Период делегирования валидируется по `delegation_starts_at <= now_utc <= delegation_ends_at`; если срок истёк в момент попытки действия, API возвращает 409 с кодом `delegation_expired`.",
                "- Для каждого запрещённого перехода API возвращает 403 или 409 с машинным кодом причины и текстом для аудита.",
                "",
            ]
        )

    if "forms" in tag_set:
        lines.extend(
            [
                "### Поля и валидация формы",
                "",
                "- Обязательные поля заявки: `request_number`, `request_type`, `department_code`, `budget_code`, `currency`, `requested_amount`, `need_by_date`, `business_reason`.",
                "- Для капитальных затрат дополнительно обязательны `project_code`, `cost_center`, `investment_limit_ref`.",
                "- Если изменяются `request_type`, `department_code` или `requested_amount`, система пересчитывает обязательные поля и маркирует их как `requires_reconfirmation=true`.",
                "",
            ]
        )

    if "attachments" in tag_set:
        lines.extend(
            [
                "### Вложения",
                "",
                "- Допустимые MIME-типы: `application/pdf`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/plain`.",
                "- Размер одного файла не более 10 МБ, число файлов на задачу не более 20.",
                "- Для каждого вложения сохраняются `attachment_id`, `original_filename`, `storage_path`, `content_type`, `uploaded_by`, `uploaded_at`.",
                "- Ошибка одного файла не удаляет ранее сохранённые вложения и возвращается отдельным ответом для проблемного файла.",
                "",
            ]
        )

    if "notifications" in tag_set:
        lines.extend(
            [
                "### Нотификации и SLA",
                "",
                "- События уведомлений: `submitted`, `needs_rework`, `approved`, `cancelled`, `escalated`.",
                "- SLA шага руководителя подразделения: 8 рабочих часов; SLA шага финансового контролёра: 16 рабочих часов.",
                "- При эскалации сохраняются `escalation_from_user_id`, `escalation_to_user_id`, `original_deadline_at`, `escalated_at`.",
                "",
            ]
        )

    if "import" in tag_set:
        lines.extend(
            [
                "### Импорт",
                "",
                "- CSV содержит колонки `full_name`, `department_code`, `external_employee_id`, `work_email`, `is_active`.",
                "- Для каждой строки сохраняется результат `created|updated|skipped|manual_review` и причина решения.",
                "- При конфликте по существующему `external_employee_id` API возвращает старые и новые значения полей без автоматического перезаписывания.",
                "",
            ]
        )

    if "integration" in tag_set:
        lines.extend(
            [
                "### Интеграционные события",
                "",
                "- Внешний payload содержит `request_id`, `external_employee_id`, `department_code`, `status`, `amount`, `changed_at`, `correlation_id`, `attempt_number`.",
                "- Идемпотентность определяется парой `request_id + correlation_id`.",
                "- При ошибке внешней системы внутренний переход статуса не откатывается; отдельно сохраняются `delivery_status`, `delivery_error_code`, `delivery_error_message`, `next_retry_at`.",
                "",
            ]
        )

    if "audit" in tag_set or "reports" in tag_set:
        lines.extend(
            [
                "### Аудит и отчёты",
                "",
                "- Для аудита сохраняются `event_id`, `entity_type`, `entity_id`, `actor_user_id`, `from_status`, `to_status`, `comment`, `occurred_at`, `batch_id`.",
                "- В отчётах используется время в UTC ISO 8601.",
                "- Любая массовая операция должна содержать `batch_id`, `reason`, `affected_count` и связь с затронутыми заявками.",
                "",
            ]
        )

    if "dashboard" in tag_set:
        lines.extend(
            [
                "### Метрики дашборда",
                "",
                "- Виджеты SLA рассчитываются по полям `submitted_at`, `current_step_started_at`, `approved_at`, `escalated_at`.",
                "- Просрочка считается отдельно для обычных заявок, заявок с изменённым маршрутом и заявок с интеграционной ошибкой.",
                "",
            ]
        )

    if "security" in tag_set:
        lines.extend(
            [
                "### Хранение и маскирование",
                "",
                "- В архиве сохраняются технические идентификаторы, вложения и аудит, но в управленческом отчёте маскируются e-mail и персональные идентификаторы, кроме последних 4 символов.",
                "- Срок хранения архивных записей: 5 лет, если по заявке нет открытого расследования; при открытом расследовании автоудаление запрещено.",
                "",
            ]
        )

    lines.extend(
        [
            "### Машинные критерии приёмки",
            "",
            "1. Для каждого шага описаны входные данные, разрешённый актор и ожидаемый результат в API или БД.",
            "2. Граничные случаи и ошибки перечислены явно, а не подразумеваются.",
            "3. Все временные метки задаются в ISO 8601 UTC.",
            "4. Проверка выполняется без UI: через API-ответы, payload событий, аудит и содержимое задач.",
        ]
    )
    return "\n".join(lines).strip()


def compose_strict_content(base_content: str, title: str, tags: list[str]) -> str:
    body = base_content.strip()
    marker_index = body.find(STRICT_SPEC_MARKER)
    if marker_index != -1:
        body = body[:marker_index].rstrip()
    return f"{body}\n\n{build_improvement_appendix(title, tags)}".strip()


def build_runtime_content(base_content: str, title: str, tags: list[str]) -> str:
    body = base_content.strip()
    if "Критерии приёмки:" in body:
        body = body.split("Критерии приёмки:", maxsplit=1)[0].rstrip()
    replacements = {
        "карточке заявки": "ответе GET /requests/{id}",
        "карточка заявки": "ответ GET /requests/{id}",
        "карточке": "ответе GET /requests/{id}",
        "карточка": "ответ GET /requests/{id}",
        "видит": "получает в API",
        "видеть": "получать в API",
        "в журнале видно": "запись аудита содержит",
        "показывает": "возвращает",
    }
    for source, target in replacements.items():
        body = body.replace(source, target)
    return compose_strict_content(body, title, tags)


@dataclass(slots=True)
class AttachmentPlan:
    filename: str
    content: str
    content_type: str = "text/plain; charset=utf-8"


@dataclass(slots=True)
class ChatPlan:
    actor: str
    content: str
    expect_agent_response: bool = False
    expect_backlog_save: bool = False
    expect_proposal: bool = False
    label: str = ""


@dataclass(slots=True)
class ProposalPlan:
    actor: str
    content: str
    review_status: str
    label: str


@dataclass(slots=True)
class TaskScenario:
    index: int
    title: str
    tags: list[str]
    initial_content: str
    final_content: str
    initial_verdict: str = "approved"
    pre_approval_attachment: AttachmentPlan | None = None
    team_discussion: list[ChatPlan] = field(default_factory=list)
    proposal: ProposalPlan | None = None
    post_approval_edit: str | None = None

    @property
    def slug(self) -> str:
        return slugify(self.title)


@dataclass
class TaskRunRecord:
    scenario: TaskScenario
    task_file: Path
    history_file: Path
    task_id: str | None = None
    created_at: str | None = None
    final_status: str | None = None
    final_validation_questions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    chat_messages: list[dict[str, Any]] = field(default_factory=list)
    validation_runs: list[dict[str, Any]] = field(default_factory=list)
    proposal_events: list[dict[str, Any]] = field(default_factory=list)
    attachment_events: list[dict[str, Any]] = field(default_factory=list)
    backlog_saves: list[dict[str, Any]] = field(default_factory=list)
    backlog_reuse: list[str] = field(default_factory=list)

    def add_action(self, text: str) -> None:
        self.actions.append(f"- {now_iso()}: {text}")
        self.write_history()

    def add_chat_message(self, payload: dict[str, Any]) -> None:
        self.chat_messages.append(payload)
        self.write_history()

    def add_validation_run(self, payload: dict[str, Any]) -> None:
        self.validation_runs.append(payload)
        self.write_history()

    def add_proposal_event(self, payload: dict[str, Any]) -> None:
        self.proposal_events.append(payload)
        self.write_history()

    def add_attachment_event(self, payload: dict[str, Any]) -> None:
        self.attachment_events.append(payload)
        self.write_history()

    def add_backlog_save(self, payload: dict[str, Any]) -> None:
        self.backlog_saves.append(payload)
        self.write_history()

    def set_final_status(self, status: str, questions: list[str]) -> None:
        self.final_status = status
        self.final_validation_questions = list(questions)
        self.write_history()

    def set_backlog_reuse(self, questions: list[str]) -> None:
        self.backlog_reuse = list(questions)
        self.write_history()

    def write_history(self) -> None:
        source_section = self.task_file.read_text(encoding="utf-8") if self.task_file.exists() else ""
        chat_lines = [
            (
                f"- {item['created_at']}: {item['author']} -> `{item['message_type']}`"
                f" {item['content']}"
            )
            for item in self.chat_messages
        ] or ["- Пока без сообщений."]
        validation_lines = []
        for item in self.validation_runs:
            issues = item.get("issues") or []
            questions = item.get("questions") or []
            issues_text = "; ".join(issues) if issues else "нет"
            questions_text = "; ".join(questions) if questions else "нет"
            validation_lines.append(
                f"- {item['at']}: `{item['phase']}` -> `{item['verdict']}`; issues: {issues_text}; questions: {questions_text}"
            )
        if not validation_lines:
            validation_lines.append("- Проверка ещё не запускалась.")
        proposal_lines = [
            f"- {item['at']}: {item['summary']}"
            for item in self.proposal_events
        ] or ["- Proposal-событий пока нет."]
        attachment_lines = [
            f"- {item['at']}: {item['filename']} ({item['phase']})"
            for item in self.attachment_events
        ] or ["- Вложений нет."]
        backlog_lines = [
            f"- {item['at']}: сохранён вопрос «{item['question']}»"
            for item in self.backlog_saves
        ] or ["- QA backlog для этой задачи не пополнялся."]
        reuse_lines = [f"- {item}" for item in self.backlog_reuse] or ["- Повторно использованных backlog-вопросов не зафиксировано."]
        conclusion = (
            "Сценарий показал связку LangGraph -> chat -> backlog вопросов -> следующая validation."
            if self.backlog_reuse or self.backlog_saves
            else "Сценарий показал базовый lifecycle задачи и взаимодействие команды."
        )
        content = textwrap.dedent(
            f"""
            # {self.scenario.title}

            - Task ID: {self.task_id or 'ещё не создана'}
            - Теги: {', '.join(self.scenario.tags)}
            - Дата создания: {self.created_at or 'ещё не создана'}

            ## Исходное описание

            {source_section.strip() or 'Файл описания ещё не сформирован.'}

            ## Хронология

            {chr(10).join(self.actions) if self.actions else '- Сценарий ещё не запускался.'}

            ## Ключевые сообщения чата

            {chr(10).join(chat_lines)}

            ## Результаты валидации

            {chr(10).join(validation_lines)}

            ## Сохранённые backlog-вопросы

            {chr(10).join(backlog_lines)}

            ## Повторное использование backlog-вопросов

            {chr(10).join(reuse_lines)}

            ## Change Proposals

            {chr(10).join(proposal_lines)}

            ## Вложения

            {chr(10).join(attachment_lines)}

            ## Финальный статус

            - {self.final_status or 'ещё не завершена'}

            ## Вывод для магистерской

            - {conclusion}
            """
        ).strip()
        write_text(self.history_file, content + "\n")


class ApiUser:
    def __init__(self, email: str, password: str, token: str):
        self.email = email
        self.password = password
        self.token = token

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


class ApiClient:
    def __init__(self, base_url: str):
        self.client = httpx.Client(base_url=base_url, timeout=DEFAULT_TIMEOUT)

    def close(self) -> None:
        self.client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        user: ApiUser | None = None,
        expected_status: int | set[int] = 200,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if user is not None:
            headers.update(user.headers)
        response = self.client.request(method, path, headers=headers, **kwargs)
        if response.status_code == 401 and user is not None and path != "/auth/login":
            login_response = self.client.post(
                "/auth/login",
                json={"email": user.email, "password": user.password},
                timeout=DEFAULT_TIMEOUT,
            )
            if login_response.status_code == 200:
                user.token = login_response.json()["access_token"]
                headers = dict(kwargs.pop("headers", {}))
                headers.update(user.headers)
                response = self.client.request(method, path, headers=headers, **kwargs)
        expected = {expected_status} if isinstance(expected_status, int) else set(expected_status)
        if response.status_code not in expected:
            detail = response.text
            raise RuntimeError(
                f"{method} {path} -> {response.status_code}, ожидался {sorted(expected)}; body={detail}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


class SimulationRunner:
    def __init__(self) -> None:
        ensure_dirs()
        self.api = ApiClient(API_BASE_URL)
        self.summary: dict[str, Any] = {
            "started_at": now_iso(),
            "api_base_url": API_BASE_URL,
            "accounts": [],
            "tags": [],
            "llm": {},
            "project": {},
            "tasks": [],
            "issues": [],
        }
        self.users_by_alias: dict[str, dict[str, Any]] = {}
        self.api_users: dict[str, ApiUser] = {}
        self.project_id: str | None = None
        self.backlog_questions: list[dict[str, Any]] = []
        self.scenarios = build_scenarios()

    def log(self, message: str) -> None:
        line = f"[{now_iso()}] {message}"
        print(line, flush=True)

    def close(self) -> None:
        self.api.close()

    def run(self) -> None:
        try:
            self.preflight()
            self.capture_and_reset_state()
            self.bootstrap()
            self.run_simulation()
            self.finish()
        finally:
            self.close()

    def preflight(self) -> None:
        self.log("Проверяю статус docker compose сервисов.")
        lines = self.run_command(["docker", "compose", "ps", "--format", "json"]).splitlines()
        services = [json.loads(line) for line in lines if line.strip()]
        service_map = {item["Service"]: item for item in services}
        for required_service in ("backend", "postgres", "qdrant", "ollama"):
            service = service_map.get(required_service)
            if service is None or service.get("State") != "running":
                raise RuntimeError(f"Сервис {required_service} не запущен.")
            if required_service != "qdrant" and service.get("Health") not in {"healthy", ""}:
                raise RuntimeError(f"Сервис {required_service} не healthy: {service.get('Status')}")
        ready = self.api.request("GET", "/readyz", expected_status=200)
        if ready.get("status") != "ok":
            raise RuntimeError(f"Backend /readyz вернул неожиданный payload: {ready!r}")
        self.summary["preflight"] = {
            item["Service"]: {"state": item["State"], "health": item.get("Health")}
            for item in services
        }

    def capture_and_reset_state(self) -> None:
        self.log("Считываю текущую LLM-конфигурацию и очищаю бизнес-данные.")
        provider_rows = self.psql_json(
            """
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select
                    id,
                    name,
                    provider_kind,
                    model,
                    enabled,
                    encrypted_secret is not null as has_secret
                from llm_provider_configs
                order by created_at
            ) t;
            """
        )
        override_rows = self.psql_json(
            """
            select coalesce(json_agg(row_to_json(t)), '[]'::json)
            from (
                select agent_key, provider_config_id, enabled
                from llm_agent_overrides
                order by agent_key
            ) t;
            """
        )
        runtime_settings = self.psql_json(
            """
            select row_to_json(t)
            from (
                select id, default_provider_config_id, prompt_log_mode
                from llm_runtime_settings
                order by id
                limit 1
            ) t;
            """
        )
        if runtime_settings is None:
            raise RuntimeError("В llm_runtime_settings нет строки по умолчанию.")
        self.summary["llm"]["providers_before_reset"] = provider_rows
        self.summary["llm"]["overrides_before_reset"] = override_rows
        self.summary["llm"]["runtime_before_reset"] = runtime_settings
        self.stop_backend()

        reset_sql = textwrap.dedent(
            f"""
            begin;
            update llm_provider_configs set created_by = null, updated_by = null;
            update llm_agent_overrides set updated_by = null;
            update llm_runtime_settings set updated_by = null;

            delete from audit_events;
            delete from llm_request_logs;
            delete from llm_agent_prompt_versions;
            delete from llm_agent_prompt_configs;
            delete from change_proposals;
            delete from messages;
            delete from task_attachments;
            delete from validation_questions;
            delete from tasks;
            delete from custom_rules;
            delete from project_members;
            delete from projects;
            delete from refresh_tokens;
            delete from task_tags;
            delete from users;
            delete from llm_runtime_settings;

            insert into llm_runtime_settings (id, default_provider_config_id, prompt_log_mode, updated_by)
            values (
                1,
                '{runtime_settings["default_provider_config_id"]}',
                '{runtime_settings["prompt_log_mode"]}',
                null
            );
            commit;
            """
        ).strip()
        self.run_psql(reset_sql)
        self.clear_qdrant_collections()
        self.clear_uploads()
        self.start_backend_and_wait()
        counts = self.psql_json(
            """
            select row_to_json(t)
            from (
                select
                    (select count(*) from users) as users_count,
                    (select count(*) from projects) as projects_count,
                    (select count(*) from tasks) as tasks_count,
                    (select count(*) from messages) as messages_count,
                    (select count(*) from change_proposals) as proposals_count,
                    (select count(*) from validation_questions) as validation_questions_count,
                    (select count(*) from audit_events) as audit_events_count,
                    (select count(*) from task_tags) as task_tags_count
            ) t;
            """
        )
        self.summary["reset_counts_after"] = counts
        zero_keys = {
            "users_count",
            "projects_count",
            "tasks_count",
            "messages_count",
            "proposals_count",
            "validation_questions_count",
            "audit_events_count",
            "task_tags_count",
        }
        for key in zero_keys:
            if int(counts[key]) != 0:
                raise RuntimeError(f"Очистка не завершилась: {key}={counts[key]}")

    def bootstrap(self) -> None:
        self.log("Создаю админа, команду, проект и теги.")
        self.register_user(ADMIN_USER)
        admin_api_user = self.login(ADMIN_USER["email"], ADMIN_USER["password"])
        self.api_users["admin"] = admin_api_user
        self.users_by_alias["admin"] = self.api.request("GET", "/auth/me", user=admin_api_user)

        for alias, payload in zip(("analyst", "developer", "tester"), TEAM_USERS, strict=True):
            self.register_user(payload)
            self.api_users[alias] = self.login(payload["email"], payload["password"])
            self.users_by_alias[alias] = self.api.request("GET", "/auth/me", user=self.api_users[alias])

        for alias, payload in zip(("analyst", "developer", "tester"), TEAM_USERS, strict=True):
            updated = self.api.request(
                "PATCH",
                f"/users/{self.users_by_alias[alias]['id']}",
                user=admin_api_user,
                json={"role": payload["role"]},
                expected_status=200,
            )
            self.users_by_alias[alias] = updated
            self.api_users[alias] = self.login(payload["email"], payload["password"])

        self.summary["accounts"] = [
            {
                "alias": alias,
                "email": self.users_by_alias[alias]["email"],
                "full_name": self.users_by_alias[alias]["full_name"],
                "role": self.users_by_alias[alias]["role"],
                "password": PASSWORD,
            }
            for alias in ("admin", "analyst", "developer", "tester")
        ]

        project = self.api.request(
            "POST",
            "/projects",
            user=self.api_users["analyst"],
            json={"name": PROJECT_NAME, "description": PROJECT_DESCRIPTION},
            expected_status=201,
        )
        self.project_id = project["id"]
        self.summary["project"] = project
        self.api.request(
            "POST",
            f"/projects/{self.project_id}/members",
            user=self.api_users["analyst"],
            json={"user_id": self.users_by_alias["developer"]["id"], "role": "DEVELOPER"},
            expected_status=201,
        )
        self.api.request(
            "POST",
            f"/projects/{self.project_id}/members",
            user=self.api_users["analyst"],
            json={"user_id": self.users_by_alias["tester"]["id"], "role": "TESTER"},
            expected_status=201,
        )

        tag_rows = []
        for tag_name in TAG_NAMES:
            row = self.api.request(
                "POST",
                "/admin/task-tags",
                user=admin_api_user,
                json={"name": tag_name},
                expected_status=201,
            )
            tag_rows.append(row)
        self.summary["tags"] = [item["name"] for item in tag_rows]

        self.ensure_live_task_validation_override(admin_api_user)
        self.verify_providers(admin_api_user)

    def verify_providers(self, admin_user: ApiUser) -> None:
        self.log("Проверяю доступность LLM-провайдеров после bootstrap.")
        providers = self.api.request("GET", "/admin/llm/providers", user=admin_user)
        overrides = self.api.request("GET", "/admin/llm/overrides", user=admin_user)
        runtime = self.api.request("GET", "/admin/llm/runtime/settings", user=admin_user)
        default_provider = next((item for item in providers if item.get("is_default")), None)
        default_provider_id = default_provider["id"] if default_provider is not None else None

        override_provider_ids = {
            item["provider_config_id"]
            for item in overrides
            if item["enabled"] and item["agent_key"] in REQUIRED_AGENT_PROVIDER_KEYS
        }
        required_provider_ids = set(override_provider_ids)
        optional_provider_ids = ({default_provider_id} if default_provider_id else set()) - required_provider_ids

        checks = []
        for provider in providers:
            provider_id = provider["id"]
            result: dict[str, Any] | None
            if provider_id in required_provider_ids:
                result = self.api.request(
                    "POST",
                    f"/admin/llm/providers/{provider_id}/test",
                    user=admin_user,
                    expected_status=200,
                    timeout=180.0,
                )
            else:
                result = None
            checks.append(
                {
                    "id": provider_id,
                    "name": provider["name"],
                    "provider_kind": provider["provider_kind"],
                    "model": provider["model"],
                    "required_for_simulation": provider_id in required_provider_ids,
                    "is_runtime_default": provider.get("is_default", False),
                    "result": result,
                }
            )
            if provider_id in required_provider_ids and (result is None or not result.get("ok")):
                raise RuntimeError(
                    "Для сценария недоступен обязательный LLM-провайдер "
                    f"{provider['name']}: {result}"
                )
        self.summary["llm"]["provider_checks_after_bootstrap"] = checks
        self.summary["llm"]["optional_provider_ids"] = list(optional_provider_ids)

    def ensure_live_task_validation_override(self, admin_user: ApiUser) -> None:
        overrides = self.api.request("GET", "/admin/llm/overrides", user=admin_user)
        preferred_override = next(
            (
                item
                for item in overrides
                if item["enabled"] and item["agent_key"] in {"qa", "change-tracker"}
            ),
            None,
        )
        if preferred_override is None:
            raise RuntimeError("Не найден live LLM override для восстановления task-validation.")
        self.api.request(
            "PUT",
            "/admin/llm/overrides/task-validation",
            user=admin_user,
            json={
                "provider_config_id": preferred_override["provider_config_id"],
                "enabled": True,
            },
            expected_status=200,
        )
        self.summary["llm"]["task_validation_mode"] = {
            "mode": "live",
            "provider_config_id": preferred_override["provider_config_id"],
            "provider_name": preferred_override["provider_name"],
            "provider_kind": preferred_override["provider_kind"],
            "model": preferred_override["model"],
        }

    def run_simulation(self) -> None:
        if self.project_id is None:
            raise RuntimeError("project_id не инициализирован")
        self.log("Запускаю симуляцию 10 последовательных задач с активными чатами.")
        for scenario in self.scenarios:
            try:
                self.run_task_scenario(scenario)
            except Exception as exc:
                self.summary.setdefault("issues", []).append(
                    {
                        "at": now_iso(),
                        "type": type(exc).__name__,
                        "scenario_index": scenario.index,
                        "scenario_title": scenario.title,
                        "message": str(exc),
                    }
                )
                self.log(f"Сценарий [{scenario.index:02d}] завершился с ошибкой, продолжаю со следующей задачей: {exc}")

    def run_task_scenario(self, scenario: TaskScenario) -> None:
        task_filename = TASKS_DIR / f"{scenario.index:02d}-{scenario.slug}.md"
        history_filename = HISTORY_DIR / f"{scenario.index:02d}-{scenario.slug}.md"
        write_text(task_filename, self.render_task_source_file(scenario))
        record = TaskRunRecord(scenario=scenario, task_file=task_filename, history_file=history_filename)
        record.write_history()

        self.log(f"[{scenario.index:02d}] Создаю задачу «{scenario.title}».")
        initial_task_content = scenario.initial_content
        created_with_final_content = False
        if scenario.initial_verdict == "approved":
            initial_task_content = build_runtime_content(
                scenario.final_content,
                scenario.title,
                scenario.tags,
            )
            created_with_final_content = True
        task = self.api.request(
            "POST",
            f"/projects/{self.project_id}/tasks",
            user=self.api_users["analyst"],
            json={
                "title": scenario.title,
                "content": initial_task_content,
                "tags": scenario.tags,
            },
            expected_status=201,
        )
        record.task_id = task["id"]
        record.created_at = task["created_at"]
        record.add_action("Создана задача в статусе `draft`.")
        if scenario.initial_verdict == "approved":
            record.add_action("Для первого живого прогона в задачу сразу добавлено стандартизированное приложение с критериями.")

        if scenario.pre_approval_attachment is not None:
            attachment = self.upload_attachment(
                record.task_id,
                scenario.pre_approval_attachment,
                user=self.api_users["analyst"],
                phase="pre-approval",
            )
            record.add_attachment_event(
                {
                    "at": now_iso(),
                    "filename": attachment["filename"],
                    "phase": "pre-approval",
                }
            )
            record.add_action(f"Добавлено вложение `{attachment['filename']}` до первой проверки.")

        task, validation_result = self.validate_and_fetch(record.task_id, phase="initial")
        record.add_validation_run(self.render_validation_run("initial", validation_result))

        if scenario.initial_verdict == "needs_rework":
            if validation_result["verdict"] != "needs_rework":
                failproof_content = "Сделать быстро и удобно. Детали уточним позже."
                task = self.update_task_content(
                    record.task_id,
                    failproof_content,
                    note="Форсированно упрощён черновик, чтобы получить `needs_rework`.",
                )
                record.add_action("Черновик намеренно упростили, чтобы зафиксировать сценарий `needs_rework`.")
                task, validation_result = self.validate_and_fetch(record.task_id, phase="forced-needs-rework")
                record.add_validation_run(self.render_validation_run("forced-needs-rework", validation_result))
            if validation_result["verdict"] != "needs_rework":
                raise RuntimeError(f"Не удалось получить needs_rework для задачи {record.task_id}")
            task = self.update_task_content(
                record.task_id,
                build_runtime_content(scenario.final_content, scenario.title, scenario.tags),
                note="Аналитик доработал требование после замечаний QA.",
            )
            record.add_action("Аналитик доработал требование и подготовил повторную проверку.")
            task, validation_result = self.validate_until_approved(record, phase="after-rework")
        else:
            if validation_result["verdict"] != "approved":
                record.add_action("Автопроверка вернула `needs_rework`, задача будет усилена и перевалидирована.")
                task = self.update_task_content(
                    record.task_id,
                    build_runtime_content(scenario.final_content, scenario.title, scenario.tags),
                    note="Усиление постановки после неожиданного needs_rework.",
                )
                task, validation_result = self.validate_until_approved(record, phase="after-strengthening")
            elif scenario.initial_content != scenario.final_content and not created_with_final_content:
                task = self.update_task_content(
                    record.task_id,
                    scenario.final_content,
                    note="Финальная редакция описания сохранена после успешной первой проверки.",
                )
                record.add_action("После первой проверки сохранена финальная редакция описания.")
                task, validation_result = self.validate_until_approved(record, phase="final-content-check")

        reused_questions = self.detect_backlog_reuse(validation_result["questions"], record.task_id)
        record.set_backlog_reuse(reused_questions)

        task = self.approve_task(record.task_id)
        record.add_action("Задача approved, назначены разработчик и тестировщик, team chat открыт.")

        for chat_plan in scenario.team_discussion:
            agent_message = self.send_chat_message(record.task_id, chat_plan)
            user_name = self.users_by_alias[chat_plan.actor]["full_name"]
            record.add_chat_message(
                {
                    "created_at": now_iso(),
                    "author": user_name,
                    "message_type": "user",
                    "content": chat_plan.content,
                }
            )
            if agent_message is not None:
                record.add_chat_message(
                    {
                        "created_at": agent_message["created_at"],
                        "author": agent_message.get("agent_name") or "Agent",
                        "message_type": agent_message["message_type"],
                        "content": agent_message["content"],
                    }
                )
                source_ref = agent_message.get("source_ref") or {}
                backlog_question = source_ref.get("validation_backlog_question")
                if source_ref.get("validation_backlog_saved") and backlog_question:
                    payload = {
                        "at": now_iso(),
                        "question": backlog_question,
                        "task_id": record.task_id,
                    }
                    self.backlog_questions.append(payload)
                    record.add_backlog_save(payload)

        if scenario.proposal is not None:
            proposal = self.run_proposal_flow(record.task_id, scenario.proposal)
            record.add_proposal_event(
                {
                    "at": now_iso(),
                    "summary": (
                        f"{scenario.proposal.label}: proposal `{proposal['id']}` переведён в `{proposal['status']}`."
                    ),
                }
            )
            if proposal["status"] == "accepted":
                record.add_action("Принято change proposal, задача возвращена в `needs_rework`.")
                task, validation_result = self.validate_until_approved(record, phase="after-proposal-accept")
                task = self.approve_task(record.task_id)
                record.add_action("После принятого proposal задача повторно approved.")

        if scenario.post_approval_edit is not None:
            self.update_task_content(
                record.task_id,
                scenario.final_content + "\n\n" + scenario.post_approval_edit,
                note="Пост-approval правка для проверки commit flow.",
            )
            record.add_action("После approve аналитик внёс post-approval правку.")
            conflict = self.try_validate_expect_conflict(record.task_id)
            record.add_validation_run(
                {
                    "at": now_iso(),
                    "phase": "pre-commit-revalidate",
                    "verdict": "blocked",
                    "issues": [conflict],
                    "questions": [],
                }
            )
            self.commit_task(record.task_id)
            record.add_action("Изменения закоммичены, embeddings пересчитаны.")
            task, validation_result = self.validate_until_approved(record, phase="post-commit-revalidate")
            record.add_action("Повторная проверка после commit завершилась успешно.")

        task = self.get_task(record.task_id)
        record.set_final_status(task["status"], list((task.get("validation_result") or {}).get("questions", [])))
        self.summary["tasks"].append(
            {
                "index": scenario.index,
                "task_id": record.task_id,
                "title": scenario.title,
                "tags": scenario.tags,
                "history_file": str(record.history_file.relative_to(REPO_ROOT)).replace("\\", "/"),
                "task_file": str(record.task_file.relative_to(REPO_ROOT)).replace("\\", "/"),
                "final_status": task["status"],
                "messages_count": len(self.list_messages(record.task_id)),
                "qa_backlog_saved": [item["question"] for item in record.backlog_saves],
                "backlog_reuse": record.backlog_reuse,
                "proposals": record.proposal_events,
                "attachments": [item["filename"] for item in record.attachment_events],
            }
        )

    def render_task_source_file(self, scenario: TaskScenario) -> str:
        sections = [
            f"# {scenario.title}",
            "",
            f"- Теги: {', '.join(scenario.tags)}",
            "",
            "## Стартовая редакция",
            "",
            scenario.initial_content.strip(),
        ]
        if scenario.initial_content != scenario.final_content:
            sections.extend(
                [
                    "",
                    "## Редакция после доработки",
                    "",
                    scenario.final_content.strip(),
                ]
            )
        return "\n".join(sections).rstrip() + "\n"

    def render_validation_run(self, phase: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "at": now_iso(),
            "phase": phase,
            "verdict": payload["verdict"],
            "issues": [item["message"] for item in payload.get("issues", [])],
            "questions": list(payload.get("questions", [])),
        }

    def validate_until_approved(
        self,
        record: TaskRunRecord,
        *,
        phase: str,
        max_attempts: int = 3,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        task_id = record.task_id
        if task_id is None:
            raise RuntimeError("task_id не установлен")
        latest_task = self.get_task(task_id)
        for attempt in range(1, max_attempts + 1):
            latest_task, validation_result = self.validate_and_fetch(task_id, phase=f"{phase}-{attempt}")
            record.add_validation_run(self.render_validation_run(f"{phase}-{attempt}", validation_result))
            if validation_result["verdict"] == "approved":
                return latest_task, validation_result
            strengthened_content = compose_strict_content(
                latest_task["content"],
                latest_task["title"],
                list(latest_task.get("tags", [])),
            )
            latest_task = self.update_task_content(
                task_id,
                strengthened_content,
                note=f"Усиление требований после `{phase}` attempt {attempt}.",
            )
            record.add_action(
                f"После `{phase}` attempt {attempt} аналитик уточнил критерии и граничные сценарии."
            )
        raise RuntimeError(f"Не удалось довести задачу {task_id} до approved за {max_attempts} попытки.")

    def detect_backlog_reuse(self, questions: list[str], current_task_id: str | None) -> list[str]:
        if not questions:
            return []
        backlog_texts = {
            item["question"]
            for item in self.backlog_questions
            if item["task_id"] != current_task_id
        }
        return [question for question in questions if question in backlog_texts]

    def upload_attachment(
        self,
        task_id: str,
        attachment: AttachmentPlan,
        *,
        user: ApiUser,
        phase: str,
    ) -> dict[str, Any]:
        attachment_path = ATTACHMENTS_DIR / attachment.filename
        write_text(attachment_path, attachment.content.strip() + "\n")
        with attachment_path.open("rb") as file_obj:
            return self.api.request(
                "POST",
                f"/projects/{self.project_id}/tasks/{task_id}/attachments",
                user=user,
                files={"file": (attachment.filename, file_obj, attachment.content_type)},
                expected_status=201,
            )

    def send_chat_message(self, task_id: str, plan: ChatPlan) -> dict[str, Any] | None:
        baseline_messages = self.list_messages(task_id)
        baseline_count = len(baseline_messages)
        baseline_proposals = self.list_proposals(task_id)
        content = plan.content
        if plan.expect_agent_response and not content.lstrip().startswith(("/", "@")):
            content = f"/qa {content}"
        self.api.request(
            "POST",
            f"/tasks/{task_id}/messages",
            user=self.api_users[plan.actor],
            json={"content": content},
            expected_status=201,
        )
        if plan.expect_proposal:
            self.wait_for_proposal(task_id, baseline=len(baseline_proposals))
        if not plan.expect_agent_response:
            return None
        try:
            agent_message = self.wait_for_new_agent_message(task_id, baseline_messages=baseline_count)
        except RuntimeError as exc:
            self.summary.setdefault("issues", []).append(
                {
                    "at": now_iso(),
                    "type": "MissingAgentResponse",
                    "task_id": task_id,
                    "message": str(exc),
                }
            )
            return None
        if plan.expect_backlog_save and not (agent_message.get("source_ref") or {}).get("validation_backlog_saved"):
            fallback_prompts = [
                "Что делать, если этот граничный случай возникнет в середине маршрута согласования?",
                "Какой ожидается результат, если для этого случая нет данных в интеграции?",
            ]
            for extra_prompt in fallback_prompts:
                self.log(f"Повторяю вопрос для фиксации backlog на задаче {task_id}.")
                self.api.request(
                    "POST",
                    f"/tasks/{task_id}/messages",
                    user=self.api_users[plan.actor],
                    json={"content": f"/qa {extra_prompt}"},
                    expected_status=201,
                )
                try:
                    agent_message = self.wait_for_new_agent_message(task_id, baseline_messages=len(self.list_messages(task_id)) - 1)
                except RuntimeError:
                    break
                if (agent_message.get("source_ref") or {}).get("validation_backlog_saved"):
                    break
        return agent_message

    def wait_for_new_agent_message(self, task_id: str, *, baseline_messages: int) -> dict[str, Any]:
        deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            messages = self.list_messages(task_id)
            if len(messages) > baseline_messages:
                for item in reversed(messages[baseline_messages:]):
                    if item.get("author_id") is None:
                        return item
            time.sleep(WAIT_INTERVAL_SECONDS)
        raise RuntimeError(f"Не дождался agent response по задаче {task_id}")

    def wait_for_proposal(self, task_id: str, *, baseline: int) -> list[dict[str, Any]]:
        deadline = time.monotonic() + WAIT_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            proposals = self.list_proposals(task_id)
            if len(proposals) > baseline:
                return proposals
            time.sleep(WAIT_INTERVAL_SECONDS)
        raise RuntimeError(f"Не дождался change proposal по задаче {task_id}")

    def run_proposal_flow(self, task_id: str, plan: ProposalPlan) -> dict[str, Any]:
        baseline_proposals = self.list_proposals(task_id)
        baseline_messages = len(self.list_messages(task_id))
        content = plan.content
        if not content.lstrip().startswith(("/", "@")):
            content = f"/change {content}"
        self.api.request(
            "POST",
            f"/tasks/{task_id}/messages",
            user=self.api_users[plan.actor],
            json={"content": content},
            expected_status=201,
        )
        self.wait_for_new_agent_message(task_id, baseline_messages=baseline_messages)
        proposals = self.wait_for_proposal(task_id, baseline=len(baseline_proposals))
        proposal = proposals[0]
        updated = self.api.request(
            "PATCH",
            f"/tasks/{task_id}/proposals/{proposal['id']}",
            user=self.api_users["analyst"],
            json={"status": plan.review_status},
            expected_status=200,
        )
        return updated

    def validate_and_fetch(self, task_id: str, *, phase: str) -> tuple[dict[str, Any], dict[str, Any]]:
        self.log(f"Валидация `{phase}` для задачи {task_id}.")
        validation_result = self.api.request(
            "POST",
            f"/tasks/{task_id}/validate",
            user=self.api_users["analyst"],
            expected_status=200,
            timeout=None,
        )
        task = self.get_task(task_id)
        return task, validation_result

    def try_validate_expect_conflict(self, task_id: str) -> str:
        response = self.api.client.post(
            f"{API_BASE_URL}/tasks/{task_id}/validate",
            headers=self.api_users["analyst"].headers,
            timeout=DEFAULT_TIMEOUT,
        )
        if response.status_code != 409:
            raise RuntimeError(f"Ожидался 409 перед commit, но пришёл {response.status_code}: {response.text}")
        payload = response.json()
        return str(payload.get("detail", response.text))

    def update_task_content(self, task_id: str, content: str, *, note: str) -> dict[str, Any]:
        self.log(f"Обновляю задачу {task_id}: {note}")
        return self.api.request(
            "PATCH",
            f"/projects/{self.project_id}/tasks/{task_id}",
            user=self.api_users["analyst"],
            json={"content": content},
            expected_status=200,
        )

    def approve_task(self, task_id: str) -> dict[str, Any]:
        return self.api.request(
            "POST",
            f"/projects/{self.project_id}/tasks/{task_id}/approve",
            user=self.api_users["analyst"],
            json={
                "developer_id": self.users_by_alias["developer"]["id"],
                "tester_id": self.users_by_alias["tester"]["id"],
            },
            expected_status=200,
        )

    def commit_task(self, task_id: str) -> dict[str, Any]:
        return self.api.request(
            "POST",
            f"/projects/{self.project_id}/tasks/{task_id}/commit",
            user=self.api_users["analyst"],
            expected_status=200,
        )

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self.api.request(
            "GET",
            f"/projects/{self.project_id}/tasks/{task_id}",
            user=self.api_users["analyst"],
        )

    def list_messages(self, task_id: str) -> list[dict[str, Any]]:
        return self.api.request(
            "GET",
            f"/tasks/{task_id}/messages",
            user=self.api_users["analyst"],
        )

    def list_proposals(self, task_id: str) -> list[dict[str, Any]]:
        return self.api.request(
            "GET",
            f"/tasks/{task_id}/proposals",
            user=self.api_users["analyst"],
        )

    def register_user(self, payload: dict[str, str]) -> None:
        self.api.request(
            "POST",
            "/auth/register",
            json={
                "email": payload["email"],
                "password": payload["password"],
                "full_name": payload["full_name"],
            },
            expected_status=201,
        )

    def login(self, email: str, password: str) -> ApiUser:
        payload = self.api.request(
            "POST",
            "/auth/login",
            json={"email": email, "password": password},
            expected_status=200,
        )
        return ApiUser(email=email, password=password, token=payload["access_token"])

    def clear_qdrant_collections(self) -> None:
        self.log("Очищаю Qdrant-коллекции task_knowledge, project_questions, task_proposals.")
        python_code = textwrap.dedent(
            """
            from qdrant_client import QdrantClient

            client = QdrantClient(url="http://qdrant:6333")
            for name in ("task_knowledge", "project_questions", "task_proposals"):
                try:
                    if client.collection_exists(name):
                        client.delete_collection(name)
                        print(f"deleted:{name}")
                    else:
                        print(f"missing:{name}")
                except Exception as exc:
                    print(f"error:{name}:{exc}")
                    raise
            """
        ).strip()
        self.run_command(
            ["docker", "compose", "run", "--rm", "--no-deps", "backend", "python", "-c", python_code]
        )

    def clear_uploads(self) -> None:
        self.log("Очищаю volume uploads.")
        self.run_command(
            [
                "docker",
                "compose",
                "run",
                "--rm",
                "--no-deps",
                "backend",
                "sh",
                "-lc",
                "rm -rf /var/lib/task-platform/uploads/*",
            ]
        )

    def stop_backend(self) -> None:
        self.log("Останавливаю backend перед reset, чтобы фоновые задачи не писали в БД.")
        self.run_command(["docker", "compose", "stop", "backend"])

    def start_backend_and_wait(self) -> None:
        self.log("Поднимаю backend после reset и жду healthy.")
        self.run_command(["docker", "compose", "up", "-d", "backend"])
        deadline = time.monotonic() + 240.0
        while time.monotonic() < deadline:
            try:
                ready = self.api.request("GET", "/readyz", expected_status=200)
            except Exception:
                time.sleep(3.0)
                continue
            if ready.get("status") == "ok":
                return
            time.sleep(3.0)
        raise RuntimeError("Backend не стал ready после reset.")

    def run_command(self, args: list[str], *, input_text: str | None = None) -> str:
        result = subprocess.run(
            args,
            cwd=REPO_ROOT,
            input=input_text,
            text=True,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Команда завершилась с ошибкой ({result.returncode}): {' '.join(args)}\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )
        return result.stdout.strip()

    def run_psql(self, sql: str) -> None:
        self.run_command(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "app_user",
                "-d",
                "taskplatform",
            ],
            input_text=sql,
        )

    def psql_json(self, sql: str) -> Any:
        output = self.run_command(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "psql",
                "-t",
                "-A",
                "-U",
                "app_user",
                "-d",
                "taskplatform",
                "-c",
                sql.strip(),
            ]
        )
        text = output.strip()
        if not text:
            return None
        return json.loads(text)

    def finish(self) -> None:
        self.collect_remaining_tasks_summary()
        self.summary["finished_at"] = now_iso()
        write_text(SUMMARY_PATH, json.dumps(self.summary, ensure_ascii=False, indent=2) + "\n")
        write_text(README_PATH, render_readme(self.summary))
        self.log(f"Сценарий завершён. Итоги сохранены в {SUMMARY_PATH}.")

    def collect_remaining_tasks_summary(self) -> None:
        if self.project_id is None or "analyst" not in self.api_users:
            return
        try:
            tasks = self.api.request(
                "GET",
                f"/projects/{self.project_id}/tasks",
                user=self.api_users["analyst"],
                params={"size": 100},
            )
        except Exception as exc:
            self.summary.setdefault("issues", []).append(
                {
                    "at": now_iso(),
                    "type": "CollectSummaryFailed",
                    "message": str(exc),
                }
            )
            return
        existing_ids = {item["task_id"] for item in self.summary.get("tasks", []) if item.get("task_id")}
        for task in tasks:
            if task["id"] in existing_ids:
                continue
            try:
                messages = self.list_messages(task["id"])
            except Exception:
                messages = []
            self.summary["tasks"].append(
                {
                    "index": None,
                    "task_id": task["id"],
                    "title": task["title"],
                    "tags": task.get("tags", []),
                    "history_file": None,
                    "task_file": None,
                    "final_status": task["status"],
                    "messages_count": len(messages),
                    "qa_backlog_saved": [],
                    "backlog_reuse": list((task.get("validation_result") or {}).get("questions", [])),
                    "proposals": [],
                    "attachments": [item["filename"] for item in task.get("attachments", [])],
                }
            )


def build_scenarios() -> list[TaskScenario]:
    return [
        TaskScenario(
            index=1,
            title="Жизненный цикл заявки на закупку",
            tags=["workflow", "validation", "roles"],
            initial_content=textwrap.dedent(
                """
                Нужно описать базовый жизненный цикл заявки на закупку оборудования для офисов и филиалов. В системе должны быть состояния черновика, отправки на согласование, возврата на доработку, подтверждения и отмены. Инициатор всегда видит текущий этап и причину возврата, а руководитель подразделения и финансовый контролёр работают в одном маршруте без параллельных веток.

                Требование должно объяснить, как система фиксирует автора каждого перехода статуса, что показывается в карточке заявки после возврата на доработку и в каком виде аналитик ожидает минимально достаточное описание для разработки. Для магистерской важно, чтобы из этой задачи было видно, как валидатор и чат команды работают с одним и тем же контекстом.

                Критерии приёмки:
                1. После отправки на согласование система меняет статус и пишет, кто инициировал переход.
                2. После возврата на доработку в карточке есть причина возврата и предыдущий статус.
                3. Инициатор видит список согласующих и текущий активный шаг маршрута.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать базовый жизненный цикл заявки на закупку оборудования для офисов и филиалов. В системе есть состояния черновика, отправки на согласование, возврата на доработку, подтверждения и отмены. Инициатор всегда видит текущий этап, причину возврата и список участников маршрута, а руководитель подразделения и финансовый контролёр проходят последовательные шаги согласования.

                Требование должно зафиксировать состав метаданных каждого перехода: кто выполнил действие, когда это произошло, из какого статуса и в какой статус переведена заявка, а также какой комментарий сопровождал действие. После возврата на доработку инициатор должен видеть причину, прошлый статус и ожидаемый набор действий для повторной отправки, чтобы разработчик и тестировщик могли проверить полный цикл без UI.

                Критерии приёмки:
                1. После отправки на согласование система сохраняет автора, время и новый статус.
                2. После возврата на доработку карточка показывает причину, предыдущий статус и список незавершённых шагов.
                3. При отмене заявки в журнале видно, кто отменил процесс и на каком шаге это произошло.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(actor="developer", content="Предлагаю начать с маршрута без параллельных веток, чтобы не раздувать первую итерацию.", label="team-note"),
                ChatPlan(
                    actor="tester",
                    content="Что делать, если руководитель уже согласовал заявку, а после смены подразделения инициатора финансовый контролёр возвращает её на доработку?",
                    expect_agent_response=True,
                    expect_backlog_save=True,
                    label="qa-backlog-1",
                ),
            ],
        ),
        TaskScenario(
            index=2,
            title="Роли участников и ограничения переходов статусов",
            tags=["workflow", "roles", "validation"],
            initial_content=textwrap.dedent(
                """
                Нужно описать, кто и когда может переводить заявку между стадиями, чтобы было удобно и без лишних настроек. Участники проекта сами поймут, где нужна проверка, а где можно пропустить ручной шаг. Важно, чтобы роли были примерно понятны и не мешали работе команды.

                Хотелось бы, чтобы правила подходили и для филиалов, и для центрального офиса, но детали можно будет решить по ходу. Нужно как-то учитывать руководителя, финансовый контроль и администратора.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать матрицу ролей и допустимых переходов статусов для процесса согласования заявок. Инициатор создаёт и редактирует черновик, руководитель подразделения согласует только заявки своего подразделения, финансовый контролёр подтверждает бюджеты, а администратор может принудительно остановить процесс и перевести заявку в отменённое состояние с обязательным комментарием.

                Требование должно отдельно фиксировать запреты: пользователь не может согласовывать собственную заявку, тестировщик проверяет лишь уже утверждённую постановку, а временный заместитель действует только в пределах периода делегирования. Для проверки без UI нужен явный список переходов «кто -> из какого статуса -> в какой статус» и обязательных причин отказа, если переход запрещён.

                Критерии приёмки:
                1. У каждой роли есть список разрешённых переходов и список запретов.
                2. При попытке запрещённого перехода API возвращает понятную причину отказа.
                3. Для режима временного заместителя указаны условия начала и окончания полномочий.
                """
            ).strip(),
            initial_verdict="needs_rework",
            team_discussion=[
                ChatPlan(
                    actor="developer",
                    content="Если временный заместитель подписал заявку в последний день делегирования, а основной руководитель вернулся через час, кто может отменить это решение?",
                    expect_agent_response=True,
                    expect_backlog_save=True,
                    label="qa-backlog-2",
                ),
                ChatPlan(actor="tester", content="Зафиксирую отдельные тесты на запрет самосогласования и просроченное делегирование.", label="team-note"),
            ],
        ),
        TaskScenario(
            index=3,
            title="Динамическая форма заявки и обязательные поля",
            tags=["forms", "workflow", "validation"],
            initial_content=textwrap.dedent(
                """
                Нужно описать динамическую форму заявки на закупку, где набор полей зависит от типа закупки и суммы. Для стандартных заявок достаточно данных о подразделении, бюджете и желаемой дате поставки, а для капитальных затрат форма должна дополнительно требовать проектный код, центр затрат и ссылку на инвестиционный лимит.

                Требование должно учитывать повторное открытие заявки после возврата на доработку: ранее заполненные поля не теряются, но система должна повторно проверять обязательность тех полей, которые зависят от изменённого типа закупки или маршрута согласования. Для команды важно явно зафиксировать, какие поля становятся обязательными при определённых условиях, чтобы валидатор и тестировщик работали по одному набору правил.

                Критерии приёмки:
                1. Для каждого типа закупки описан набор обязательных полей.
                2. При смене типа закупки система пересчитывает обязательность полей без потери уже введённых данных.
                3. После возврата на доработку инициатор видит, какие поля требуют повторной проверки.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать динамическую форму заявки на закупку, где набор полей зависит от типа закупки, суммы и маршрута согласования. Для стандартных заявок обязательны подразделение, бюджет, ожидаемая дата поставки и обоснование, а для капитальных затрат дополнительно требуются проектный код, центр затрат и ссылка на инвестиционный лимит.

                При повторном открытии заявки после возврата на доработку ранее заполненные поля сохраняются, но система пересчитывает обязательность тех полей, которые зависят от изменившихся бизнес-условий. Если инициатор сменил подразделение, тип закупки или сумму, API должен повторно проверить обязательные поля до повторной отправки, чтобы исключить расхождение между новой формой и уже созданным маршрутом согласования.

                Критерии приёмки:
                1. Для каждого сочетания типа закупки и диапазона суммы описан обязательный набор полей.
                2. Изменение подразделения или типа закупки приводит к пересчёту обязательности без потери данных.
                3. После возврата на доработку в API явно видно, какие поля требуют повторного подтверждения.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(actor="developer", content="По форме предлагаю хранить причину повторной проверки прямо в метаданных поля.", label="team-note"),
                ChatPlan(
                    actor="tester",
                    content="Если подразделение меняется уже после возврата на доработку, какие поля должны заново стать обязательными и нужно ли пересобирать маршрут согласования?",
                    expect_agent_response=False,
                    label="qa-reuse-1",
                ),
            ],
        ),
        TaskScenario(
            index=4,
            title="Вложения к заявке и правила допустимых файлов",
            tags=["attachments", "validation", "workflow"],
            initial_content=textwrap.dedent(
                """
                Нужно описать, какие файлы инициатор может прикладывать к заявке на закупку и как API должен валидировать их до отправки на согласование. В базовом сценарии поддерживаются PDF с коммерческими предложениями, XLSX со сметой и текстовые пояснения, а для капитальных затрат дополнительно нужны схемы и акты обследования в виде отдельных вложений.

                Требование должно зафиксировать ограничения по размеру, типу MIME, количеству файлов и реакции на ошибку загрузки, чтобы команда могла проверить это без UI. Для связки с RAG важно, чтобы текстовые вложения индексировались вместе с основной постановкой, а имена файлов попадали в контекст последующей валидации.

                Критерии приёмки:
                1. Для каждого типа вложения указаны допустимые форматы и ограничения по размеру.
                2. При ошибке загрузки пользователь получает понятную причину отказа.
                3. Текстовые вложения индексируются в контексте задачи и учитываются при следующей проверке.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать правила работы с вложениями в заявке на закупку: допустимые форматы, ограничения по размеру, количество файлов и реакцию API на ошибки загрузки. В базовом сценарии поддерживаются PDF с коммерческими предложениями, XLSX со сметой и текстовые пояснения, а для капитальных затрат разрешены дополнительные схемы и акты обследования.

                Требование должно зафиксировать, что текстовые вложения индексируются в одном контексте с задачей, а их названия и краткие фрагменты доступны валидатору и QA-агенту. Если вложение не прошло проверку по типу, размеру или повреждённому содержимому, API возвращает причину отказа, не меняя уже сохранённые корректные файлы и не теряя историю предыдущих загрузок.

                Критерии приёмки:
                1. Для каждого разрешённого формата указаны MIME-типы, лимиты размера и правила именования.
                2. Ошибка одного вложения не удаляет остальные корректно сохранённые файлы.
                3. Текстовые вложения попадают в task_knowledge и влияют на следующую автоматическую проверку.
                """
            ).strip(),
            pre_approval_attachment=AttachmentPlan(
                filename="04-attachment-policy.txt",
                content="""
                Коммерческие предложения могут поступать как отдельные PDF, а пояснения аналитика допускаются в текстовом виде.
                Если инициатор прикладывает несколько файлов, система должна сохранить исходные имена и время загрузки каждого файла.
                """,
            ),
            team_discussion=[
                ChatPlan(actor="developer", content="По загрузке файлов я бы сразу сохранял и исходное имя, и безопасное storage имя.", label="team-note"),
                ChatPlan(
                    actor="tester",
                    content="Что делать со сканированным PDF без OCR, если по регламенту из него нельзя автоматически извлечь текст для последующей проверки?",
                    expect_agent_response=True,
                    expect_backlog_save=True,
                    label="qa-backlog-3",
                ),
            ],
        ),
        TaskScenario(
            index=5,
            title="Уведомления о смене статуса и эскалациях",
            tags=["notifications", "validation", "workflow"],
            initial_content=textwrap.dedent(
                """
                Нужно описать уведомления по ключевым изменениям статуса заявки: отправка на согласование, возврат на доработку, подтверждение и отмена. Инициатор должен получать уведомление при каждом изменении статуса, а согласующие — только когда действие требуется именно от них или когда вышел срок реакции и запускается эскалация.

                Требование должно зафиксировать, какие данные включаются в уведомление, как система помечает просрочку и какой набор событий должен быть доступен для последующих отчётов. Для магистерской важно показать, что вопросы из предыдущих обсуждений про возврат на доработку и смену подразделения могут всплывать в контексте новой проверки.

                Критерии приёмки:
                1. Для каждого события указан получатель, канал уведомления и состав полезной нагрузки.
                2. При просрочке согласования запускается эскалация руководителю следующего уровня.
                3. События уведомлений записываются так, чтобы их можно было использовать в отчётности и аудите.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать уведомления по ключевым изменениям статуса заявки: отправка на согласование, возврат на доработку, подтверждение, отмена и запуск эскалации. Инициатор получает уведомление при каждом изменении статуса, а согласующие — только когда действие требуется от них или когда вышел срок реакции.

                Требование должно зафиксировать состав полезной нагрузки уведомления: идентификатор заявки, текущий статус, причина возврата, активный согласующий, срок ответа и ссылка на историю действий. Если заявка ушла на доработку после смены подразделения или маршрута, уведомление должно показывать, какой шаг был перестроен и кто теперь отвечает за следующий переход, чтобы вопросы из командного чата можно было соотнести с новой validation.

                Критерии приёмки:
                1. Для каждого события указан получатель, канал и обязательный набор полей уведомления.
                2. При эскалации система записывает исходный срок реакции и новый адресат.
                3. Нотификации по возврату на доработку содержат причину возврата и обновлённый маршрут.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(
                    actor="developer",
                    content="Если эскалация уходит уже после возврата на доработку, нужно ли отправлять повторное уведомление новому согласующему или достаточно обновить историю заявки?",
                    expect_agent_response=False,
                    label="qa-reuse-2",
                ),
                ChatPlan(actor="tester", content="Запланирую тесты на совпадение payload нотификации с историей переходов.", label="team-note"),
            ],
        ),
        TaskScenario(
            index=6,
            title="Импорт заявителей из CSV",
            tags=["import", "attachments", "validation"],
            initial_content=textwrap.dedent(
                """
                Нужно как-то поддержать импорт заявителей из CSV, чтобы команда могла быстро загружать стартовый справочник. В файле будут колонки с ФИО, подразделением и чем-то вроде внешнего идентификатора, но детали формата можно уточнить потом. Важно, чтобы импорт был понятен и не ломал текущую работу.

                Желательно обработать ошибки по строкам и дубликаты, но правила можно определить позднее, когда появятся реальные файлы.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать импорт справочника заявителей из CSV для первичного наполнения системы. В файле обязательно присутствуют ФИО, код подразделения, внешний идентификатор сотрудника, признак активности и рабочий e-mail. Импорт должен поддерживать пакетную загрузку, построчную валидацию и отдельный отчёт по ошибкам без остановки всей операции.

                Требование должно отдельно описать обработку дубликатов и неполных записей. Если у строки нет внешнего идентификатора, система не создаёт пользователя автоматически и помещает запись в отчёт на ручную проверку. Если внешний идентификатор уже есть в базе, но отличаются подразделение или e-mail, импорт не молча перезаписывает данные, а маркирует конфликт и требует решения аналитика.

                Критерии приёмки:
                1. Для каждой строки фиксируется итог: создана, обновлена, пропущена или отправлена на ручную проверку.
                2. Ошибки по отдельным строкам не останавливают обработку корректных записей.
                3. Конфликты по существующим сотрудникам содержат старые и новые значения в отчёте импорта.
                """
            ).strip(),
            initial_verdict="needs_rework",
            pre_approval_attachment=AttachmentPlan(
                filename="06-import-example.txt",
                content="""
                Пример конфликта: строка с одинаковым external_id, но новым подразделением и другим e-mail.
                Для магистерского сценария важно, чтобы такой конфликт не затирал существующего сотрудника без явного решения аналитика.
                """,
            ),
            team_discussion=[
                ChatPlan(
                    actor="developer",
                    content="Что делать, если в CSV есть две строки без external_id, но с одинаковыми ФИО и разными подразделениями?",
                    expect_agent_response=True,
                    expect_backlog_save=True,
                    label="qa-backlog-4",
                ),
                ChatPlan(actor="tester", content="После импорта проверю, что конфликтная строка не меняет существующие данные тихо.", label="team-note"),
            ],
        ),
        TaskScenario(
            index=7,
            title="Синхронизация статусов с внешней CRM",
            tags=["integration", "reports", "audit"],
            initial_content=textwrap.dedent(
                """
                Нужно описать интеграцию со внешней CRM, чтобы после ключевых изменений статуса заявки система могла публиковать событие наружу. Интеграция должна передавать идентификатор заявки, внешний идентификатор инициатора, статус, сумму и дату последнего изменения, а также уметь безопасно переживать временную недоступность CRM.

                Требование должно объяснить, когда событие считается успешно доставленным, что делать при ошибке на стороне CRM и какие записи нужны для последующего аудита и отчётов. Для последовательного backlog важно, чтобы здесь появились вопросы о повторной отправке и о поведении при несовпадении данных между внутренним маршрутом и внешней системой.

                Критерии приёмки:
                1. Для каждого статуса, публикуемого в CRM, определён состав события.
                2. Ошибка внешней системы не приводит к потере внутреннего перехода статуса.
                3. Повторные отправки фиксируются в аудите и доступны для отчётности.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать интеграцию со внешней CRM, чтобы после ключевых изменений статуса заявки система публиковала событие наружу. В событие входят идентификатор заявки, внешний идентификатор инициатора, статус, сумма, код подразделения, дата последнего изменения и ссылка на внутренний журнал аудита.

                Требование должно зафиксировать модель повторной отправки: если CRM недоступна или вернула ошибку бизнес-валидации, внутренний переход статуса остаётся завершённым, а публикация получает отдельный статус доставки, причину ошибки и время следующей попытки. Для магистерской проверки важно, чтобы история повторных отправок была доступна в отчётности и чтобы вопросы команды о восстановлении после сбоя можно было потом увидеть в validation следующих задач.

                Критерии приёмки:
                1. Внутренний статус заявки не откатывается из-за ошибки внешней CRM.
                2. Каждая попытка доставки содержит код результата, время и краткое описание ошибки.
                3. Повторная отправка одной и той же заявки не должна терять ссылку на исходный переход статуса.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(actor="developer", content="Для повторной отправки я бы сохранял correlation id и номер попытки.", label="team-note"),
                ChatPlan(
                    actor="tester",
                    content="Что ожидается, если CRM была недоступна во время возврата заявки на доработку, а следующая попытка отправки уходит уже после изменения подразделения инициатора?",
                    expect_agent_response=True,
                    expect_backlog_save=True,
                    label="qa-backlog-5",
                ),
            ],
        ),
        TaskScenario(
            index=8,
            title="Аудит массовых изменений маршрута согласования",
            tags=["audit", "integration", "reports"],
            initial_content=textwrap.dedent(
                """
                Нужно описать аудит массовых операций, когда аналитик или администратор меняет маршрут согласования сразу у группы заявок после реорганизации или изменения лимитов. Система должна сохранять, кто выполнил массовое действие, сколько заявок затронуто и какие шаги маршрута были пересобраны.

                Требование должно быть пригодно для отчётности и последующего расследования: у каждой массовой операции должен быть единый batch id, а у каждой заявки — ссылка на эту операцию, старый маршрут и новый маршрут. Также важно зафиксировать, как это сочетается с уже отправленными во внешнюю CRM событиями и повторными доставками.

                Критерии приёмки:
                1. Для массовой операции сохраняются actor, batch id, причина запуска и количество затронутых заявок.
                2. По каждой заявке можно увидеть старый и новый маршрут согласования.
                3. В отчёте аудита видно, какие интеграционные события были связаны с массовым изменением.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать аудит массовых операций, когда аналитик или администратор меняет маршрут согласования у группы заявок после реорганизации, смены лимитов или обновления матрицы полномочий. Система сохраняет actor, batch id, причину запуска, количество затронутых заявок и время применения операции.

                Требование должно отдельно фиксировать следы по каждой заявке: старый маршрут, новый маршрут, активный шаг до изменения, активный шаг после изменения и связь с уже отправленными во внешнюю CRM событиями. Если операция затронула заявку, по которой уже выполняется повторная интеграционная отправка, аудит обязан показать это явно, чтобы аналитик понимал контекст и мог сопоставить сбой интеграции с изменением маршрута.

                Критерии приёмки:
                1. У каждой массовой операции есть actor, batch id, причина и временная метка.
                2. По каждой затронутой заявке видно старый и новый маршрут, а также активный шаг до и после изменения.
                3. Отчёт аудита отображает связанные интеграционные события и повторные отправки.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(
                    actor="developer",
                    content="Если операция массовая, я бы ещё хранил ссылку на прежний и новый маршрут в JSON-поле аудита.",
                    expect_agent_response=False,
                    label="qa-reuse-3",
                ),
            ],
            proposal=ProposalPlan(
                actor="developer",
                content="Предлагаю изменить требование: нужно дополнительно сохранять старый и новый маршрут в отдельной структуре для последующего сравнения и выводить batch id в истории задачи.",
                review_status="accepted",
                label="accepted-proposal",
            ),
        ),
        TaskScenario(
            index=9,
            title="Дашборд SLA по просроченным заявкам",
            tags=["dashboard", "reports", "audit"],
            initial_content=textwrap.dedent(
                """
                Нужно описать дашборд SLA для аналитика и руководителя процесса. На дашборде должны отображаться заявки с просроченным сроком согласования, заявки с активной эскалацией, среднее время прохождения этапов и отдельный блок для операций, по которым был изменён маршрут согласования после старта процесса.

                Требование должно показать, какие агрегаты считаются в реальном времени, какие можно пересчитывать пакетно, и как связать показатели SLA с аудитом и интеграционными событиями. Это нужно для проверки того, что контекст из предыдущих задач про batch id, повторные интеграционные отправки и историю переходов влияет на следующую validation.

                Критерии приёмки:
                1. Для каждой карточки на дашборде определён источник данных и период обновления.
                2. Заявки с изменённым маршрутом помечаются отдельно от обычных просрочек.
                3. По просроченной заявке можно перейти к аудиту и последним интеграционным попыткам.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать дашборд SLA для аналитика и руководителя процесса. На дашборде отображаются просроченные заявки, активные эскалации, среднее время прохождения этапов, заявки с изменённым маршрутом и заявки, по которым были ошибки повторной интеграционной отправки.

                Требование должно зафиксировать, какие показатели считаются в реальном времени, а какие пересчитываются пакетно, а также как пользователь переходит из карточки SLA к деталям аудита, batch id массовой операции и истории интеграционных попыток. После пост-approval правки нужно заново проверить, что embeddings и validation корректно отражают обновлённое описание без потери предыдущего контекста.

                Критерии приёмки:
                1. Для каждого виджета указан источник данных, правило агрегации и период обновления.
                2. Просрочки с изменённым маршрутом и просрочки с интеграционными ошибками выделяются отдельно.
                3. Из карточки дашборда доступны ссылки на аудит, batch id и историю интеграционных попыток.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(
                    actor="tester",
                    content="Как считать SLA по заявке, если маршрут меняли массово уже после первой эскалации и часть шагов была пересобрана?",
                    expect_agent_response=True,
                    expect_backlog_save=False,
                    label="qa-reuse-4",
                ),
                ChatPlan(actor="developer", content="По дашборду я добавлю отдельный виджет для ошибок повторной интеграционной отправки.", label="team-note"),
            ],
            post_approval_edit=textwrap.dedent(
                """
                ## Пост-approval уточнение

                Для каждой просроченной заявки дашборд дополнительно показывает флаг «исключить из SLA», если заявка переведена в архивный режим по служебному распоряжению. Этот флаг должен сохраняться вместе с причиной исключения и ссылкой на соответствующее аудиторское событие.
                """
            ).strip(),
        ),
        TaskScenario(
            index=10,
            title="Экспорт и архив согласованных заявок",
            tags=["security", "integration", "reports"],
            initial_content=textwrap.dedent(
                """
                Нужно описать экспорт и архивирование согласованных заявок после завершения процесса. Пользователь с административными правами должен иметь возможность выгрузить карточку заявки, историю статусов, список согласующих, вложения и связанные интеграционные статусы, а затем перевести запись в архив без потери возможности для последующего аудита.

                Требование должно учитывать срок хранения, требования к маскированию персональных данных в отчётах и связь с уже сохранёнными batch id массовых операций и интеграционными журналами. Для магистерского сценария важно, чтобы здесь можно было обсудить спорное предложение команды и показать, как аналитик принимает или отклоняет change proposal.

                Критерии приёмки:
                1. Экспорт включает историю статусов, согласующих, вложения и интеграционные события.
                2. Архивирование не удаляет данные, нужные для аудита и расследований.
                3. В отчётах маскируются поля, которые не нужны для просмотра руководителю.
                """
            ).strip(),
            final_content=textwrap.dedent(
                """
                Нужно описать экспорт и архивирование согласованных заявок после завершения процесса. Пользователь с административными правами выгружает карточку заявки, историю статусов, список согласующих, вложения, связанные batch id массовых операций и интеграционные журналы, а затем переводит запись в архивный режим без потери следов для аудита.

                Требование должно отдельно фиксировать правила хранения и маскирования данных. В архиве сохраняются все технические идентификаторы и история действий, но в управленческом отчёте скрываются персональные поля, которые не нужны руководителю. Если заявка участвовала в массовом изменении маршрута или повторной интеграционной отправке, экспорт должен включать эти связи как часть полного следа по заявке.

                Критерии приёмки:
                1. Экспорт включает статусы, согласующих, вложения, batch id и интеграционные события.
                2. Архивирование не удаляет данные, нужные для аудита и регуляторных проверок.
                3. Отчёт для руководителя маскирует поля, не нужные для принятия решения.
                """
            ).strip(),
            team_discussion=[
                ChatPlan(
                    actor="tester",
                    content="Что делать с подписанными файлами, если срок хранения уже истёк, но по заявке ещё открыто расследование?",
                    expect_agent_response=False,
                    label="qa-reuse-5",
                ),
            ],
            proposal=ProposalPlan(
                actor="tester",
                content="Предлагаю изменить требование и разрешить экспортировать в архив также черновики и заявки на доработке, чтобы руководитель видел полный поток без ограничений.",
                review_status="rejected",
                label="rejected-proposal",
            ),
        ),
    ]


def render_readme(summary: dict[str, Any]) -> str:
    task_lines = []
    for item in summary.get("tasks", []):
        backlog_saved = ", ".join(item["qa_backlog_saved"]) if item["qa_backlog_saved"] else "нет"
        backlog_reuse = ", ".join(item["backlog_reuse"]) if item["backlog_reuse"] else "нет"
        task_lines.append(
            f"| {item['index']} | {item['title']} | {', '.join(item['tags'])} | {item['final_status']} | {item['messages_count']} | {backlog_saved} | {backlog_reuse} |"
        )
    llm_checks = summary.get("llm", {}).get("provider_checks_after_bootstrap", [])
    llm_lines = [
        f"- {item['name']} ({item['provider_kind']}/{item['model']}): "
        f"ok={item['result'].get('ok') if item['result'] else 'not-tested'} "
        f"required={item['required_for_simulation']} default={item['is_runtime_default']}"
        for item in llm_checks
    ] or ["- Проверки провайдеров не сохранены."]
    account_lines = [
        f"- {item['alias']}: `{item['email']}` / `{item['password']}` / роль `{item['role']}`"
        for item in summary.get("accounts", [])
    ]
    content = textwrap.dedent(
        f"""
        # Team Flow Simulation 2026-04-26

        ## Контур

        - API: `{summary.get('api_base_url', API_BASE_URL)}`
        - Проект: `{summary.get('project', {}).get('name', PROJECT_NAME)}`
        - Project ID: `{summary.get('project', {}).get('id', 'n/a')}`

        ## Учётки

        {chr(10).join(account_lines) if account_lines else '- Учётки не сохранены.'}

        ## Теги

        - {', '.join(summary.get('tags', []))}

        ## LLM-проверка

        {chr(10).join(llm_lines)}

        ## Задачи

        | № | Заголовок | Теги | Финальный статус | Сообщений | Backlog сохранён | Backlog reused |
        | --- | --- | --- | --- | ---: | --- | --- |
        {chr(10).join(task_lines) if task_lines else '| - | - | - | - | - | - | - |'}

        ## Артефакты

        - `tasks/` содержит исходные описания задач.
        - `history/` содержит поминутную историю по каждой задаче.
        - `attachments/` содержит текстовые файлы, загруженные через API.
        - `summary.json` содержит машинно-читаемый итог прогона.
        """
    ).strip()
    return content + "\n"


def main() -> int:
    runner = SimulationRunner()
    try:
        runner.run()
    except Exception as exc:  # pragma: no cover - runtime orchestration
        runner.summary.setdefault("issues", []).append(
            {"at": now_iso(), "type": type(exc).__name__, "message": str(exc)}
        )
        write_text(SUMMARY_PATH, json.dumps(runner.summary, ensure_ascii=False, indent=2) + "\n")
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
