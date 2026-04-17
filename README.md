# Task Platform MVP

Интеллектуальная платформа управления требованиями и задачами на стеке `FastAPI + PostgreSQL + React`.

В репозитории теперь есть два поддерживаемых operational path:

- `docker-compose.yml` для локального production-like запуска;
- `deploy/helm/task-platform` для развёртывания и масштабирования в Kubernetes.

## Что уже подготовлено для k8s

- backend и frontend собираются в отдельные production-образы;
- миграции больше не выполняются из основного процесса backend;
- для backend добавлен `readyz`, который проверяет доступность БД;
- frontend конфигурируется через `BACKEND_UPSTREAM`, а не через жёстко зашитое имя контейнера;
- Helm chart включает `Deployment`, `Service`, `Ingress`, `HPA`, `PDB`, migration `Job` и PVC для загрузок;
- CI валидирует Helm chart и сборку Docker-образов.

## Быстрый старт через Docker Compose

```bash
docker compose up --build -d
```

После запуска:

- frontend: `http://localhost:8080`
- backend health: `http://localhost:8080/healthz`
- backend readiness: `http://localhost:8080/readyz`

При необходимости хостовый порт можно переопределить через переменную окружения `FRONTEND_PORT`, например `FRONTEND_PORT=80`.

Compose-сценарий теперь состоит из:

- `migrate` для `alembic upgrade head`;
- `backend` без встроенного запуска миграций;
- `frontend` с healthcheck и runtime proxy на backend.

## Развёртывание в Kubernetes

1. Соберите и опубликуйте образы `backend` и `frontend`.
2. Скопируйте [deploy/helm/task-platform/values.production.example.yaml](/C:/Users/sasha/OneDrive/Рабочий%20стол/Магистратура/mvp/deploy/helm/task-platform/values.production.example.yaml) в свой `values.production.yaml`.
3. Заполните образа, `DATABASE_URL`, `JWT_SECRET_KEY`, ingress host и storage.
4. Установите chart:

```bash
helm upgrade --install task-platform deploy/helm/task-platform \
  -n task-platform \
  --create-namespace \
  -f deploy/helm/task-platform/values.production.yaml
```

По умолчанию chart включает:

- отдельный migration job через Helm hooks;
- HPA для backend и frontend;
- PDB для безболезненных rolling updates;
- PVC под `UPLOAD_DIR`;
- ingress-маршрутизацию `/api` на backend и `/` на frontend.

## Эксплуатационные замечания

- Для горизонтального масштабирования backend `UPLOAD_DIR` должен быть на shared PVC (`ReadWriteMany`) или вынесен во внешнее object storage.
- PostgreSQL и Qdrant лучше держать как managed/external сервисы, а не внутри этого chart.
- Для backend в конфиг вынесены `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`.

## Chat Agents

- Chat agents are now pluggable through `backend/app/agents/chat_agents`.
- New agents can be forced from chat with prefixes like `@qa` or `@change`.
- Each agent can now resolve its own `LLM provider/model/base_url/temperature`, including local `Ollama`, through `CHAT_AGENT_LLM_OVERRIDES`.
- Short integration guide: [backend/app/agents/README.md](/C:/Users/sasha/OneDrive/Рабочий%20стол/Магистратура/mvp/backend/app/agents/README.md).

## Полезные команды

```bash
make check
make docker-build
make helm-lint
make helm-template
```

Подробная инструкция по окружению, Compose и Kubernetes находится в [SETUP_GUIDE.md](/C:/Users/sasha/OneDrive/Рабочий%20стол/Магистратура/mvp/SETUP_GUIDE.md).
