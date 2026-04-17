# task-platform Helm chart

Chart разворачивает:

- backend deployment/service;
- frontend deployment/service;
- migration job через Helm hooks;
- ingress c путями `/api` и `/`;
- HPA и PDB для обоих сервисов;
- PVC для `UPLOAD_DIR`.

## Быстрый запуск

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
- `frontend.image.repository`
- `frontend.image.tag`
- `ingress.enabled`
- `ingress.hosts`
- `ingress.tls`
- `uploads.persistence`

Готовый production override-шаблон: `values.production.example.yaml`.

