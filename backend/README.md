# Backend

Backend - асинхронное FastAPI-приложение для Task Platform MVP. Он отвечает за пользователей, авторизацию, проекты, задачи, чат, валидацию требований, RAG-индексацию, LLM runtime, мониторинг, аудит и интеграцию с Qdrant.

ИИ-взаимодействие реализовано через LangGraph. Роутеры и сервисы не должны напрямую привязываться к конкретному LLM-провайдеру: вызовы проходят через `LLMRuntimeService`, а сценарии оформлены как графы или subgraphs.

## Стек

- Python `>=3.12,<3.15`
- FastAPI, Uvicorn
- SQLAlchemy AsyncIO, asyncpg, psycopg
- Alembic
- PostgreSQL
- Qdrant, LangChain Qdrant
- LangGraph, LangChain OpenAI/Ollama
- Pydantic v2, pydantic-settings
- pytest, pytest-asyncio, ruff, mypy

## Структура

```text
backend/
|-- alembic/              # миграции PostgreSQL
|-- app/
|   |-- agents/           # LangGraph-графы, agent registry, RAG pipeline
|   |-- core/             # config, database, security, dependencies
|   |-- models/           # SQLAlchemy-модели
|   |-- routers/          # FastAPI routers
|   |-- schemas/          # Pydantic-схемы входа и ответа
|   `-- services/         # бизнес-логика и интеграции
|-- tests/                # pytest-тесты API, сервисов и agent-графов
|-- main.py               # ASGI entrypoint и wiring приложения
|-- pyproject.toml
`-- README.md
```

## Запуск приложения

`main.py` создает FastAPI app, подключает CORS, роутеры, статическую раздачу uploads и экспортированных LangGraph-схем. На старте backend:

- создает `UPLOAD_DIR`;
- проверяет и создает Qdrant-коллекции;
- экспортирует схемы LangGraph в `LANGGRAPH_IMAGES_DIR`;
- публикует `/healthz` и `/readyz`.

Health endpoints:

- `GET /healthz` - процесс отвечает.
- `GET /readyz` - backend готов работать с БД.

Статические пути:

- `/uploads` и `/api/uploads` - файлы вложений.
- `/langgraph-images` и `/api/langgraph-images` - экспортированные схемы графов.

## Доменная модель

Ключевые SQLAlchemy-сущности:

- `User` - пользователь с email, хешем пароля, профилем, avatar URL, ролью и статусом активности.
- `RefreshToken` - refresh-сессия с ротацией и отзывом.
- `Project` - проект с названием, описанием и настройками включения узлов валидации.
- `ProjectMember` - участие пользователя в проекте.
- `CustomRule` - правило качества требований на уровне проекта.
- `Task` - задача/требование с текстом, тегами, статусом, участниками, результатом валидации и временем последней индексации.
- `TaskAttachment` - вложение задачи: имя файла, MIME-тип, путь хранения и `alt_text`.
- `Message` - сообщение чата: пользовательское, агентное, вопрос или предложение изменения.
- `ChangeProposal` - предложение изменения требования со статусом рассмотрения.
- `ValidationQuestion` - вопрос из очереди/банка валидации.
- `TaskTag` и `ProjectTaskTag` - справочник тегов и связь с проектами.
- `AuditEvent` - журнал действий.
- `LLMProviderConfig`, `LLMAgentOverride`, `LLMRequestLog`, `LLMRuntimeSettings`, `LLMAgentPromptConfig`, `LLMAgentPromptVersion` - настройки, overrides, prompt configs и журналы LLM runtime.

## Роли и доступ

Глобальные роли:

- `ADMIN` - администрирование пользователей, LLM runtime, мониторинга, Qdrant, тегов, вопросов и правил.
- `ANALYST` - создание и ведение требований, валидация, подготовка к разработке.
- `DEVELOPER` - работа с задачей после передачи в разработку.
- `TESTER` - проверка задачи после разработки.
- `MANAGER` - управленческий доступ в рамках проектных сценариев.

Проверки доступа собраны в `app/core/dependencies.py`. Авторизация использует access token в памяти frontend и refresh token в `httpOnly` cookie.

## Жизненный цикл задачи

Фактические статусы из `TaskStatus`:

```text
draft
  -> validating
  -> needs_rework или awaiting_approval
  -> ready_for_dev
  -> in_progress
  -> ready_for_testing
  -> testing
  -> done
```

Основные правила:

- задача создается в `draft`;
- запуск валидации переводит задачу в `validating`;
- успешная валидация переводит задачу в `awaiting_approval`;
- неуспешная валидация переводит задачу в `needs_rework`;
- подтверждение аналитиком/проверяющим и назначение команды переводит задачу в `ready_for_dev`;
- разработчик переводит задачу в `in_progress`, затем в `ready_for_testing`;
- тестировщик переводит задачу в `testing`, затем в `done`;
- изменения подтвержденной задачи требуют commit и повторной валидации.

## API-роутеры

Все роутеры подключаются в `main.py`.

### `auth.py`

- `POST /auth/register` - регистрация.
- `POST /auth/login` - вход и выдача access token.
- `POST /auth/refresh` - ротация refresh token.
- `POST /auth/logout` - выход.
- `GET /auth/me` - текущий пользователь.
- `GET /auth/sessions` - активные сессии.
- `DELETE /auth/sessions/{session_id}` - отзыв сессии.

### `users.py`

- `GET /users` - список пользователей.
- `PATCH /users/me` - обновление профиля.
- `POST /users/me/avatar` - загрузка аватара.
- `PATCH /users/{user_id}` - админское обновление пользователя.

### `projects.py`

- CRUD проектов.
- Управление участниками проекта.
- CRUD кастомных правил проекта.

### `tasks.py`

- CRUD задач внутри проекта.
- `POST /projects/{project_id}/tasks/{task_id}/suggest-tags` - AI-подсказка тегов.
- `POST /projects/{project_id}/tasks/{task_id}/commit` - фиксация изменений.
- `POST /projects/{project_id}/tasks/{task_id}/approve` - подтверждение требования.
- `POST /start-development`, `/ready-for-testing`, `/start-testing`, `/complete` - workflow-переходы.
- `POST /attachments` - загрузка вложения.

### `validation.py`

- `POST /tasks/{task_id}/validate` - запуск LangGraph-валидации.

### `chat.py`

- `GET /tasks/{task_id}/messages` - история чата.
- `POST /tasks/{task_id}/messages` - отправка сообщения и запуск agent-routing.
- WebSocket endpoint в этом же роутере публикует обновления чата.

### `proposals.py`

- `GET /tasks/{task_id}/proposals` - список предложений изменений.
- `PATCH /tasks/{task_id}/proposals/{proposal_id}` - принять или отклонить предложение.

### `task_tags.py`

- `GET /projects/{project_id}/task-tags` - доступные теги проекта.
- `POST /projects/{project_id}/task-tags` - добавить тег в проект.
- `DELETE /projects/{project_id}/task-tags/{tag_id}` - удалить тег из проекта.

### `admin.py`

Админский роутер покрывает:

- LLM provider configs и тест провайдера;
- Vision test;
- runtime default provider и runtime settings;
- agent overrides;
- agent directory;
- prompt configs, версии и restore;
- monitoring summary, activity, LLM metrics;
- Qdrant overview, coverage, scenario probes и resync задачи;
- LLM request logs;
- audit feed;
- validation questions;
- task tags.

## Сервисный слой

Сервисы отделяют бизнес-логику от FastAPI-роутеров:

- `auth_service.py` - пароли, access/refresh tokens, сессии.
- `project_service.py` - проекты, участники, правила.
- `task_service.py` - задачи, workflow, вложения, revalidation flags.
- `chat_service.py` и `chat_realtime.py` - сообщения, агентные ответы, WebSocket-publish.
- `proposal_service.py` - предложения изменений.
- `validation_question_service.py` - вопросы валидации.
- `task_tag_service.py` - справочник тегов и проектные связи.
- `qdrant_service.py`, `rag_service.py`, `attachment_content_service.py` - RAG и векторные коллекции.
- `llm_runtime_service.py`, `llm_prompt_service.py`, `llm_agent_registry.py`, `llm_prompt_registry.py` - runtime LLM, prompts и agent directory.
- `admin_llm_service.py`, `admin_qdrant_service.py`, `monitoring_service.py`, `audit_service.py` - админские сценарии.

## LangGraph и RAG

`app/agents` содержит весь agentic-слой:

- `validation_graph.py` - проверка требований.
- `rag_pipeline.py` - подготовка chunks и payload для Qdrant.
- `chat_graph.py` - общий граф обработки сообщений.
- `qa_agent_graph.py` - ответы на вопросы.
- `change_tracker_agent_graph.py` - предложения изменений и дедупликация.
- `manager_agent_graph.py` - fallback и forced routing.
- `task_tag_suggestion_graph.py` - подбор тегов.
- `provider_test_graph.py`, `vision_test_graph.py`, `attachment_vision_graph.py` - проверки провайдера и Vision.
- `subgraph_registry.py` - регистрация встроенных и внешних agent subgraphs.
- `graph_export.py` - экспорт схем графов.

Qdrant-коллекции:

- `task_knowledge` - знания по задачам.
- `project_questions` - вопросы валидации.
- `task_proposals` - предложения изменений.

RAG-параметры задаются через `RAG_CHUNK_TARGET_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS`, `RAG_ATTACHMENT_MAX_TEXT_CHARS`, `RAG_VISION_ENABLED`, `RAG_VISION_MAX_IMAGE_BYTES`.

## Переменные окружения

Смотрите `backend/.env.example`. Минимальный набор для локального dev:

```env
DATABASE_URL=postgresql+asyncpg://app_user:app_pass@localhost:5432/taskplatform
JWT_SECRET_KEY=replace_with_a_long_random_secret
ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
COOKIE_SECURE=false
COOKIE_DOMAIN=
QDRANT_URL=http://localhost:6333
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
UPLOAD_DIR=./uploads
```

Для production-like запуска через Compose часть значений переопределяется в `docker-compose.yml`: `DATABASE_URL`, `QDRANT_URL`, `OLLAMA_BASE_URL`, `UPLOAD_DIR`, `LANGGRAPH_IMAGES_DIR`.

## Миграции

```bash
cd backend
alembic upgrade head
```

В Docker Compose миграции выполняет отдельный сервис `migrate`; основной backend стартует только после успешного завершения миграций.

## Проверки

```bash
cd backend
ruff check .
ruff format --check .
mypy .
pytest
```

Из корня:

```bash
make backend-lint
make backend-test
```
