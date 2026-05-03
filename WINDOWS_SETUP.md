# Запуск и конфигурация проекта в Windows

Документ описывает запуск Task Platform MVP в Windows 10/11 через PowerShell, Docker Desktop и локальные dev-серверы.

## Состав проекта

- `backend` - FastAPI-приложение на Python с SQLAlchemy AsyncIO, Alembic, PostgreSQL, Qdrant и LangGraph.
- `frontend` - React 19 + TypeScript + Vite SPA.
- `docker-compose.yml` - production-like контур для локального запуска.
- `langgraph_graphs` - экспортированные PNG/HTML-схемы LangGraph.
- `deploy/nginx` - примеры внешнего nginx proxy.

ИИ-взаимодействие идет через LangGraph-графы. В документации и коде не нужно описывать альтернативные agent-фреймворки как фактический слой проекта.

## Требования

Проверьте наличие:

- Windows 10/11
- Git
- Python `3.12.x`
- Node.js `24.x`
- npm `11.x`
- Docker Desktop с Docker Compose

Проверка в PowerShell:

```powershell
git --version
py -3.12 --version
node --version
npm --version
docker --version
docker compose version
```

## Кодировка PowerShell

Markdown-файлы проекта хранятся в UTF-8. Если русские символы отображаются как нечитаемые последовательности, выставьте UTF-8 для текущей сессии:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

Если инструменты нестабильно работают с путем OneDrive или кириллицей, перенесите репозиторий в короткий ASCII-путь, например:

```text
C:\dev\mvp
```

Это не обязательное требование, но на Windows иногда упрощает работу CLI-инструментов.

## Подготовка PowerShell

Если PowerShell запрещает активацию виртуального окружения:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Вариант 1. Быстрый запуск через Docker Desktop

Этот вариант поднимает весь проект: PostgreSQL, Qdrant, Ollama, миграции, backend и frontend.

### 1. Создать backend `.env`

Из корня проекта:

```powershell
Copy-Item backend\.env.example backend\.env
```

Проверьте в `backend\.env`:

- `JWT_SECRET_KEY` - задайте длинный случайный секрет.
- `COOKIE_SECURE=false` - для локального HTTP.
- `COOKIE_DOMAIN=` - пустое значение для localhost.
- `ALLOWED_ORIGINS` - должен включать локальный frontend.
- `EMBEDDING_PROVIDER` и embedding-модель - если используете RAG.
- `OPENAI_API_KEY` или другие provider-настройки - если нужны внешние LLM.

Для локальных embeddings через Ollama:

```env
EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

### 2. Запустить Compose

```powershell
docker compose up --build -d
```

Compose-сервисы:

- `postgres`
- `qdrant`
- `ollama`
- `ollama-init`
- `migrate`
- `backend`
- `frontend`

### 3. Проверить статус

```powershell
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

PowerShell-проверка:

```powershell
Invoke-RestMethod http://localhost:8080/api/healthz
Invoke-RestMethod http://localhost:8080/api/readyz
```

Если нужен другой внешний порт:

```powershell
$env:FRONTEND_PORT = "80"
docker compose up --build -d
```

### 4. Остановка

```powershell
docker compose down
```

Полный сброс данных:

```powershell
docker compose down -v
```

`-v` удаляет volumes PostgreSQL, Qdrant, Ollama и uploads.

## Вариант 2. Dev-запуск в Windows

Этот вариант удобен для разработки: PostgreSQL и Qdrant работают в Docker, backend и frontend запускаются локально.

### 1. Создать `.env` файлы

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

### 2. Рекомендуемый `backend\.env`

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

### 3. `frontend\.env`

```env
VITE_API_URL=/api
VITE_API_PROXY_TARGET=http://localhost:8000
```

При такой настройке Vite проксирует HTTP и WebSocket `/api/*` на backend.

### 4. Поднять PostgreSQL и Qdrant

```powershell
docker compose up postgres qdrant -d
docker compose ps
```

Если используете Ollama embeddings:

```powershell
docker compose up ollama ollama-init -d
```

### 5. Запустить backend

Откройте отдельное окно PowerShell:

```powershell
Set-Location backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn main:app --reload
```

Backend:

- `http://localhost:8000`
- `http://localhost:8000/docs`
- `http://localhost:8000/healthz`
- `http://localhost:8000/readyz`

Проверка:

```powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
```

### 6. Запустить frontend

Откройте второе окно PowerShell:

```powershell
Set-Location frontend
npm install
npm run dev
```

Frontend:

- `http://localhost:5173`

## Проверки качества

Из корня проекта:

```powershell
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

Если `make` недоступен, выполните напрямую.

Backend:

```powershell
Set-Location backend
ruff check .
ruff format --check .
mypy .
pytest
```

Frontend:

```powershell
Set-Location frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

## Частые проблемы

- `readyz` возвращает 503: backend не подключился к PostgreSQL; проверьте `DATABASE_URL` и `docker compose ps`.
- `ollama-init` завершается ошибкой: при `EMBEDDING_PROVIDER=ollama` не задан `OLLAMA_EMBEDDING_MODEL`.
- Frontend получает 401 после старта: проверьте cookie-настройки и `COOKIE_SECURE=false` для localhost без HTTPS.
- CORS-ошибка: добавьте frontend origin в `ALLOWED_ORIGINS`.
- Русский текст отображается неверно: включите UTF-8 в PowerShell и убедитесь, что файл сохранен как UTF-8.
- WebSocket не подключается в dev: проверьте `VITE_API_URL=/api` и `VITE_API_PROXY_TARGET=http://localhost:8000`.
