# Интеллектуальная платформа управления задачами

## Техническая спецификация текущей реализации

Документ описывает фактическую архитектуру проекта `mvp` в поддерживаемом Markdown-формате. PDF-версия считается сгенерированным артефактом и отдельно не обновляется.

## 1. Назначение системы

Task Platform MVP - веб-приложение для управления задачами и требованиями в Agile-команде. Платформа помогает аналитику формулировать требования, автоматически проверяет качество постановки, сохраняет контекст проекта в RAG-хранилище и поддерживает обсуждение задачи с участием LangGraph-агентов.

Основные возможности:

- управление пользователями и ролями;
- проекты и участники проектов;
- задачи/требования с полным workflow;
- загрузка вложений;
- автоматическая валидация требований;
- командный чат задачи;
- ответы на вопросы по контексту задачи;
- предложения изменений и их рассмотрение;
- RAG-поиск по задачам, вопросам и предложениям;
- администрирование LLM-провайдеров, prompts, overrides, мониторинга и Qdrant.

## 2. Роли

Глобальные роли задаются в `backend/app/models/user.py`:

- `ADMIN` - управляет системными справочниками, пользователями, LLM runtime, Qdrant и мониторингом.
- `ANALYST` - создает, редактирует, валидирует и подтверждает требования.
- `DEVELOPER` - ведет задачу в разработке.
- `TESTER` - ведет задачу на тестировании.
- `MANAGER` - участвует в управленческих сценариях проекта.

Проектное участие хранится отдельно от глобальной роли. Проверки доступа выполняются через зависимости backend.

## 3. Технологический стек

| Слой | Технологии | Назначение |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, Zustand, Axios, Tailwind CSS | SPA с приватными маршрутами, рабочими экранами и админкой |
| Backend | FastAPI, Uvicorn, SQLAlchemy AsyncIO, Alembic, Pydantic v2 | REST/WebSocket API, бизнес-логика, миграции |
| Основная БД | PostgreSQL | Пользователи, проекты, задачи, сообщения, предложения, аудит, настройки |
| Векторная БД | Qdrant | RAG-память задач, вопросов и предложений изменений |
| AI-слой | LangGraph, LangChain, `LLMRuntimeService` | Валидация, чат-агенты, RAG, Vision, тесты провайдеров |
| LLM providers | OpenAI, Ollama, OpenRouter, GigaChat, OpenAI-compatible API | Облачный и локальный inference через единый runtime |
| Infra | Docker Compose, nginx, health/readiness endpoints | Локальный production-like контур |
| Quality | pytest, ruff, mypy, Vitest, ESLint, TypeScript, Vite build | Проверка backend и frontend |

## 4. Репозиторий

```text
.
|-- backend/
|   |-- alembic/
|   |-- app/
|   |   |-- agents/
|   |   |-- core/
|   |   |-- models/
|   |   |-- routers/
|   |   |-- schemas/
|   |   `-- services/
|   |-- tests/
|   |-- main.py
|   `-- pyproject.toml
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- auth/
|   |   |-- features/
|   |   |-- shared/
|   |   `-- store/
|   |-- package.json
|   `-- vite.config.ts
|-- deploy/nginx/
|-- docs/
|-- langgraph_graphs/
|-- docker-compose.yml
|-- Makefile
|-- README.md
|-- SETUP_GUIDE.md
`-- WINDOWS_SETUP.md
```

## 5. Backend entrypoint

`backend/main.py` собирает приложение:

- создает FastAPI app с названием "Интеллектуальная платформа управления задачами";
- подключает CORS по `ALLOWED_ORIGINS`;
- подключает все routers;
- монтирует uploads;
- монтирует экспортированные LangGraph-схемы;
- публикует `/healthz` и `/readyz`;
- на lifespan создает каталог uploads, проверяет Qdrant-коллекции и экспортирует схемы графов.

`/readyz` проверяет доступность PostgreSQL. Это endpoint для readiness, а не только для проверки процесса.

## 6. Конфигурация backend

`backend/app/core/config.py` читает `.env` как UTF-8 через Pydantic Settings.

Группы настроек:

- Database: `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`.
- JWT: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`.
- Cookie: `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN`.
- CORS: `ALLOWED_ORIGINS`.
- Agents: `CHAT_AGENT_MODULES`.
- Qdrant: `QDRANT_URL`, `QDRANT_API_KEY`.
- Providers: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL`, GigaChat TLS-настройки.
- Embeddings: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`.
- LLM settings: `LLM_SETTINGS_ENCRYPTION_KEY`.
- RAG: `RAG_CHUNK_TARGET_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS`, `RAG_ATTACHMENT_MAX_TEXT_CHARS`, `RAG_VISION_ENABLED`, `RAG_VISION_MAX_IMAGE_BYTES`.
- Storage: `UPLOAD_DIR`, `LANGGRAPH_IMAGES_DIR`.

Пустые optional-значения приводятся к `None`. `ALLOWED_ORIGINS` и `CHAT_AGENT_MODULES` можно задавать JSON-массивом или списком через запятую.

## 7. Модель данных PostgreSQL

Основные таблицы:

- `users` - учетные записи, роли, профиль, avatar URL, активность.
- `refresh_tokens` - refresh-сессии, ротация и отзыв.
- `projects` - проекты и настройки включения узлов валидации.
- `project_members` - участники проекта.
- `custom_rules` - кастомные правила проекта.
- `tasks` - задачи/требования.
- `task_attachments` - вложения задач.
- `messages` - сообщения чата и agent messages.
- `change_proposals` - предложения изменений.
- `validation_questions` - вопросы валидации.
- `task_tags`, `project_task_tags` - справочник тегов и связь с проектами.
- `audit_events` - журнал действий.
- `llm_provider_configs` - настройки LLM-провайдеров.
- `llm_agent_overrides` - overrides на уровне agent key.
- `llm_request_logs` - журнал LLM-вызовов.
- `llm_runtime_settings` - runtime defaults.
- `llm_agent_prompt_configs`, `llm_agent_prompt_versions` - prompt configs и версии.

Ключевая сущность `Task` содержит:

- `title`, `content`, `tags`;
- `status`;
- `created_by`;
- `analyst_id`;
- `reviewer_analyst_id`;
- `developer_id`;
- `tester_id`;
- `reviewer_approved_at`;
- `validation_result`;
- `indexed_at`;
- timestamps.

## 8. Жизненный цикл задачи

Фактические статусы:

```text
draft
  -> validating
  -> needs_rework
  -> awaiting_approval
  -> ready_for_dev
  -> in_progress
  -> ready_for_testing
  -> testing
  -> done
```

Ветка после `validating` зависит от результата LangGraph-валидации:

- `approved` переводит задачу в `awaiting_approval`;
- `needs_rework` переводит задачу в `needs_rework`.

После ручного подтверждения и назначения команды задача становится `ready_for_dev`. Дальше разработчик и тестировщик ведут workflow до `done`.

Изменения подтвержденной задачи фиксируются через commit и требуют повторной валидации, чтобы RAG и статус требования оставались согласованными.

## 9. Backend API

API строится из FastAPI routers.

### Auth

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /auth/sessions`
- `DELETE /auth/sessions/{session_id}`

### Users

- `GET /users`
- `PATCH /users/me`
- `POST /users/me/avatar`
- `PATCH /users/{user_id}`

### Projects

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `GET /projects/{project_id}/members`
- `POST /projects/{project_id}/members`
- `DELETE /projects/{project_id}/members/{...}`
- `GET /projects/{project_id}/rules`
- `POST /projects/{project_id}/rules`
- `PATCH /projects/{project_id}/rules/{rule_id}`
- `DELETE /projects/{project_id}/rules/{rule_id}`

### Tasks

- `GET /projects/{project_id}/tasks`
- `POST /projects/{project_id}/tasks`
- `GET /projects/{project_id}/tasks/{task_id}`
- `PATCH /projects/{project_id}/tasks/{task_id}`
- `POST /projects/{project_id}/tasks/{task_id}/suggest-tags`
- `POST /projects/{project_id}/tasks/{task_id}/commit`
- `POST /projects/{project_id}/tasks/{task_id}/approve`
- `POST /projects/{project_id}/tasks/{task_id}/start-development`
- `POST /projects/{project_id}/tasks/{task_id}/ready-for-testing`
- `POST /projects/{project_id}/tasks/{task_id}/start-testing`
- `POST /projects/{project_id}/tasks/{task_id}/complete`
- `DELETE /projects/{project_id}/tasks/{task_id}`
- `POST /projects/{project_id}/tasks/{task_id}/attachments`

### Validation, Chat, Proposals

- `POST /tasks/{task_id}/validate`
- `GET /tasks/{task_id}/messages`
- `POST /tasks/{task_id}/messages`
- WebSocket для обновлений чата задачи.
- `GET /tasks/{task_id}/proposals`
- `PATCH /tasks/{task_id}/proposals/{proposal_id}`

### Task Tags

- `GET /projects/{project_id}/task-tags`
- `POST /projects/{project_id}/task-tags`
- `DELETE /projects/{project_id}/task-tags/{tag_id}`

### Admin

Админский API покрывает:

- provider configs: список, создание, обновление, тест;
- Vision test;
- runtime default provider и settings;
- agent overrides и directory;
- prompt configs, версии и restore;
- monitoring summary, activity, LLM metrics;
- Qdrant overview, coverage, probes, task resync;
- LLM request logs;
- audit feed;
- validation questions;
- task tags.

## 10. Сервисный слой

Сервисы являются основным местом бизнес-логики:

- `AuthService` управляет паролями, access/refresh tokens и сессиями.
- `ProjectService` управляет проектами, участниками и правилами.
- `TaskService` управляет задачами, workflow, commit, вложениями и revalidation flags.
- `ChatService` сохраняет сообщения и запускает LangGraph-обработку.
- `ChatRealtimeService` публикует WebSocket-обновления.
- `ProposalService` управляет предложениями изменений.
- `ValidationQuestionService` управляет банком вопросов.
- `TaskTagService` управляет справочником тегов.
- `QdrantService` и `RagService` обслуживают RAG.
- `LLMRuntimeService` выбирает провайдера, модель, параметры и логирует запросы.
- `LLMPromptService` управляет prompt configs.
- `MonitoringService`, `AuditService`, `AdminQdrantService`, `AdminLLMService` обслуживают админку.

## 11. Agentic-слой LangGraph

Все AI-сценарии описаны через LangGraph:

- `validation_graph.py` - валидация требования.
- `rag_pipeline.py` - подготовка индексируемого контекста.
- `chat_graph.py` - маршрутизация чата.
- `qa_agent_graph.py` - ответы на вопросы по задаче.
- `change_tracker_agent_graph.py` - предложения изменений.
- `manager_agent_graph.py` - fallback и forced routing.
- `task_tag_suggestion_graph.py` - подсказки тегов.
- `provider_test_graph.py` - проверка provider config.
- `vision_test_graph.py` - проверка Vision-провайдера.
- `attachment_vision_graph.py` - описание изображений вложений.

`subgraph_registry.py` регистрирует agent subgraphs. Внешние subgraphs подключаются через `CHAT_AGENT_MODULES`.

`graph_export.py` экспортирует схемы в `LANGGRAPH_IMAGES_DIR`, после чего backend раздает их как статические файлы.

## 12. Chat routing

Поток сообщения:

1. Frontend отправляет сообщение в задачу.
2. Backend сохраняет его в `messages`.
3. `ChatService` определяет грубый тип сообщения.
4. `chat_graph` строит context.
5. Forced routing по prefix отправляет сообщение в заданный agent alias.
6. Без prefix registry выбирает subgraph через `can_handle`.
7. Subgraph возвращает ответ и source reference.
8. Backend сохраняет agent message и связанные артефакты.
9. WebSocket публикует обновление участникам задачи.

Примеры forced aliases:

- `@qa`
- `@change-tracker`
- aliases внешних modules из `CHAT_AGENT_MODULES`.

## 13. RAG и Qdrant

Qdrant используется как векторная память проекта. Коллекции:

- `task_knowledge` - задачи, результаты валидации, вложения и контекстные chunks.
- `project_questions` - вопросы валидации.
- `task_proposals` - предложения изменений и поиск дублей.

RAG pipeline собирает фрагменты из:

- заголовка;
- описания;
- тегов;
- текстового содержимого вложений в пределах лимита;
- `alt_text` изображений при включенной Vision-обработке;
- результата валидации.

Параметры chunking и Vision задаются env-переменными. Если Vision или конкретный LLM-провайдер недоступен, документация не должна описывать расширенную мультимодальную обработку как гарантированную для каждого запуска.

## 14. LLM runtime

`LLMRuntimeService` скрывает различия провайдеров. Он учитывает:

- default provider;
- provider configs из БД;
- agent overrides;
- prompt configs;
- модель и температуру;
- provider-specific параметры;
- логирование LLM-запросов.

Админка позволяет тестировать провайдеры, менять defaults, смотреть журналы и переопределять agent-specific настройки.

## 15. Frontend архитектура

Frontend - Vite SPA.

Основные каталоги:

- `src/api` - typed API clients.
- `src/auth` - авторизация, guards, login/register.
- `src/features` - доменные экраны.
- `src/shared` - общие компоненты, hooks и helpers.
- `src/store` - Zustand stores.
- `src/test` - setup тестов.

Маршруты:

- `/`, `/login`, `/register`;
- `/profile`;
- `/projects`;
- `/projects/:projectId/tasks`;
- `/projects/:projectId/tasks/new`;
- `/projects/:projectId/tasks/:taskId`;
- `/projects/:projectId/tasks/:taskId/chat`;
- `/admin/monitoring`;
- `/admin/qdrant`;
- `/admin/llm-requests`;
- `/admin/validation-questions`;
- `/admin/task-tags`;
- `/admin/providers`;
- `/admin/vision-test`;
- `/admin/agent-prompts`;
- `/admin/users`;
- `/admin/projects/:projectId/rules`.

## 16. Frontend auth flow

Access token хранится в Zustand store. Refresh token хранится в `httpOnly` cookie. `AuthProvider` восстанавливает сессию при старте, `ProtectedRoute` закрывает приватные маршруты, `RoleGuard` закрывает админку.

Axios client:

- добавляет Bearer token;
- выполняет refresh при 401;
- защищает от параллельных refresh-запросов очередью;
- очищает auth state при невозможности восстановить сессию.

## 17. Docker Compose

Compose-сервисы:

- `postgres`
- `qdrant`
- `ollama`
- `ollama-init`
- `migrate`
- `backend`
- `frontend`

Порядок старта:

1. PostgreSQL проходит healthcheck.
2. Qdrant стартует.
3. Ollama проходит healthcheck.
4. `ollama-init` при необходимости загружает embedding-модель.
5. `migrate` выполняет Alembic migrations.
6. Backend стартует и проходит readiness.
7. Frontend/nginx стартует и публикует порт `${FRONTEND_PORT:-8080}`.

## 18. Проверки

Makefile:

- `make backend-lint`
- `make backend-test`
- `make frontend-lint`
- `make frontend-test`
- `make frontend-build`
- `make check`
- `make docker-build`
- `make compose-up`
- `make compose-down`

Backend напрямую:

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Frontend напрямую:

```bash
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

## 19. Кодировка

Markdown и русские UI-тексты должны храниться в UTF-8. Если PowerShell отображает русские символы некорректно, нужно включить UTF-8 output encoding в текущей сессии. Некорректные строки вида mojibake не должны попадать в документацию и пользовательские тексты.

## 20. Границы текущей реализации

- `architecture-spec.pdf` не является источником истины для текущей правки.
- Source of truth для API - `backend/app/routers`.
- Source of truth для env - `backend/app/core/config.py`, `.env.example` и `docker-compose.yml`.
- Source of truth для frontend routes - `frontend/src/App.tsx`.
- Source of truth для AI-слоя - `backend/app/agents` и `backend/app/services/llm_runtime_service.py`.
- Новые AI-сценарии должны добавляться как LangGraph graph/subgraph и регистрироваться через существующий registry/runtime слой.
