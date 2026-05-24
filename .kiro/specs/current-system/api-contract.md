# Сводка API-контракта

## Соглашения

- Backend routes регистрируются на корневых путях. В production-like deployment фронтенд обращается к ним через nginx proxy `/api`.
- Защищенные endpoints требуют `Authorization: Bearer <access_token>`, если явно не указано другое.
- Refresh token передается через HTTP-only cookie `refresh_token`.
- Pydantic schemas в `backend/app/schemas` являются каноническими request/response contracts.
- Frontend clients в `frontend/src/api` зеркалируют backend endpoints.

## Система и статические файлы

| Метод | Путь | Авторизация | Назначение |
| --- | --- | --- | --- |
| `GET` | `/healthz` | Публичный | Проверка состояния процесса. |
| `GET` | `/readyz` | Публичный | Проверка готовности базы данных. |
| `GET` | `/uploads/*`, `/api/uploads/*` | Статический | Загруженные файлы. |
| `GET` | `/langgraph-images/*`, `/api/langgraph-images/*` | Статический | Экспортированные схемы LangGraph. |

## Аутентификация и пользователи

| Метод | Путь | Авторизация | Ответ / примечания |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | Публичный | `UserRead`; первый пользователь становится администратором. |
| `POST` | `/auth/login` | Публичный | `TokenResponse`; устанавливает refresh cookie. |
| `POST` | `/auth/refresh` | Refresh cookie | `TokenResponse`; выполняет refresh token rotation. |
| `POST` | `/auth/logout` | Optional refresh cookie | `204`; отзывает текущий refresh token, если он есть. |
| `GET` | `/auth/me` | Bearer | `UserRead`. |
| `GET` | `/auth/sessions` | Bearer | `SessionRead[]`. |
| `DELETE` | `/auth/sessions/{session_id}` | Bearer | `204`. |
| `GET` | `/users` | Bearer | `UserSummary[]`. |
| `PATCH` | `/users/me` | Bearer | `UserRead`. |
| `DELETE` | `/users/me` | Bearer | `204`. |
| `POST` | `/users/me/avatar` | Bearer multipart | `UserRead`. |
| `PATCH` | `/users/{user_id}` | Admin | `UserSummary`. |
| `DELETE` | `/users/{user_id}` | Admin | `204`; последний активный администратор защищен. |

## Проекты, правила и теги

| Метод | Путь | Авторизация | Назначение |
| --- | --- | --- | --- |
| `GET` | `/projects` | Bearer | Получить доступные проекты. |
| `POST` | `/projects` | Bearer | Создать проект и membership менеджера. |
| `GET` | `/projects/{project_id}` | Project access | Прочитать проект. |
| `PATCH` | `/projects/{project_id}` | Project manager; admin для validation settings | Обновить name, description или validation node settings. |
| `DELETE` | `/projects/{project_id}` | Project manager/admin | Удалить проект и очистить Qdrant/upload artifacts. |
| `GET` | `/projects/{project_id}/members` | Project access | Получить участников. |
| `POST` | `/projects/{project_id}/members` | Project manager/admin | Добавить участника с project role. |
| `DELETE` | `/projects/{project_id}/members/{user_id}` | Project manager/admin | Удалить участника. |
| `GET` | `/projects/{project_id}/rules` | Project access | Получить custom validation rules. |
| `POST` | `/projects/{project_id}/rules` | Project manager/admin | Создать custom rule. |
| `PATCH` | `/projects/{project_id}/rules/{rule_id}` | Project manager/admin | Обновить custom rule. |
| `DELETE` | `/projects/{project_id}/rules/{rule_id}` | Project manager/admin | Удалить custom rule. |
| `GET` | `/projects/{project_id}/task-tags` | Project access | Получить project task tags. |
| `POST` | `/projects/{project_id}/task-tags` | Project manager/admin | Добавить project tag. |
| `DELETE` | `/projects/{project_id}/task-tags/{tag_id}` | Project manager/admin | Удалить project tag. |

Admin endpoints для глобальных тегов:

- `GET /admin/task-tags`
- `POST /admin/task-tags`
- `PATCH /admin/task-tags/{tag_id}`
- `DELETE /admin/task-tags/{tag_id}`

## Задачи и валидация

| Метод | Путь | Авторизация | Назначение |
| --- | --- | --- | --- |
| `GET` | `/projects/{project_id}/tasks` | Project access | Получить задачи с optional status/search/participant filters. |
| `POST` | `/projects/{project_id}/tasks` | Project access | Создать задачу. |
| `GET` | `/projects/{project_id}/tasks/{task_id}` | Project access | Прочитать задачу. |
| `PATCH` | `/projects/{project_id}/tasks/{task_id}` | Project access plus workflow rules | Обновить title/content/tags. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/suggest-tags` | Project access | Получить LLM tag suggestions. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/commit` | Project access plus workflow rules | Переиндексировать измененное task content. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/approve` | Reviewer roles | Утвердить и назначить developer/tester/reviewer. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/validation-appeal` | Analyst/admin | Оспорить выбранные validation findings. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/start-development` | Developer/admin | Перевести в `in_progress`. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/ready-for-testing` | Developer/admin | Перевести в `ready_for_testing`. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/start-testing` | Tester/admin | Перевести в `testing`. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/complete` | Tester/admin | Перевести в `done`. |
| `DELETE` | `/projects/{project_id}/tasks/{task_id}` | Project access plus delete rules | Удалить задачу и artifacts. |
| `POST` | `/projects/{project_id}/tasks/{task_id}/attachments` | Project access | Загрузить attachment. |
| `GET` | `/projects/{project_id}/tasks/{task_id}/attachments/{attachment_id}` | Project access | Скачать attachment. |
| `DELETE` | `/projects/{project_id}/tasks/{task_id}/attachments/{attachment_id}` | Project access | Удалить attachment. |
| `POST` | `/tasks/{task_id}/validate` | Analyst/admin | Запустить validation graph. |

Важные schemas:

- `TaskCreate`, `TaskUpdate`, `TaskRead`.
- `TaskApprove`.
- `ValidationResult`, `ValidationIssue`, `ValidationAppealCreate`.
- `TaskAttachmentRead`.

## Чат и предложения изменений

| Метод | Путь | Авторизация | Назначение |
| --- | --- | --- | --- |
| `GET` | `/tasks/{task_id}/messages` | Task chat access | Получить task messages. |
| `POST` | `/tasks/{task_id}/messages` | Task chat access | Сохранить user message и запустить chat graph. |
| `WebSocket` | `/tasks/{task_id}/messages/ws` | Token-based | Realtime-обновления task chat. |
| `GET` | `/tasks/{task_id}/proposals` | Task access | Получить change proposals, optionally by status. |
| `PATCH` | `/tasks/{task_id}/proposals/{proposal_id}` | Task access plus proposal rules | Принять или отклонить proposal. |

Важные schemas:

- `MessageCreate`, `MessageRead`.
- `ProposalRead`, proposal status `new`, `accepted`, `rejected`.

QA `MessageRead.source_ref` может содержать RAG diagnostics (`cross_task_sources`, `reranked_chunks`) и отдельные UI-ready источники `used_cross_task_sources`. Кнопки перехода строятся только по `used_cross_task_sources`, где каждый элемент содержит как минимум `task_id` и `chunk_id`, а также может содержать `task_title`, `task_status` и `source_type`.

## Уведомления и Telegram

| Метод | Путь | Авторизация | Назначение |
| --- | --- | --- | --- |
| `GET` | `/notifications` | Bearer | Получить/отфильтровать notifications и unread count. |
| `PATCH` | `/notifications/{notification_id}/read` | Bearer | Отметить одно notification как прочитанное. |
| `POST` | `/notifications/read-all` | Bearer | Отметить все как прочитанные. |
| `GET` | `/users/me/notification-settings` | Bearer | Прочитать Telegram delivery settings и link state. |
| `PATCH` | `/users/me/notification-settings` | Bearer | Обновить Telegram delivery settings. |
| `POST` | `/users/me/telegram-link-token` | Bearer | Создать one-time Telegram link token и optional deep link. |
| `DELETE` | `/users/me/telegram` | Bearer | Отвязать Telegram. |
| `POST` | `/telegram/webhook` | Secret checked by service | Принять Telegram updates. |
| `GET` | `/tasks/{task_id}/chat-unread` | Chat access | Прочитать unread count. |
| `POST` | `/tasks/{task_id}/chat-read` | Chat access | Отметить chat как прочитанный. |
| `WebSocket` | `/notifications/ws` | Token-based | Realtime-уведомления. |

## Администрирование runtime и мониторинга

Admin endpoints требуют роль `ADMIN`.

| Область | Маршруты |
| --- | --- |
| LLM providers | `GET/POST /admin/llm/providers`, `PATCH /admin/llm/providers/{provider_id}`, `POST /admin/llm/providers/{provider_id}/test`, `POST /admin/llm/vision-test` |
| Runtime-настройки | `POST /admin/llm/runtime/default-provider`, `GET/PATCH /admin/llm/runtime/settings` |
| Agent overrides | `GET /admin/llm/overrides`, `GET /admin/llm/agents`, `PUT /admin/llm/overrides/{agent_key}` |
| Prompt configs | `GET /admin/llm/prompt-configs`, `PATCH /admin/llm/prompt-configs/{prompt_key}`, `GET /admin/llm/prompt-configs/{prompt_key}/versions`, `POST /admin/llm/prompt-configs/{prompt_key}/restore` |
| Monitoring | `GET /admin/monitoring/summary`, `/activity`, `/llm`, `/llm/requests`, `/graphs/summary`, `/graphs/runs`, `/graphs/runs/{run_id}` |
| Audit | `GET /admin/audit` |
| Validation questions | `GET /admin/validation/questions`, `DELETE /admin/validation/questions/{question_id}` |
| Qdrant | `GET /admin/qdrant/overview`, `GET /admin/qdrant/projects/{project_id}/coverage`, scenario probes, `POST /admin/qdrant/tasks/{task_id}/resync` |

## Админские оценочные наборы

| Suite | Основные endpoints |
| --- | --- |
| RAG Eval | `/admin/rag-eval/datasets`, `/admin/rag-eval/datasets/import`, `/admin/rag-eval/datasets/{dataset_id}`, `/admin/rag-eval/datasets/{dataset_id}/runs`, `/admin/rag-eval/runs/{run_id}`, `/admin/rag-eval/runs/{run_id}/export` |
| Orchestrator Eval | `/admin/orchestrator-eval/playground/run`, datasets import/list/detail, dataset runs, run detail/delete/export |
| Adaptation Eval | datasets import template/import/list/detail/delete, dataset runs, run detail/delete/export |
| Validation Eval | datasets import/list/detail/delete, manual case create/update/delete, dataset runs, run detail/delete/export |
| QuRE Eval | `POST/GET /admin/qure-eval/runs`, `GET/DELETE /admin/qure-eval/runs/{run_id}`, `GET /admin/qure-eval/runs/{run_id}/export` |
