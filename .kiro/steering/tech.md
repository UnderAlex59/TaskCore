# Технический контекст

## Бэкенд

| Область | Текущее решение |
| --- | --- |
| Среда выполнения | Python `>=3.12,<3.15` |
| Web API | FastAPI, асинхронные routers, Pydantic schemas |
| База данных | PostgreSQL, SQLAlchemy AsyncIO `>=2.0,<2.1`, Alembic migrations `>=1.15,<2` |
| Аутентификация | JWT access token, хэшированные refresh tokens в БД, HTTP-only refresh cookie |
| AI-слой | LangGraph, LangChain, абстракция провайдеров через `LLMRuntimeService` |
| Vector store | Qdrant collections для task knowledge, project questions и proposals |
| Telegram | Webhook-интеграция на `aiogram` и сервис доставки |
| Качество | `ruff`, `mypy`, `pytest`, `pytest-asyncio` |

Точка входа backend находится в `backend/main.py`. Она создает upload-директории, проверяет Qdrant collections, экспортирует LangGraph images, монтирует статические routes для uploads и graph images, а также регистрирует routers.

## Фронтенд

| Область | Текущее решение |
| --- | --- |
| Среда выполнения | React 19, TypeScript, Vite |
| Маршрутизация | `react-router-dom` с protected и admin routes |
| Состояние | Zustand auth/UI stores |
| API | Axios client с добавлением bearer token и refresh queue |
| UI | Tailwind CSS, пользовательские feature components, Markdown и Mermaid rendering |
| Тесты | Vitest, Testing Library, jsdom |

Базовый URL frontend API задается `VITE_API_URL`, значение по умолчанию - `/api`. Цель dev proxy задается `VITE_API_PROXY_TARGET`.

## Инфраструктура

`docker-compose.yml` определяет PostgreSQL, Qdrant, Ollama, migration job, backend, optional Telegram webhook setup и frontend, обслуживаемый через nginx. Compose-путь переопределяет backend service URLs на internal hostnames и собирает frontend с `VITE_API_URL=/api`.

Постоянные runtime-данные:

- PostgreSQL volume `pgdata`.
- Qdrant volume `qdrant_data`.
- Ollama volume `ollama_data`.
- Volume загруженных файлов `uploads`.
- Экспортированные LangGraph images в `langgraph_graphs`.

## Конфигурация

Backend configuration централизована в `backend/app/core/config.py`. Обязательные production-значения включают `DATABASE_URL` и `JWT_SECRET_KEY`. Важные optional-группы:

- Cookies and CORS: `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN`, `ALLOWED_ORIGINS`.
- LLM runtime: `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL`, GigaChat TLS settings, `LLM_SETTINGS_ENCRYPTION_KEY`.
- Embeddings and RAG: `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `RAG_*`.
- Storage and graph export: `UPLOAD_DIR`, `LANGGRAPH_IMAGES_DIR`, `GRAPH_RUN_MONITORING_ENABLED`.
- Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_BOT_USERNAME`.

## Команды качества

Используйте repository Makefile, если shell его поддерживает:

```sh
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

Эквивалентные прямые команды:

```sh
cd backend && ruff check . && ruff format --check . && mypy .
cd backend && pytest
cd frontend && npm run lint && npm run typecheck
cd frontend && npm run test -- --run
cd frontend && npm run build
```

Для docs-only изменений обычно достаточно Markdown-инспекции и targeted `rg` checks, без полного запуска тестов.
