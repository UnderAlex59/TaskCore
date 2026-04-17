# Инструкция по запуску и конфигурации проекта в Windows

## 1. Что находится в репозитории

Проект состоит из трёх основных частей:

- `backend` - FastAPI-приложение на Python 3.12 с Alembic и PostgreSQL.
- `frontend` - React 19 + Vite + TypeScript.
- `docker-compose.yml` - локальный production-like запуск через Docker Desktop.

Дополнительно есть Helm chart в `deploy/helm/task-platform` для Kubernetes.

## 2. Поддерживаемые сценарии запуска

Для Windows есть два основных сценария:

1. `docker compose` - самый простой способ быстро поднять проект целиком.
2. Ручной dev-запуск - backend и frontend запускаются отдельно, а PostgreSQL/Qdrant поднимаются через Docker.

Если нужна локальная разработка, обычно удобнее второй вариант.
Если нужно быстро проверить проект целиком, удобнее первый.

## 3. Требования к окружению

Минимально нужно установить:

- Windows 10/11
- Git
- Python `3.12.x`
- Node.js `24.x`
- npm `11.x`
- Docker Desktop с включённым Docker Compose

Опционально, если нужен Kubernetes-сценарий:

- `kubectl`
- `helm 3.x`
- ingress controller
- `metrics-server`

Проверка установленных версий в PowerShell:

```powershell
git --version
python --version
py -3.12 --version
node --version
npm --version
docker --version
docker compose version
```

## 4. Подготовка PowerShell

Если PowerShell не даёт активировать виртуальное окружение, один раз выполните:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Если проект лежит в OneDrive или в пути с кириллицей и какие-то инструменты начинают вести себя нестабильно, перенесите репозиторий в короткий ASCII-путь, например:

```text
C:\dev\mvp
```

Это не обязательное требование, но на Windows такой перенос иногда избавляет от проблем с путями.

## 5. Быстрый запуск через Docker Desktop

### 5.1. Подготовить backend-конфиг

Из корня репозитория:

```powershell
Copy-Item backend\.env.example backend\.env
```

После этого откройте `backend\.env` и как минимум измените:

- `JWT_SECRET_KEY` - задайте длинный случайный секрет.
- `OPENAI_API_KEY` - если хотите использовать OpenAI.
- `COOKIE_SECURE=false` - для локального HTTP.
- `COOKIE_DOMAIN=` - оставить пустым для localhost.

Для `docker compose` файл `frontend\.env` не обязателен: frontend собирается с `VITE_API_URL=/api`.

### 5.2. Запуск

```powershell
docker compose up --build -d
```

По умолчанию frontend будет доступен на `http://localhost:8080`.
Если хотите использовать другой внешний порт, создайте в корне проекта файл `.env` с переменной `FRONTEND_PORT`, например `FRONTEND_PORT=80`.

Проверка статуса:

```powershell
docker compose ps
docker compose logs -f migrate
docker compose logs -f backend
docker compose logs -f frontend
```

### 5.3. Что должно открываться

- UI: `http://localhost:8080`
- health frontend/nginx: `http://localhost:8080/healthz`
- health backend через proxy: `http://localhost:8080/api/healthz`
- readiness backend через proxy: `http://localhost:8080/api/readyz`

Проверка из PowerShell:

```powershell
Invoke-RestMethod http://localhost:8080/api/healthz
Invoke-RestMethod http://localhost:8080/api/readyz
```

### 5.4. Остановка

```powershell
docker compose down
```

Полная остановка со сбросом volumes:

```powershell
docker compose down -v
```

### 5.5. Важные замечания для Docker-сценария

- Во внешнюю сеть публикуется только frontend на порту `8080` по умолчанию.
- Backend снаружи доступен через префикс `/api`.
- При необходимости задайте внешний порт через `FRONTEND_PORT`, например `FRONTEND_PORT=80`.

## 6. Ручной запуск для локальной разработки в Windows

Этот вариант удобнее для разработки, потому что frontend и backend работают в dev-режиме с hot reload.

### 6.1. Подготовить `.env` файлы

Из корня репозитория:

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env
```

### 6.2. Рекомендуемый `backend\.env` для Windows dev

Ниже рабочий пример для локальной разработки:

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
LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4o-mini
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.2
EMBEDDING_MODEL=text-embedding-3-small
CHAT_AGENT_LLM_OVERRIDES={}
UPLOAD_DIR=./uploads
```

Пояснения:

- `UPLOAD_DIR=./uploads` удобно для Windows dev-режима. Папка будет создана автоматически внутри `backend`.
- `COOKIE_SECURE=false` обязательно для локального HTTP без HTTPS.
- `ALLOWED_ORIGINS` должен быть корректной JSON-строкой.

### 6.3. `frontend\.env`

Для ручного dev-запуска frontend должен ходить напрямую в backend:

```env
VITE_API_URL=http://localhost:8000
```

### 6.4. Поднять PostgreSQL и Qdrant

Из корня репозитория:

```powershell
docker compose up postgres qdrant -d
```

Проверка:

```powershell
docker compose ps
```

### 6.5. Запуск backend

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

Backend будет доступен по адресам:

- `http://localhost:8000`
- `http://localhost:8000/docs`
- `http://localhost:8000/healthz`
- `http://localhost:8000/readyz`

Проверка:

```powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
```

### 6.6. Запуск frontend

Откройте ещё одно окно PowerShell:

```powershell
Set-Location frontend
npm install
npm run dev
```

Frontend будет доступен по адресу:

- `http://localhost:5173`

### 6.7. Первый вход в систему

После запуска откройте frontend и зарегистрируйте пользователя.

Важно: первый зарегистрированный пользователь автоматически получает роль `ADMIN`.

Отдельный seed-скрипт для первичного администратора не нужен.

## 7. Конфигурация: что за что отвечает

### 7.1. Обязательные переменные backend

- `DATABASE_URL` - строка подключения к PostgreSQL.
- `JWT_SECRET_KEY` - секрет для access/refresh токенов.

Без этих двух переменных backend не стартует.

### 7.2. Настройки браузера и cookie

- `ALLOWED_ORIGINS` - список разрешённых origin'ов для CORS. Нужен JSON-массив или список через запятую.
- `COOKIE_SECURE` - `false` для localhost без HTTPS, `true` для production с HTTPS.
- `COOKIE_SAMESITE` - обычно `lax`.
- `COOKIE_DOMAIN` - пусто для localhost, домен в production.

### 7.3. Настройки LLM и AI

- `LLM_PROVIDER` - `openai` или `ollama`.
- `OPENAI_API_KEY` - ключ OpenAI.
- `OPENAI_BASE_URL` - опционально, если используется OpenAI-compatible endpoint.
- `OPENAI_MODEL` - модель по умолчанию для OpenAI.
- `OLLAMA_BASE_URL` - адрес локального Ollama, обычно `http://localhost:11434`.
- `OLLAMA_MODEL` - модель Ollama по умолчанию.
- `LLM_MODEL` - общий fallback-модельный идентификатор.
- `LLM_TEMPERATURE` - температура генерации.
- `EMBEDDING_MODEL` - модель эмбеддингов.
- `CHAT_AGENT_MODULES` - JSON-массив дополнительных модулей с агентами.
- `CHAT_AGENT_LLM_OVERRIDES` - JSON-объект с переопределениями моделей по агентам.

Пример `CHAT_AGENT_LLM_OVERRIDES` в одну строку:

```env
CHAT_AGENT_LLM_OVERRIDES={"qa":{"provider":"ollama","model":"llama3.1","base_url":"http://localhost:11434","temperature":0.1}}
```

### 7.4. Настройки Qdrant

- `QDRANT_URL` - URL сервиса Qdrant.
- `QDRANT_API_KEY` - ключ, если Qdrant защищён.

### 7.5. Настройки uploads и пула БД

- `UPLOAD_DIR` - папка для файлов.
- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT`
- `DB_POOL_RECYCLE`

## 8. Важные правила для `.env` в Windows

- Файлы `.env` должны быть сохранены в `UTF-8`.
- `ALLOWED_ORIGINS`, `CHAT_AGENT_MODULES`, `CHAT_AGENT_LLM_OVERRIDES` лучше писать как валидный JSON в одну строку.
- Для путей на Windows безопаснее использовать `./uploads` или путь со слэшами вперёд, например `C:/task-platform/uploads`.

## 9. Команды проверки и тестирования в Windows

### 9.1. Backend

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m ruff check .
python -m ruff format --check .
python -m mypy .
python -m pytest
```

### 9.2. Frontend

```powershell
Set-Location frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

### 9.3. Тестовая база данных для backend-тестов

Некоторые backend-тесты требуют отдельную БД `taskplatform_test`.

Если такой базы нет, создайте её:

```powershell
docker compose up postgres -d
docker compose exec postgres psql -U app_user -d postgres -c "CREATE DATABASE taskplatform_test;"
```

При необходимости можно переопределить URL тестовой БД переменной `TEST_DATABASE_URL`.

## 10. Аналоги команд из Makefile для PowerShell

В репозитории есть `Makefile`, но он использует `/bin/sh`, поэтому в обычном PowerShell его лучше не считать основным способом запуска.

Прямые аналоги:

- `make check`

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
python -m ruff check .
python -m ruff format --check .
python -m mypy .
python -m pytest

Set-Location ..\frontend
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

- `make docker-build`

```powershell
docker build -t task-platform-backend:local backend
docker build -t task-platform-frontend:local frontend
```

## 11. Kubernetes/Helm из Windows

Если нужно развёртывание в Kubernetes из Windows, команды выполняются из PowerShell так же, как и в Linux.

### 11.1. Подготовить values

Скопируйте пример:

```powershell
Copy-Item deploy\helm\task-platform\values.production.example.yaml deploy\helm\task-platform\values.production.yaml
```

Минимально заполните:

- `backend.image.repository`
- `backend.image.tag`
- `frontend.image.repository`
- `frontend.image.tag`
- `backend.secretEnv.databaseUrl`
- `backend.secretEnv.jwtSecretKey`
- `backend.secretEnv.openaiApiKey`
- `backend.env.allowedOrigins`
- `backend.env.cookieDomain`
- `ingress.enabled`
- `ingress.hosts`
- `ingress.tls`
- `uploads.persistence`

### 11.2. Установка chart

```powershell
helm upgrade --install task-platform deploy/helm/task-platform `
  -n task-platform `
  --create-namespace `
  -f deploy/helm/task-platform/values.production.yaml
```

### 11.3. Проверка после установки

```powershell
kubectl get pods -n task-platform
kubectl get ingress -n task-platform
kubectl get hpa -n task-platform
kubectl logs job/task-platform-backend-migrate -n task-platform
```

## 12. Типовые проблемы и решения

### Проблема: `Activate.ps1` не запускается

Решение:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Проблема: `readyz` возвращает `503`

Проверьте:

- поднят ли PostgreSQL;
- правильный ли `DATABASE_URL`;
- были ли применены миграции `python -m alembic upgrade head`.

### Проблема: frontend не открывается на `http://localhost`

Проверьте:

- не занят ли выбранный внешний порт;
- поднялся ли контейнер `frontend`;
- что показывает `docker compose logs -f frontend`.

### Проблема: AI-функции не работают

Проверьте:

- заполнен ли `OPENAI_API_KEY` при `LLM_PROVIDER=openai`;
- запущен ли Ollama при `LLM_PROVIDER=ollama`;
- доступен ли `QDRANT_URL`.

### Проблема: CORS или cookie не работают локально

Для локальной разработки обычно нужны такие значения:

```env
COOKIE_SECURE=false
COOKIE_DOMAIN=
ALLOWED_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

## 13. Рекомендуемый порядок запуска

Если нужна разработка:

1. Скопировать `.env` файлы.
2. Поднять `postgres` и `qdrant`.
3. Создать `backend\.venv` и установить backend-зависимости.
4. Применить миграции.
5. Запустить backend.
6. Запустить frontend.
7. Зарегистрировать первого пользователя.

Если нужна быстрая проверка сборки:

1. Скопировать `backend\.env.example` в `backend\.env`.
2. Заполнить `JWT_SECRET_KEY`.
3. Выполнить `docker compose up --build -d`.
4. Открыть `http://localhost:8080`.
