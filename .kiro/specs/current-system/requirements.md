# Требования текущей системы

## Область действия

Эта спецификация документирует реализованное состояние репозитория. Идентификаторы требований являются стабильными ссылками для разработчиков и ИИ-агентов. Каждое требование указывает на область реализации и существующие тесты, когда их можно однозначно определить.

## Аутентификация и пользователи

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-AUTH-001` | Система должна поддерживать регистрацию, вход, refresh, logout, получение текущего пользователя и отзыв сессий. Первый зарегистрированный пользователь получает роль `ADMIN`; следующие пользователи по умолчанию получают `DEVELOPER`. | `backend/app/routers/auth.py`, `backend/app/services/auth_service.py`, `backend/app/core/security.py`, `backend/app/models/refresh_token.py` | `backend/tests/test_auth_api.py`, `backend/tests/test_security.py`, `frontend/src/auth/AuthProvider.test.tsx`, `frontend/src/api/client.test.ts` |
| `REQ-AUTH-002` | Система должна аутентифицировать защищенные backend API через bearer JWT и отклонять неактивных или удаленных пользователей. | `backend/app/core/dependencies.py`, все routers с `CurrentUser` или `require_role` | `backend/tests/test_auth_api.py`, `backend/tests/test_admin_runtime_api.py` |
| `REQ-AUTH-003` | Система должна поддерживать глобальные роли `ADMIN`, `ANALYST`, `DEVELOPER`, `TESTER`, `MANAGER` и ограничивать admin-only API. | `backend/app/models/user.py`, `backend/app/core/dependencies.py`, `backend/app/routers/admin.py`, `frontend/src/auth/RoleGuard.tsx` | `backend/tests/test_admin_runtime_api.py`, `frontend/src/auth/RouteGuards.test.tsx` |
| `REQ-AUTH-004` | Система должна позволять пользователям редактировать профиль, загружать аватар, удалять собственный аккаунт, а администраторам - обновлять и удалять пользователей с защитой последнего активного администратора. | `backend/app/routers/users.py`, `backend/app/services/user_service.py`, `frontend/src/features/profile/ProfilePage.tsx`, `frontend/src/features/admin/UserList.tsx` | `backend/tests/test_auth_api.py` |

## Проекты, участники и правила

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-PROJ-001` | Система должна позволять авторизованным пользователям получать доступные проекты, создавать проекты, читать/обновлять/удалять проекты и автоматически добавлять создателя как project `MANAGER`. | `backend/app/routers/projects.py`, `backend/app/services/project_service.py`, `backend/app/models/project.py`, `frontend/src/features/projects` | `backend/tests/test_projects_api.py` |
| `REQ-PROJ-002` | Система должна требовать project membership для доступа не-администраторов и права project manager для управления участниками и правилами. | `backend/app/services/project_service.py`, `backend/app/core/dependencies.py` | `backend/tests/test_projects_api.py`, `backend/tests/test_task_workflow_api.py` |
| `REQ-PROJ-003` | Система должна поддерживать настройки project validation nodes для `core_rules`, `custom_rules` и `context_questions`; менять эти настройки могут только администраторы. | `backend/app/core/validation_settings.py`, `backend/app/models/project.py`, `backend/app/schemas/project.py` | `backend/tests/test_projects_api.py`, `backend/tests/test_task_workflow_api.py` |
| `REQ-PROJ-004` | Система должна поддерживать кастомные project validation rules с фильтрами по тегам и состоянием active/inactive. | `backend/app/models/custom_rule.py`, `backend/app/routers/projects.py`, `frontend/src/features/admin/CustomRulesEditor.tsx` | `backend/tests/test_task_workflow_api.py` |

## Теги задач

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-TAG-001` | Система должна поддерживать глобальный справочник task tags и project-specific директорию тегов задач. | `backend/app/models/task_tag.py`, `backend/app/models/project_task_tag.py`, `backend/app/routers/task_tags.py`, `backend/app/routers/admin.py` | `backend/tests/test_task_tags_api.py` |
| `REQ-TAG-002` | Система должна валидировать task tags по project directory и обновлять задачи/правила при переименовании или удалении проектных тегов. | `backend/app/services/task_tag_service.py`, `backend/app/services/task_service.py` | `backend/tests/test_task_tags_api.py` |
| `REQ-TAG-003` | Система должна предлагать task tags через LangGraph LLM graph на основе содержимого задачи и project tag directory. | `backend/app/agents/task_tag_suggestion_graph.py`, `backend/app/routers/tasks.py`, `frontend/src/api/tasksApi.ts` | `backend/tests/test_task_tags_api.py`, `backend/tests/test_llm_agent_registry.py` |

## Задачи и рабочий процесс

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-TASK-001` | Система должна поддерживать task CRUD внутри проекта с title, Markdown content, tags, analyst, reviewer, developer, tester, validation result, indexed timestamp и attachments. | `backend/app/models/task.py`, `backend/app/schemas/task.py`, `backend/app/routers/tasks.py`, `frontend/src/features/tasks` | `backend/tests/test_task_workflow_api.py`, `backend/tests/test_task_service.py`, `frontend/src/features/tasks/TaskForm.test.tsx` |
| `REQ-TASK-002` | Система должна поддерживать фильтрацию задач по status, search text и participant scope с учетом project access. | `backend/app/services/task_service.py`, `frontend/src/features/tasks/TaskList.tsx` | `backend/tests/test_task_service.py`, `frontend/src/features/tasks/TaskList.test.tsx` |
| `REQ-TASK-003` | Система должна проводить задачи через validation и approval statuses и сохранять `needs_rework`, когда валидация находит blocking issues. | `backend/app/services/task_service.py`, `backend/app/agents/validation_graph.py` | `backend/tests/test_task_workflow_api.py`, `backend/tests/test_validation_graph.py` |
| `REQ-TASK-004` | Система должна поддерживать optional second analyst review до перехода задачи в `ready_for_dev`. | `backend/app/services/task_service.py`, `backend/app/schemas/task.py` | `backend/tests/test_task_service.py`, `backend/tests/test_task_review_and_testing_api.py` |
| `REQ-TASK-005` | Система должна поддерживать delivery flow `ready_for_dev -> in_progress -> ready_for_testing -> testing -> done` с role-aware actions. | `backend/app/services/task_service.py`, `frontend/src/features/tasks/TaskWorkspacePage.tsx` | `backend/tests/test_task_review_and_testing_api.py`, `backend/tests/test_task_service.py` |
| `REQ-TASK-006` | Система должна помечать утвержденные задачи как требующие revalidation и explicit embedding commit при post-approval изменениях содержимого. | `backend/app/services/task_service.py`, `frontend/src/features/tasks/TaskForm.tsx` | `backend/tests/test_task_workflow_api.py`, `frontend/src/features/tasks/TaskForm.test.tsx` |
| `REQ-TASK-007` | Система должна хранить task attachments внутри `UPLOAD_DIR`, предоставлять download/delete API, генерировать image `alt_text` через Vision при доступности и включать meaningful attachment content в RAG. | `backend/app/services/task_service.py`, `backend/app/services/attachment_content_service.py`, `backend/app/agents/attachment_vision_graph.py`, `backend/app/agents/rag_pipeline.py` | `backend/tests/test_task_workflow_api.py`, `backend/tests/test_rag_pipeline.py`, `frontend/src/features/tasks/AttachmentUpload.test.tsx` |

## Валидация

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-VAL-001` | Система должна валидировать требования задач через LangGraph stages для normalized input, core rules, custom project rules и context questions. | `backend/app/agents/validation_graph.py`, `backend/app/services/task_service.py`, `backend/app/routers/validation.py` | `backend/tests/test_validation_graph.py`, `backend/tests/test_task_workflow_api.py` |
| `REQ-VAL-002` | Система должна сохранять validation verdict, issues, questions, timestamps и appeal metadata в `tasks.validation_result`. | `backend/app/models/task.py`, `backend/app/schemas/task.py`, `backend/app/services/task_service.py` | `backend/tests/test_task_workflow_api.py`, `frontend/src/features/tasks/ValidationPanel.test.tsx` |
| `REQ-VAL-003` | Система должна позволять analyst/admin оспаривать выбранные validation findings с указанием причин и переводить accepted appeals к approval. | `backend/app/services/task_service.py`, `backend/app/routers/tasks.py`, `frontend/src/features/tasks/ValidationPanel.tsx` | `backend/tests/test_task_workflow_api.py`, `frontend/src/features/tasks/ValidationPanel.test.tsx` |
| `REQ-VAL-004` | Система должна поддерживать validation question backlog, формируемый из low-confidence QA и validation context questions. | `backend/app/models/validation_question.py`, `backend/app/services/validation_question_service.py`, `backend/app/routers/admin.py` | `backend/tests/test_task_workflow_api.py`, `backend/tests/test_admin_runtime_api.py`, `frontend/src/features/admin/ValidationQuestionsPage.test.tsx` |

## Чат, агенты и предложения изменений

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-CHAT-001` | Система должна предоставлять per-task chat history, создание сообщений и realtime WebSocket updates пользователям с chat access. | `backend/app/routers/chat.py`, `backend/app/services/chat_service.py`, `backend/app/services/chat_realtime.py`, `frontend/src/features/chat` | `backend/tests/test_task_workflow_api.py`, `frontend/src/features/chat/MessageList.test.tsx` |
| `REQ-CHAT-002` | Система должна маршрутизировать chat messages через `chat_graph`, используя forced agent prefixes или LLM routing metadata. | `backend/app/agents/chat_graph.py`, `backend/app/agents/chat_routing.py`, `backend/app/agents/subgraph_registry.py` | `backend/tests/test_chat_agents.py`, `backend/tests/test_chat_routing.py`, `backend/tests/test_admin_orchestrator_eval_api.py` |
| `REQ-CHAT-003` | Система должна отвечать на task questions через QA Agent, используя current task content, validation result, attachments и cross-task RAG context. Если ответ опирается на стороннюю задачу, QA должна явно указать использованные `chunk_id`, а UI должен показывать переход только к этим использованным задачам, не ко всем retrieval-кандидатам. | `backend/app/agents/qa_agent_graph.py`, `backend/app/agents/rag_retrieval_graph.py`, `backend/app/services/qdrant_service.py`, `frontend/src/features/chat/MessageBubble.tsx` | `backend/tests/test_chat_agents.py`, `backend/tests/test_rag_retrieval_graph.py`, `frontend/src/features/chat/MessageBubble.test.tsx` |
| `REQ-CHAT-004` | Система должна извлекать change proposals из чата, обнаруживать duplicate proposals и предоставлять proposal review status. При принятии proposal система должна добавлять его в markdown-секцию задачи `## История изменений`; frontend должен читать эту секцию во вкладке истории и поддерживать legacy-заголовок `## Одобренные изменения`. Review-события в чате должны показывать пользователю статус, ревьюера и текст предложения без raw UUID в основном тексте сообщения. | `backend/app/agents/change_tracker_agent_graph.py`, `backend/app/models/change_proposal.py`, `backend/app/routers/proposals.py`, `backend/app/services/proposal_service.py`, `frontend/src/features/chat/MessageBubble.tsx`, `frontend/src/features/tasks/taskDocument.ts` | `backend/tests/test_chat_agents.py`, `backend/tests/test_task_workflow_api.py`, `frontend/src/features/chat/MessageBubble.test.tsx`, `frontend/src/features/tasks/taskDocument.test.ts` |
| `REQ-CHAT-005` | Система должна позволять подключать external chat subgraphs через `CHAT_AGENT_MODULES` и `register_agent_subgraph`. | `backend/app/agents/subgraph_registry.py`, `backend/app/agents/README.md` | `backend/tests/test_chat_agents.py` |

## RAG и Qdrant

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-RAG-001` | Система должна проверять Qdrant collections при app startup и использовать active embedding provider metadata для совместимости. | `backend/main.py`, `backend/app/services/qdrant_service.py` | `backend/tests/test_qdrant_service.py`, `backend/tests/test_system_api.py` |
| `REQ-RAG-002` | Система должна индексировать task title, description, tags, meaningful attachment content, image alt text, validation output и selected project context. | `backend/app/agents/rag_pipeline.py`, `backend/app/services/rag_service.py` | `backend/tests/test_rag_pipeline.py`, `backend/tests/test_task_workflow_api.py` |
| `REQ-RAG-003` | Система должна извлекать RAG context с query rewriting, candidate retrieval, hybrid reranking, score thresholds и deterministic fallback behavior. | `backend/app/agents/rag_retrieval_graph.py`, `backend/app/services/bm25_retrieval_service.py` | `backend/tests/test_rag_retrieval_graph.py`, `backend/tests/test_admin_rag_eval_api.py` |
| `REQ-RAG-004` | Система должна предоставлять admin Qdrant diagnostics, scenario probes и task resync. | `backend/app/services/admin_qdrant_service.py`, `backend/app/routers/admin.py`, `frontend/src/features/admin/QdrantAdminPage.tsx` | `backend/tests/test_admin_qdrant_api.py`, `backend/tests/test_admin_qdrant_service.py`, `frontend/src/features/admin/QdrantAdminPage.test.tsx` |

## Уведомления и Telegram

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-NOTIF-001` | Система должна создавать, получать, фильтровать и отмечать in-app notifications с unread counts. | `backend/app/models/notification.py`, `backend/app/services/notification_service.py`, `backend/app/routers/notifications.py` | `backend/tests/test_notifications_api.py`, `frontend/src/features/notifications/NotificationsPage.test.tsx` |
| `REQ-NOTIF-002` | Система должна отслеживать chat unread state для пары user/task и позволять отмечать task chat как прочитанный. | `backend/app/models/notification.py`, `backend/app/routers/notifications.py` | `backend/tests/test_notifications_api.py`, `frontend/src/shared/components/Layout.test.tsx` |
| `REQ-NOTIF-003` | Система должна позволять пользователям привязывать/отвязывать Telegram, управлять normal/important delivery settings и принимать Telegram webhook messages с secret. | `backend/app/routers/telegram.py`, `backend/app/services/telegram_service.py`, `backend/app/services/notification_service.py` | `backend/tests/test_notifications_api.py` |

## Администрирование, мониторинг и оценка

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-ADMIN-001` | Система должна позволять администраторам настраивать LLM providers, тестировать providers/Vision, выбирать default runtime provider, задавать agent overrides и редактировать prompt configs с version restore. | `backend/app/routers/admin.py`, `backend/app/services/admin_llm_service.py`, `backend/app/services/llm_runtime_service.py`, `backend/app/services/llm_prompt_service.py`, `frontend/src/features/admin/ProviderSettingsPage.tsx`, `frontend/src/features/admin/AgentPromptsPage.tsx` | `backend/tests/test_admin_runtime_api.py`, `backend/tests/test_llm_runtime_service.py`, `frontend/src/features/admin/ProviderSettingsPage.test.tsx`, `frontend/src/features/admin/VisionTestPage.test.tsx` |
| `REQ-ADMIN-002` | Система должна предоставлять monitoring summaries, activity, LLM usage, LLM request logs, audit events, graph run summaries и graph run details. | `backend/app/services/monitoring_service.py`, `backend/app/services/graph_run_tracing.py`, `backend/app/routers/admin.py`, `frontend/src/features/admin/MonitoringPage.tsx`, `frontend/src/features/admin/GraphRunsPage.tsx` | `backend/tests/test_admin_runtime_api.py`, `backend/tests/test_graph_run_monitoring.py`, `frontend/src/features/admin/MonitoringPage.test.tsx`, `frontend/src/features/admin/GraphRunsPage.test.tsx` |
| `REQ-ADMIN-003` | Система должна поддерживать datasets/runs/exports для RAG Eval, Orchestrator Eval, Adaptation Eval, Validation Eval и QuRE Eval; semantic LLM-as-judge eval helpers должны передавать выбранные judge provider ids в runtime, использовать первый provider как primary и сохранять сравнение с secondary providers; Validation Eval запускает один выбранный уровень проверки (`core_rules`, `custom_rules` или `context_questions`) и считает метрики только по нему. | `backend/app/services/admin_*_eval_service.py`, `backend/app/models/*_eval.py`, `backend/app/routers/admin.py`, `frontend/src/features/admin/*EvalPage.tsx` | `backend/tests/test_admin_rag_eval_api.py`, `backend/tests/test_admin_orchestrator_eval_api.py`, `backend/tests/test_admin_adaptation_eval_api.py`, `backend/tests/test_admin_validation_eval_api.py`, `backend/tests/test_admin_qure_eval_api.py`, `backend/tests/test_eval_judge_config.py`, соответствующие frontend `*EvalPage.test.tsx` |

## Фронтенд

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-UI-001` | Фронтенд должен защищать authenticated routes и ограничивать `/admin/*` routes ролью `ADMIN`. | `frontend/src/App.tsx`, `frontend/src/auth/ProtectedRoute.tsx`, `frontend/src/auth/RoleGuard.tsx` | `frontend/src/auth/RouteGuards.test.tsx` |
| `REQ-UI-002` | Фронтенд должен предоставлять project list, task list, task create/detail/workspace, chat, notifications и profile pages. | `frontend/src/features/projects`, `frontend/src/features/tasks`, `frontend/src/features/chat`, `frontend/src/features/notifications`, `frontend/src/features/profile` | Feature tests в `frontend/src/features/**` |
| `REQ-UI-003` | Фронтенд должен предоставлять admin pages для monitoring, graph runs, Qdrant, eval suites, providers, prompts, users, task tags и project rules. | `frontend/src/features/admin`, `frontend/src/api/adminApi.ts` | Admin page tests в `frontend/src/features/admin/**` |
| `REQ-UI-004` | Frontend API client должен добавлять bearer tokens, повторять queued 401 responses через `/auth/refresh` и перенаправлять на `/login`, если refresh завершился ошибкой. | `frontend/src/api/client.ts`, `frontend/src/store/authStore.ts` | `frontend/src/api/client.test.ts`, `frontend/src/auth/AuthProvider.test.tsx` |

## Развертывание и нефункциональное поведение

| ID | Требование | Реализация | Тесты |
| --- | --- | --- | --- |
| `REQ-DEPLOY-001` | Backend должен предоставлять `/healthz`, `/readyz`, CORS, upload static files и LangGraph image static files. | `backend/main.py`, `backend/app/core/config.py` | `backend/tests/test_system_api.py`, `backend/tests/test_langgraph_images_api.py` |
| `REQ-DEPLOY-002` | Репозиторий должен предоставлять Docker Compose services для PostgreSQL, Qdrant, Ollama, migrations, backend, Telegram webhook setup и frontend. | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `frontend/nginx.conf` | Setup docs и Compose healthchecks |
| `REQ-NFR-001` | Система должна записывать audit events для важных auth, project, task и admin changes. | `backend/app/models/audit_event.py`, `backend/app/services/audit_service.py`, service layer calls | `backend/tests/test_admin_runtime_api.py`, `backend/tests/test_notifications_api.py` |
| `REQ-NFR-002` | Система должна логировать LLM requests и graph run events, когда monitoring включен. | `backend/app/models/llm_request_log.py`, `backend/app/models/graph_run_log.py`, `backend/app/models/graph_run_event.py`, `backend/app/services/graph_run_tracing.py` | `backend/tests/test_graph_run_monitoring.py`, `backend/tests/test_admin_runtime_api.py` |
| `REQ-NFR-003` | Репозиторий должен проверяться через backend lint/test, frontend lint/typecheck/test/build и docs-only static checks. | `Makefile`, `backend/pyproject.toml`, `frontend/package.json` | Существующий CI-compatible command set |
