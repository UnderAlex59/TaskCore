# Backend

Backend - асинхронное FastAPI-приложение для Task Platform MVP. Он отвечает за авторизацию, проекты, задачи, чат, валидацию требований, RAG-индексацию, LLM runtime, мониторинг и интеграцию с Qdrant.

## Стек

- Python `>=3.12,<3.15`
- FastAPI, Uvicorn
- SQLAlchemy AsyncIO, asyncpg, psycopg
- Alembic
- PostgreSQL
- Qdrant, LangChain Qdrant
- LangGraph
- LangChain OpenAI/Ollama
- Pydantic v2, pydantic-settings
- pytest, ruff, mypy

## Структура

```text
backend/
├── alembic/              # миграции БД
├── app/
│   ├── agents/           # LangGraph-графы и registry subgraphs
│   ├── core/             # конфигурация, БД, безопасность, dependencies
│   ├── models/           # SQLAlchemy-модели
│   ├── routers/          # FastAPI routers
│   ├── schemas/          # Pydantic-схемы
│   └── services/         # бизнес-логика
├── tests/                # pytest-тесты API и сервисов
├── main.py               # ASGI entrypoint
├── pyproject.toml
└── README.md
```

## Основные доменные сущности

- `User` - пользователь с глобальной ролью, профилем и статусом активности.
- `Project` - проект с настройками узлов валидации.
- `ProjectMember` - роль пользователя внутри проекта.
- `Task` - задача/требование с тегами, статусом, командой и результатом валидации.
- `TaskAttachment` - вложение задачи, сейчас индексируется как метаданные файла.
- `Message` - сообщение чата, включая ответы агентов.
- `ChangeProposal` - предложение изменения требования.
- `ValidationQuestion` - вопрос из очереди/банка валидации.
- `TaskTag` - справочник тегов.
- `AuditEvent` - журнал действий.
- `LLMProviderConfig`, `LLMAgentOverride`, `LLMRequestLog`, `LLMRuntimeSettings` - runtime-настройки LLM и мониторинг вызовов.

## API-модули

- `auth.py` - регистрация, login, refresh, logout, текущий пользователь.
- `users.py` - управление пользователями.
- `projects.py` - проекты и участники.
- `tasks.py` - CRUD задач, commit изменений, подтверждение, вложения.
- `validation.py` - запуск валидации задачи.
- `chat.py` - сообщения и WebSocket stream.
- `proposals.py` - просмотр и рассмотрение предложений изменений.
- `task_tags.py` - справочник тегов.
- `admin.py` - LLM-провайдеры, overrides, мониторинг, audit, validation questions, task tags.

## Жизненный цикл задачи

```text
draft
  -> validating
  -> needs_rework или awaiting_approval
  -> ready_for_dev
  -> in_progress
  -> done
```

Важные правила:

- создавать, редактировать, валидировать и подтверждать задачи могут `ADMIN` и `ANALYST`;
- после успешной валидации задача переходит в `awaiting_approval`;
- при подтверждении назначаются разработчик и тестировщик, задача становится `ready_for_dev`;
- чат до формирования команды доступен аналитику и администратору, после `ready_for_dev` - также разработчику и тестировщику;
- изменения после подтверждения помечают задачу как требующую commit и повторной валидации.

## LangGraph и RAG

Backend использует LangGraph как основной слой взаимодействия с ИИ:

- `app/agents/validation_graph.py` - валидация требований.
- `app/agents/rag_pipeline.py` - подготовка chunks для индексации.
- `app/agents/chat_graph.py` - маршрутизация чата к subgraphs.
- `app/agents/qa_agent_graph.py` - ответы на вопросы.
- `app/agents/change_tracker_agent_graph.py` - предложения изменений.
- `app/agents/manager_agent_graph.py` - fallback и forced routing.
- `app/agents/provider_test_graph.py` - проверка LLM-провайдера.

Qdrant-коллекции:

- `task_knowledge`
- `project_questions`
- `task_proposals`

## Переменные окружения

Смотрите `backend/.env.example`. Минимальный набор для локального запуска:

```env
DATABASE_URL=postgresql+asyncpg://app_user:app_pass@localhost:5432/taskplatform
JWT_SECRET_KEY=replace_with_a_long_random_secret
ALLOWED_ORIGINS=["http://localhost:5173"]
QDRANT_URL=http://localhost:6333
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
UPLOAD_DIR=/var/lib/task-platform/uploads
```

Если внешний LLM недоступен, часть графов использует fallback-логику, но Qdrant embeddings требуют настроенного embedding provider.

## Запуск

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn main:app --reload
```

Health endpoints:

- `GET /healthz`
- `GET /readyz`

## Проверки

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Или из корня репозитория:

```bash
make backend-lint
make backend-test
```
