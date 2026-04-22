# Task Platform MVP

Интеллектуальная платформа управления задачами и требованиями для Agile-команд. Проект объединяет трекер задач, командный чат, автоматическую валидацию требований, RAG-память проекта и администрируемый слой LLM-агентов.

Фактический стек текущей реализации:

- backend: FastAPI, SQLAlchemy AsyncIO, Alembic, PostgreSQL, Qdrant, LangGraph, LangChain;
- frontend: React 19, TypeScript, Vite, React Router, Zustand, Axios, Tailwind CSS;
- инфраструктура: Docker Compose для локального production-like запуска и Helm chart для Kubernetes;
- LLM-провайдеры: OpenAI, Ollama, OpenRouter, GigaChat и OpenAI-compatible API через единый runtime-слой.

## Что реализовано

- Регистрация, вход, refresh-токены, роли `ADMIN`, `ANALYST`, `DEVELOPER`, `TESTER`, `MANAGER`.
- Проекты и состав команды проекта.
- Задачи с жизненным циклом `draft -> validating -> needs_rework / awaiting_approval -> ready_for_dev -> in_progress -> done`.
- Назначение аналитика, разработчика и тестировщика.
- Теги задач как справочник, управляемый администратором.
- Вложения к задачам и индексирование контекста в Qdrant.
- Автоматическая валидация требований через LangGraph.
- Командный чат задачи с WebSocket-обновлениями.
- QA Agent, ChangeTracker Agent и Manager Agent как LangGraph subgraphs.
- Предложения изменений с рассмотрением `new`, `accepted`, `rejected`.
- Банк вопросов валидации и админская страница для его просмотра.
- Админка LLM-провайдеров, agent overrides, мониторинга и audit feed.
- Экспорт схем LangGraph в `langgraph_graphs`.
- Docker Compose, Helm chart, health/readiness endpoints и CI-команды.

## Структура репозитория

```text
.
├── backend/                 # FastAPI API, модели, сервисы, LangGraph-графы, Alembic
├── frontend/                # React/Vite SPA
├── deploy/helm/task-platform/ # Kubernetes Helm chart
├── langgraph_graphs/        # экспортированные PNG/HTML схемы графов
├── docs/                    # проектная документация и планы актуализации
├── docker-compose.yml       # локальный production-like контур
├── Makefile                 # команды проверки, сборки и деплоя
└── README.md
```

Подробности по подмодулям:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)
- [backend/app/agents/README.md](backend/app/agents/README.md)
- [deploy/helm/task-platform/README.md](deploy/helm/task-platform/README.md)
- [docs/report-update-plan.md](docs/report-update-plan.md)

## Быстрый запуск через Docker Compose

Создайте или проверьте `backend/.env` и `frontend/.env`. Примеры лежат в `backend/.env.example` и `frontend/.env.example`.

```bash
docker compose up --build -d
```

После запуска:

- frontend: `http://localhost:8080`
- backend health: `http://localhost:8080/healthz`
- backend readiness: `http://localhost:8080/readyz`

Порт frontend можно переопределить переменной `FRONTEND_PORT`, например `FRONTEND_PORT=80`.

## Локальная разработка

Backend:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Для локального frontend по умолчанию используется `VITE_API_PROXY_TARGET=http://localhost:8000`, а production-сборка работает через относительный путь `/api`.

## Проверки

```bash
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

## Важные переменные окружения

Backend:

- `DATABASE_URL` - PostgreSQL DSN для SQLAlchemy AsyncIO.
- `JWT_SECRET_KEY` - секрет подписи JWT.
- `ALLOWED_ORIGINS` - разрешенные origins для CORS.
- `QDRANT_URL`, `QDRANT_API_KEY` - подключение к Qdrant.
- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_TEMPERATURE` - дефолтный LLM runtime.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL` - настройки провайдеров.
- `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` - модель и размерность эмбеддингов.
- `CHAT_AGENT_MODULES` - внешние модули agent subgraphs.
- `CHAT_AGENT_LLM_OVERRIDES` - JSON-настройки LLM на уровне агентов.
- `UPLOAD_DIR` - каталог вложений.
- `LANGGRAPH_IMAGES_DIR` - каталог экспорта схем графов.

Frontend:

- `VITE_API_URL` - base URL API, в production обычно `/api`.
- `VITE_API_PROXY_TARGET` - цель dev proxy для Vite.

## Agent/RAG контур

Взаимодействие с ИИ идет через LangGraph:

- `validation_graph` проверяет требования по базовым правилам, кастомным правилам и контекстным вопросам из RAG.
- `rag_pipeline` собирает chunks из заголовка, описания, тегов, вложений и результата валидации.
- `chat_graph` маршрутизирует сообщения в agent subgraphs.
- `qa_agent_graph` отвечает на вопросы по задаче и контексту.
- `change_tracker_agent_graph` выделяет предложения изменений и проверяет дубли.
- `manager_agent_graph` выступает fallback-агентом и объясняет маршрутизацию.

Qdrant использует коллекции:

- `task_knowledge` - контекст задач;
- `project_questions` - банк вопросов для повторной валидации;
- `task_proposals` - предложения изменений и поиск дублей.

## Развертывание в Kubernetes

Helm chart расположен в `deploy/helm/task-platform` и включает backend, frontend, migration job, ingress, HPA, PDB и PVC для загрузок.

```bash
helm upgrade --install task-platform deploy/helm/task-platform \
  -n task-platform \
  --create-namespace \
  -f deploy/helm/task-platform/values.production.yaml
```

Перед production-развертыванием заполните образа, `DATABASE_URL`, `JWT_SECRET_KEY`, ingress host, TLS и параметры storage.
