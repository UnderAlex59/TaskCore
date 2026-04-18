# Setup Guide

Ниже описан актуальный порядок запуска проекта после подготовки к Kubernetes.

## 1. Что изменилось

- backend больше не запускает `alembic upgrade head` из основного `CMD`;
- в Compose миграции вынесены в отдельный сервис `migrate`;
- в Kubernetes миграции запускаются отдельным Helm hook `Job`;
- backend получил `readyz` для проверок readiness;
- frontend nginx теперь настраивается через `BACKEND_UPSTREAM`;
- для k8s добавлен Helm chart с HPA, PDB, ingress и PVC.

## 2. Требования

Для локальной разработки:

- Python `3.12.x`
- Node.js `24.x`
- npm `11.x`
- Docker + Docker Compose

Для Kubernetes:

- Kubernetes `1.27+`
- Helm `3.x`
- ingress controller
- metrics-server для работы HPA
- storage class с `ReadWriteMany` или внешний storage для загрузок

## 3. Переменные окружения backend

Шаблон: `backend/.env.example`

Ключевые переменные:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `ALLOWED_ORIGINS`
- `COOKIE_SECURE`
- `COOKIE_DOMAIN`
- `UPLOAD_DIR`

Параметры пула БД для нагрузки:

- `DB_POOL_SIZE`
- `DB_MAX_OVERFLOW`
- `DB_POOL_TIMEOUT`
- `DB_POOL_RECYCLE`

Пример production-конфига:

```env
DATABASE_URL=postgresql+asyncpg://app_user:strong_password@postgres:5432/taskplatform
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
JWT_SECRET_KEY=generate_a_long_random_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
COOKIE_DOMAIN=app.example.com
ALLOWED_ORIGINS=["https://app.example.com"]
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
LLM_PROVIDER=openai
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://ollama:11434
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
UPLOAD_DIR=/var/lib/task-platform/uploads
```

## 4. Переменные окружения frontend

Шаблон: `frontend/.env.example`

Для локальной разработки:

```env
VITE_API_URL=/api
VITE_API_PROXY_TARGET=http://localhost:8000
```

В этом режиме `vite dev server` проксирует и обычные HTTP-запросы, и WebSocket-подключения `/api/*` на backend.

Для production-сборки frontend обычно собирается с `VITE_API_URL=/api`.

Runtime proxy внутри контейнера управляется переменной:

```env
BACKEND_UPSTREAM=backend:8000
```

В Kubernetes это значение автоматически задаётся chart'ом.

## 5. Локальный ручной запуск

### 5.1. Инфраструктура

```bash
docker compose up postgres qdrant -d
```

### 5.2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
alembic upgrade head
uvicorn main:app --reload
```

Backend будет доступен по адресам:

- `http://localhost:8000`
- `http://localhost:8000/docs`
- `http://localhost:8000/healthz`
- `http://localhost:8000/readyz`

### 5.3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend будет доступен по адресу `http://localhost:5173`.

## 6. Production-like запуск через Docker Compose

```bash
docker compose up --build -d
```

По умолчанию frontend публикуется на `http://localhost:8080`.
Если нужен другой порт, задайте переменную окружения `FRONTEND_PORT`, например `FRONTEND_PORT=80`.

Проверка:

```bash
docker compose ps
docker compose logs -f migrate
docker compose logs -f backend
docker compose logs -f frontend
```

Остановка:

```bash
docker compose down
```

Остановка со сбросом данных:

```bash
docker compose down -v
```

## 7. Kubernetes через Helm

### 7.1. Подготовка values

Возьмите за основу:

- `deploy/helm/task-platform/values.yaml`
- `deploy/helm/task-platform/values.production.example.yaml`

Минимально проверьте и заполните:

- `backend.image.repository`
- `backend.image.tag`
- `frontend.image.repository`
- `frontend.image.tag`
- `backend.secretEnv.databaseUrl`
- `backend.secretEnv.jwtSecretKey`
- `backend.env.allowedOrigins`
- `backend.env.cookieDomain`
- `ingress.enabled`
- `ingress.hosts`
- `ingress.tls`
- `uploads.persistence`

### 7.2. Установка

```bash
helm upgrade --install task-platform deploy/helm/task-platform \
  -n task-platform \
  --create-namespace \
  -f deploy/helm/task-platform/values.production.yaml
```

### 7.3. Что создаёт chart

- `Deployment` и `Service` для backend;
- `Deployment` и `Service` для frontend;
- `Job` для миграций с hook `pre-install,pre-upgrade`;
- `HorizontalPodAutoscaler` для backend и frontend;
- `PodDisruptionBudget` для backend и frontend;
- `PersistentVolumeClaim` под загрузки;
- `Ingress` с отдельными маршрутами `/api` и `/`.

### 7.4. Проверка после установки

```bash
kubectl get pods -n task-platform
kubectl get ingress -n task-platform
kubectl logs job/task-platform-backend-migrate -n task-platform
kubectl get hpa -n task-platform
```

Readiness backend:

```bash
kubectl port-forward svc/task-platform-backend 8000:8000 -n task-platform
curl http://127.0.0.1:8000/readyz
```

## 8. Рекомендации по масштабированию

- backend масштабируется горизонтально через HPA, потому что состояние хранится в PostgreSQL;
- refresh token rotation хранится в БД, а не в памяти pod'а;
- frontend полностью stateless;
- загрузки нельзя хранить на `emptyDir`, если вы реально поднимаете несколько backend pod'ов;
- для production лучше вынести PostgreSQL, Qdrant и файлы во внешние managed сервисы.

## 9. Команды сопровождения

```bash
make check
make docker-build
make helm-lint
make helm-template
make helm-install HELM_VALUES="-f deploy/helm/task-platform/values.production.yaml"
```

Если `make` недоступен, используйте те же команды напрямую.
