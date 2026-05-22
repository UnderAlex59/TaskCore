# Контекст для ИИ-агентов

## Как использовать эту спецификацию

Перед изменением поведения начните отсюда:

1. Прочитайте `.kiro/steering/product.md`, чтобы понять продуктовые границы и акторов.
2. Прочитайте `.kiro/specs/current-system/requirements.md`, чтобы найти requirement IDs и ожидаемое поведение.
3. Прочитайте `design.md`, чтобы понять архитектуру и workflow invariants.
4. Прочитайте `api-contract.md` перед изменением routers, schemas или frontend API clients.
5. Прочитайте `tasks.md`, чтобы найти implementation и test anchors.

Эта спецификация является ретроспективной и описывает текущую систему. Не добавляйте roadmap behavior в эти файлы, пока такое поведение не реализовано в коде.

## Жесткие границы

- Не инспектируйте директории зависимостей и build output: `node_modules`, `.venv`, `venv`, `vendor`, `.next`, `dist`, `build`, `coverage`.
- Предпочитайте targeted search в `backend`, `frontend`, `app`, `src`, `tests` и `.kiro`.
- Не обходите service-layer business rules, добавляя логику напрямую в routers.
- Не создавайте прямые LLM-клиенты внутри graphs; используйте `LLMRuntimeService`.
- Не меняйте task status strings, role strings, message types или proposal statuses без обновления DB migrations, schemas, frontend types, tests и этой спецификации.
- Не меняйте Qdrant payload metadata или collection names без обновления RAG tests, admin diagnostics и этой спецификации.
- Не меняйте auth token/cookie semantics без обновления backend auth tests и frontend refresh-queue tests.

## Текущие инварианты

- Backend routes смонтированы в корне; `/api` является deployment/proxy convention.
- Project access основан на membership для non-admin users.
- Admin access основан на global role.
- Task chat access уже, чем project access, пока задача не достигнет team-chat statuses.
- Task validation result хранится в `tasks.validation_result` и управляет status transitions.
- Post-approval task edits требуют revalidation и могут требовать explicit RAG commit.
- Uploaded files должны оставаться внутри `UPLOAD_DIR`.
- Qdrant collections проверяются при backend startup.
- LangGraph image export failure логируется, но не блокирует startup.
- Graph run monitoring управляется `GRAPH_RUN_MONITORING_ENABLED` и runtime settings.

## Чеклист безопасного изменения

Для изменений поведения backend:

- Определите affected requirement IDs в `requirements.md`.
- Проверьте router, schema, service, model и tests для соответствующего domain.
- Добавьте или обновите tests в `backend/tests`.
- Добавьте Alembic migration, если меняется persistence shape.
- Обновите `.kiro` docs, если меняется API, workflow, data model, agents или tests.

Для изменений поведения frontend:

- Проверьте `frontend/src/App.tsx`, соответствующий `frontend/src/api/*Api.ts`, feature page и tests.
- Сохраняйте `apiClient` refresh behavior, если auth contract не меняется намеренно.
- Обновите feature tests при изменении UI behavior или route access.
- Обновите `.kiro` docs, если меняется route map или API usage.

Для изменений agent/RAG:

- Проверьте `backend/app/agents/README.md`, graph file, `state.py`, соответствующие services и tests.
- Сохраняйте `source_ref` полезным для routing/RAG/debug transparency.
- Сохраняйте deterministic fallbacks там, где tests зависят от unavailable LLM/Qdrant behavior.
- Обновите graph export expectations, если меняется graph topology.

## Команды проверки

Используйте самый узкий набор команд, который доказывает изменение:

```sh
cd backend && pytest tests/test_auth_api.py
cd backend && pytest tests/test_task_workflow_api.py tests/test_task_service.py
cd backend && pytest tests/test_chat_agents.py tests/test_rag_pipeline.py tests/test_rag_retrieval_graph.py
cd backend && pytest tests/test_admin_runtime_api.py tests/test_graph_run_monitoring.py
cd frontend && npm run test -- --run src/features/tasks/TaskForm.test.tsx
cd frontend && npm run test -- --run src/api/client.test.ts
```

Полная проверка качества:

```sh
make check
```

Проверка docs-only:

```sh
rg -n "TOD[O]|TB[D]|PLACEHOLD[E]R|FIXM[E]" .kiro
rg -n "REQ-[A-Z]+-[0-9]{3}" .kiro/specs/current-system/requirements.md
```
