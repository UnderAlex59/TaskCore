# Task Platform MVP

Интеллектуальная платформа управления задачами и требованиями для Agile-команд. Проект объединяет трекер требований, командный чат, автоматическую проверку качества постановок, RAG-память проекта и администрируемый слой LLM-агентов.

ИИ-взаимодействие в проекте идет через LangGraph. Агентные сценарии оформлены как графы и subgraphs: валидация требований, маршрутизация чата, ответы на вопросы, обработка предложений изменений, RAG-индексация, проверка провайдеров и Vision-сценарии.

## Публичный быстрый запуск

Склонируйте репозиторий и подготовьте backend-конфиг:

```bash
git clone <repository-url>
cd mvp
cp backend/.env.example backend/.env
```

В `backend/.env` задайте:

- `JWT_SECRET_KEY` - длинный случайный секрет для JWT;
- `LLM_SETTINGS_ENCRYPTION_KEY` - отдельный секрет для шифрования LLM-настроек;
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` или `OLLAMA_EMBEDDING_MODEL` - настройки embeddings;
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `QDRANT_API_KEY` и другие provider-ключи, если они нужны выбранному сценарию.

Для локальной frontend-разработки дополнительно создайте `frontend/.env`:

```bash
cp frontend/.env.example frontend/.env
```

Для Docker Compose production-like запуска `frontend/.env` не требуется: frontend собирается с `VITE_API_URL=/api`.

Запустите контур:

```bash
docker compose up --build -d
```

Если используется legacy Compose, эквивалентная команда:

```bash
docker-compose up --build -d
```

После запуска:

- UI: `http://localhost:8080`
- frontend health: `http://localhost:8080/healthz`
- backend health через proxy: `http://localhost:8080/api/healthz`
- backend readiness через proxy: `http://localhost:8080/api/readyz`

## Что реализовано

- Регистрация, вход, refresh-токены в `httpOnly` cookie, список активных сессий и выход из системы.
- Роли пользователей: `ADMIN`, `ANALYST`, `DEVELOPER`, `TESTER`, `MANAGER`.
- Проекты, участники проектов и кастомные правила проверки требований.
- Задачи с жизненным циклом `draft -> validating -> needs_rework / awaiting_approval -> ready_for_dev -> in_progress -> ready_for_testing -> testing -> done`.
- Назначение автора, аналитика, проверяющего аналитика, разработчика и тестировщика.
- Справочник тегов задач и AI-подсказка тегов.
- Вложения к задачам, хранение файлов и статическая раздача через backend.
- Валидация требований через LangGraph: базовые правила, правила проекта, контекстные вопросы и итоговый verdict.
- Командный чат задачи с HTTP API и WebSocket-обновлениями.
- QA Agent, ChangeTracker Agent и Manager Agent как LangGraph subgraphs.
- Предложения изменений со статусами `new`, `accepted`, `rejected`.
- RAG-контур на Qdrant для задач, вопросов валидации и предложений изменений.
- Админские разделы для LLM-провайдеров, agent overrides, prompt configs, Vision test, Qdrant, мониторинга, audit feed, пользователей, тегов и вопросов валидации.
- Экспорт PNG/HTML-схем LangGraph в `langgraph_graphs`.
- Docker Compose production-like контур с PostgreSQL, Qdrant, Ollama, миграциями, backend и frontend.
- Проверки качества через Makefile, pytest, ruff, mypy, ESLint, TypeScript, Vitest и Vite build.

## Стек

| Слой | Технологии |
| --- | --- |
| Backend | Python 3.12+, FastAPI, Uvicorn, SQLAlchemy AsyncIO, Alembic, Pydantic v2 |
| Data | PostgreSQL, Qdrant, локальное файловое хранилище uploads |
| AI/RAG | LangGraph, LangChain, OpenAI, Ollama, OpenRouter, GigaChat, OpenAI-compatible API |
| Frontend | React 19, TypeScript, Vite, React Router, Zustand, Axios, Tailwind CSS |
| Infra | Docker Compose, nginx во frontend-контейнере, health/readiness endpoints |
| Quality | pytest, pytest-asyncio, ruff, mypy, ESLint, Prettier, Vitest, Testing Library |

## Требования

- Python `3.12.x`. Backend package поддерживает `>=3.12,<3.15`, но проектные команды и CI ориентированы на Python 3.12.
- Node.js `24.x` и npm `11.x`.
- Docker и Docker Compose.
- Для Windows-разработки: PowerShell 7 или Windows PowerShell с UTF-8 output encoding.

## Структура репозитория

```text
.
|-- backend/             # FastAPI API, модели, сервисы, LangGraph-графы, Alembic, тесты
|-- frontend/            # React/Vite SPA, typed API clients, рабочие и админские экраны
|-- deploy/nginx/        # примеры nginx-конфигураций для внешнего reverse proxy
|-- .kiro/               # текущая SDD/agent-спецификация реализованной системы
|-- langgraph_graphs/    # локальные экспортированные PNG/HTML-схемы LangGraph, ignored
|-- docker-compose.yml   # локальный production-like контур
|-- Makefile             # команды проверок, сборки и compose-запуска
|-- architecture-spec.md # актуальная техническая спецификация Markdown
|-- LICENSE              # лицензия MIT
`-- README.md
```

Подробности по разделам:

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)
- [backend/app/agents/README.md](backend/app/agents/README.md)
- [architecture-spec.md](architecture-spec.md)
- [.kiro/specs/current-system/design.md](.kiro/specs/current-system/design.md)
- [.kiro/specs/current-system/api-contract.md](.kiro/specs/current-system/api-contract.md)
- [LICENSE](LICENSE)

## Быстрый запуск через Docker Compose

Подготовьте `backend/.env`. За основу используйте `backend/.env.example`, как описано в разделе публичного быстрого запуска.

```bash
docker compose up --build -d
```

Compose поднимает:

- `postgres` - PostgreSQL 16;
- `qdrant` - векторное хранилище;
- `ollama` - локальный runtime для моделей;
- `ollama-init` - загрузка embedding-модели, если `EMBEDDING_PROVIDER=ollama`;
- `migrate` - `alembic upgrade head`;
- `backend` - FastAPI API;
- `frontend` - nginx со статикой SPA и proxy на backend.

После запуска:

- UI: `http://localhost:8080`
- frontend health: `http://localhost:8080/healthz`
- backend health через proxy: `http://localhost:8080/api/healthz`
- backend readiness через proxy: `http://localhost:8080/api/readyz`

Порт frontend меняется переменной `FRONTEND_PORT`, например `FRONTEND_PORT=80 docker compose up --build -d`.
В PowerShell используйте `$env:FRONTEND_PORT = "80"; docker compose up --build -d`.

Диагностика:

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f backend
docker compose logs -f frontend
```

## Локальная разработка

Инфраструктура:

```bash
docker compose up postgres qdrant -d
```

Если нужны локальные embeddings через Ollama:

```bash
docker compose up ollama ollama-init -d
```

Backend:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# bash/zsh: source .venv/bin/activate
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

Для Vite dev server используется proxy `/api` на backend. По умолчанию `VITE_API_PROXY_TARGET=http://localhost:8000`.

## Проверки

```bash
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

Если `make` недоступен, запускайте команды напрямую в `backend` и `frontend`:

```bash
cd backend
ruff check .
ruff format --check .
mypy .
pytest

cd frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

## Основные переменные окружения

Backend:

- `DATABASE_URL` - DSN PostgreSQL для SQLAlchemy AsyncIO.
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE` - параметры пула соединений.
- `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` - параметры JWT.
- `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN` - параметры refresh-cookie.
- `ALLOWED_ORIGINS` - CORS origins.
- `CHAT_AGENT_MODULES` - внешние Python-модули с LangGraph agent subgraphs.
- `QDRANT_URL`, `QDRANT_API_KEY` - подключение к Qdrant.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL` - настройки LLM-провайдеров.
- `GIGACHAT_VERIFY_SSL`, `GIGACHAT_CA_BUNDLE_FILE`, `GIGACHAT_CA_BUNDLE_PEM` - параметры GigaChat TLS.
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` - embeddings для RAG.
- `LLM_SETTINGS_ENCRYPTION_KEY` - ключ шифрования сохраняемых LLM-настроек.
- `RAG_CHUNK_TARGET_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS`, `RAG_CHUNK_MAX_CHARS`, `RAG_ATTACHMENT_MAX_TEXT_CHARS` - параметры RAG-подготовки.
- `RAG_VISION_ENABLED`, `RAG_VISION_MAX_IMAGE_BYTES` - включение и ограничения Vision-обработки вложений.
- `UPLOAD_DIR` - каталог файловых вложений.
- `LANGGRAPH_IMAGES_DIR` - каталог экспорта схем графов.

Frontend:

- `VITE_API_URL` - базовый URL API, в production обычно `/api`.
- `VITE_API_PROXY_TARGET` - цель Vite dev proxy.

## AI, LangGraph и RAG

Backend не вызывает LLM-провайдеры напрямую из роутеров. Агентные сценарии идут через LangGraph-графы, а модели вызываются через `LLMRuntimeService`. Это дает единый слой для OpenAI, Ollama, OpenRouter, GigaChat и OpenAI-compatible API.

Основные графы:

- `validation_graph` - проверка требований.
- `rag_pipeline` - подготовка индексируемого контекста.
- `chat_graph` - маршрутизация сообщений в agent subgraphs.
- `qa_agent_graph` - ответы на вопросы по задаче и контексту.
- `change_tracker_agent_graph` - извлечение и дедупликация предложений изменений.
- `manager_agent_graph` - fallback и объяснение маршрутизации.
- `task_tag_suggestion_graph` - подсказки тегов.
- `provider_test_graph`, `vision_test_graph`, `attachment_vision_graph` - проверка LLM/Vision-сценариев.

Qdrant-коллекции:

- `task_knowledge` - контекст задач, результаты валидации и данные для поиска похожих задач.
- `project_questions` - банк вопросов для повторного использования валидацией.
- `task_proposals` - предложения изменений и поиск дублей.

## Документация и кодировка

Корневой `README.md` содержит актуальные инструкции запуска и сопровождения. `architecture-spec.md` и `.kiro/specs/current-system` описывают текущую реализованную архитектуру и API-контракты.

Markdown-файлы хранятся в UTF-8. Если PowerShell показывает русские символы как нечитаемые последовательности, проверьте кодировку консоли:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## Лицензия

Проект распространяется по лицензии MIT. См. [LICENSE](LICENSE).
