# Структура репозитория

## Карта верхнего уровня

| Путь | Ответственность |
| --- | --- |
| `backend/` | FastAPI-приложение, database models, migrations, services, LangGraph agents и backend tests. |
| `frontend/` | React/Vite SPA, feature pages, shared UI, API clients и frontend tests. |
| `docs/` | Исследовательские, RAG, презентационные и диссертационные материалы. Это supporting documents, а не SDD source of truth. |
| `.kiro/` | Spec-Driven Development documentation для текущей реализованной системы. |
| `deploy/` | Deployment examples, включая nginx configs. |
| `langgraph_graphs/` | Generated/exported LangGraph diagrams, которые раздает backend. |
| `docker-compose.yml` | Production-like local composition из database, Qdrant, Ollama, backend и frontend. |
| `README.md`, `SETUP_GUIDE.md`, `WINDOWS_SETUP.md` | Setup and operational entrypoints. |

## Структура бэкенда

| Путь | Ответственность |
| --- | --- |
| `backend/main.py` | App factory, lifespan, router registration, health endpoints, static mounts. |
| `backend/app/core/` | Settings, database session, security и dependency helpers. |
| `backend/app/models/` | SQLAlchemy persistence models и enums. |
| `backend/app/schemas/` | Pydantic request/response contracts. |
| `backend/app/routers/` | FastAPI route layer. Business rules должны оставаться в services. |
| `backend/app/services/` | Domain services, access checks, persistence orchestration, notifications, RAG/Qdrant и admin services. |
| `backend/app/agents/` | LangGraph graphs, chat subgraph registry, prompts, graph export и agent state types. |
| `backend/alembic/` | Миграции базы данных. |
| `backend/tests/` | Backend unit/integration tests. |

## Структура фронтенда

| Путь | Ответственность |
| --- | --- |
| `frontend/src/App.tsx` | Route tree и top-level guards. |
| `frontend/src/api/` | Typed API clients и Axios auth/refresh behavior. |
| `frontend/src/auth/` | Провайдер аутентификации, hooks, route guards, страницы login/register. |
| `frontend/src/features/` | Feature pages для projects, tasks, chat, notifications, admin и profile. |
| `frontend/src/shared/` | Shared components, hooks и utility libraries. |
| `frontend/src/store/` | Zustand stores. |

## Правила редактирования для агентов

- Не инспектируйте и не документируйте dependency internals в `node_modules`, `.venv`, `venv`, `vendor`, `.next`, `dist`, `build` или `coverage`.
- Предпочитайте targeted searches в `backend`, `frontend`, `app`, `src`, `tests` и `.kiro`.
- Держите router code тонким; route handlers должны делегировать domain work в services.
- Считайте Pydantic schemas публичным API contract, а SQLAlchemy models - persistence contract.
- Обновляйте `.kiro/specs/current-system`, когда меняется behavior, public API, workflow status transitions, agent routing, Qdrant collections или test coverage.
