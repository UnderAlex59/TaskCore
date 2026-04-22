# task-platform Helm chart

Helm chart разворачивает Task Platform MVP в Kubernetes.

## Состав chart

- backend `Deployment` и `Service`;
- frontend `Deployment` и `Service`;
- migration `Job` через Helm hooks для `alembic upgrade head`;
- `Ingress` с маршрутизацией `/api` на backend и `/` на frontend;
- `HPA` для backend и frontend;
- `PDB` для более безопасных rolling updates;
- `PVC` для `UPLOAD_DIR`;
- `ConfigMap` и `Secret` для backend-настроек.

## Быстрый запуск

Скопируйте production-шаблон и заполните значения:

```bash
cp deploy/helm/task-platform/values.production.example.yaml \
  deploy/helm/task-platform/values.production.yaml
```

Установка:

```bash
helm upgrade --install task-platform deploy/helm/task-platform \
  -n task-platform \
  --create-namespace \
  -f deploy/helm/task-platform/values.production.yaml
```

## Ключевые values

- `backend.image.repository`
- `backend.image.tag`
- `backend.secretEnv.databaseUrl`
- `backend.secretEnv.jwtSecretKey`
- `backend.env.allowedOrigins`
- `backend.env.qdrantUrl`
- `backend.env.uploadDir`
- `frontend.image.repository`
- `frontend.image.tag`
- `ingress.enabled`
- `ingress.hosts`
- `ingress.tls`
- `uploads.persistence`

## Проверка chart

Из корня репозитория:

```bash
make helm-lint
make helm-template
```

## Production-замечания

- PostgreSQL и Qdrant лучше держать как managed/external сервисы.
- `JWT_SECRET_KEY` должен быть отдельным production-секретом.
- Для нескольких backend replicas нужен общий `UPLOAD_DIR` через RWX PVC или внешний object storage.
- Для HTTPS выставляйте secure cookie и корректные CORS origins.
- Миграции выполняются отдельным hook job, а не из основного процесса backend.
