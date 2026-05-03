# Setup Guide

Этот документ описывает актуальный запуск Task Platform MVP: локальную разработку, production-like контур через Docker Compose, переменные окружения, проверки готовности и команды сопровождения.

## Требования

Для локальной разработки:

- Python `3.12.x`
- Node.js `24.x`
- npm `11.x`
- Docker и Docker Compose
- Git

Backend поддерживает Python `>=3.12,<3.15`, но проектные команды и инструкции ориентированы на Python 3.12.

## Сервисы Docker Compose

`docker-compose.yml` поднимает полный контур:

- `postgres` - PostgreSQL 16, база `taskplatform`, пользователь `app_user`.
- `qdrant` - векторное хранилище для RAG.
- `ollama` - локальный runtime моделей.
- `ollama-init` - подтягивает `OLLAMA_EMBEDDING_MODEL`, если `EMBEDDING_PROVIDER=ollama`.
- `migrate` - выполняет `alembic upgrade head`.
- `backend` - FastAPI-приложение.
- `frontend` - nginx со статикой React SPA и proxy `/api` на backend.

Миграции вынесены в отдельный сервис. Backend стартует после успешного завершения `migrate`.

## Переменные окружения backend

Шаблон: `backend/.env.example`.

Обязательные и важные параметры:

- `DATABASE_URL` - DSN PostgreSQL для SQLAlchemy AsyncIO.
- `JWT_SECRET_KEY` - длинный случайный секрет подписи JWT.
- `ALLOWED_ORIGINS` - JSON-массив или comma-separated список разрешенных origins.
- `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN` - настройки refresh-cookie.
- `QDRANT_URL`, `QDRANT_API_KEY` - подключение к Qdrant.
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL` - базовые provider-настройки.
- `GIGACHAT_VERIFY_SSL`, `GIGACHAT_CA_BUNDLE_FILE`, `GIGACHAT_CA_BUNDLE_PEM` - TLS-настройки GigaChat.
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` - embeddings для RAG.
- `LLM_SETTINGS_ENCRYPTION_KEY` - ключ для чувствительных настроек LLM runtime.
- `CHAT_AGENT_MODULES` - список внешних модулей с LangGraph agent subgraphs.
- `RAG_CHUNK_TARGET_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS` - параметры chunking.
- `RAG_ATTACHMENT_MAX_TEXT_CHARS` - лимит текста вложения для RAG.
- `RAG_VISION_ENABLED`, `RAG_VISION_MAX_IMAGE_BYTES` - Vision-контур вложений.
- `UPLOAD_DIR` - каталог загруженных файлов.
- `LANGGRAPH_IMAGES_DIR` - каталог PNG/HTML-экспорта графов.

Пример локального dev-конфига:

```env
DATABASE_URL=postgresql+asyncpg://app_user:app_pass@localhost:5432/taskplatform
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
JWT_SECRET_KEY=replace_with_a_long_random_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=false
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=
ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
CHAT_AGENT_MODULES=[]
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
OPENAI_API_KEY=
OPENAI_BASE_URL=
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_MODEL=
EMBEDDING_DIMENSION=
LLM_SETTINGS_ENCRYPTION_KEY=
RAG_CHUNK_TARGET_TOKENS=450
RAG_CHUNK_OVERLAP_TOKENS=50
RAG_ATTACHMENT_MAX_TEXT_CHARS=20000
RAG_VISION_ENABLED=true
RAG_VISION_MAX_IMAGE_BYTES=5242880
UPLOAD_DIR=./uploads
LANGGRAPH_IMAGES_DIR=../langgraph_graphs
```

## Переменные окружения frontend

Шаблон: `frontend/.env.example`.

```env
VITE_API_URL=/api
VITE_API_PROXY_TARGET=http://localhost:8000
```

В production-like Compose frontend собирается с `VITE_API_URL=/api`. Runtime proxy внутри nginx-контейнера направляет запросы на `BACKEND_UPSTREAM=backend:8000`.

## Быстрый запуск через Docker Compose

1. Создайте backend-конфиг:

```bash
cp backend/.env.example backend/.env
```

2. Проверьте минимум:

- `JWT_SECRET_KEY` не должен оставаться примером.
- Для OpenAI/OpenRouter/GigaChat укажите ключи в админке или env в зависимости от сценария.
- Для локальных embeddings через Ollama задайте `EMBEDDING_PROVIDER=ollama` и `OLLAMA_EMBEDDING_MODEL`.

3. Запустите контур:

```bash
docker compose up --build -d
```

4. Проверьте сервисы:

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f backend
docker compose logs -f frontend
```

Адреса:

- UI: `http://localhost:8080`
- frontend health: `http://localhost:8080/healthz`
- backend health через proxy: `http://localhost:8080/api/healthz`
- backend readiness через proxy: `http://localhost:8080/api/readyz`

Другой порт frontend:

```bash
FRONTEND_PORT=80 docker compose up --build -d
```

## Локальный dev-запуск

Этот режим удобен для разработки: backend и frontend запускаются с hot reload, а PostgreSQL/Qdrant остаются в Docker.

### 1. Поднять инфраструктуру

```bash
docker compose up postgres qdrant -d
```

Если нужны локальные embeddings через Ollama, также поднимите:

```bash
docker compose up ollama ollama-init -d
```

### 2. Запустить backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
alembic upgrade head
uvicorn main:app --reload
```

Backend:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- health: `http://localhost:8000/healthz`
- readiness: `http://localhost:8000/readyz`

### 3. Запустить frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend dev server:

- UI: `http://localhost:5173`
- API proxy: `/api -> http://localhost:8000`
- WebSocket proxy включен для `/api`.

## Проверки качества

Из корня:

```bash
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

Прямые команды:

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

## Команды сопровождения

```bash
make docker-build
make compose-up
make compose-down
```

Docker Compose:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f qdrant
docker compose down
docker compose down -v
```

`docker compose down -v` удаляет volumes PostgreSQL, Qdrant, Ollama и uploads. Используйте эту команду только если нужен полный сброс локальных данных.

## Эксплуатационные замечания

- Backend можно масштабировать горизонтально только при общем PostgreSQL, общем Qdrant и общем файловом хранилище uploads.
- В текущем Compose uploads хранятся в Docker volume, а LangGraph-схемы монтируются в `./langgraph_graphs`.
- Refresh token rotation хранится в PostgreSQL, поэтому процесс backend остается stateless.
- Frontend stateless: вся длительная сессия поддерживается backend refresh-cookie.
- Qdrant должен быть доступен до старта backend, потому что на lifespan выполняется `ensure_collections`.
- Если `EMBEDDING_PROVIDER=ollama`, `ollama-init` требует непустой `OLLAMA_EMBEDDING_MODEL`.
