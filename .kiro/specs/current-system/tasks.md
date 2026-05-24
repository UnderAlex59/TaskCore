# Трассировка реализации

## Назначение

Этот файл связывает текущие требования с реализованным кодом и тестами. Это не backlog будущих задач. Значения статуса:

- `implemented`: поведение существует в коде.
- `covered`: поведение существует и имеет прямые тесты.
- `partial`: поведение существует, но test coverage является косвенным или распределено по широким integration tests.

## Матрица требований

| ID требований | Статус | Основной код | Тестовые якоря |
| --- | --- | --- | --- |
| `REQ-AUTH-001` - `REQ-AUTH-004` | covered | `backend/app/routers/auth.py`, `backend/app/routers/users.py`, `backend/app/services/auth_service.py`, `backend/app/services/user_service.py`, `frontend/src/auth`, `frontend/src/api/client.ts` | `backend/tests/test_auth_api.py`, `backend/tests/test_security.py`, `frontend/src/auth/AuthProvider.test.tsx`, `frontend/src/auth/RouteGuards.test.tsx`, `frontend/src/api/client.test.ts` |
| `REQ-PROJ-001` - `REQ-PROJ-004` | covered | `backend/app/routers/projects.py`, `backend/app/services/project_service.py`, `backend/app/models/project.py`, `backend/app/models/custom_rule.py`, `frontend/src/features/projects`, `frontend/src/features/admin/CustomRulesEditor.tsx` | `backend/tests/test_projects_api.py`, `backend/tests/test_task_workflow_api.py` |
| `REQ-TAG-001` - `REQ-TAG-003` | covered | `backend/app/routers/task_tags.py`, `backend/app/routers/admin.py`, `backend/app/services/task_tag_service.py`, `backend/app/agents/task_tag_suggestion_graph.py`, `frontend/src/features/admin/TaskTagsPage.tsx` | `backend/tests/test_task_tags_api.py`, `backend/tests/test_llm_agent_registry.py` |
| `REQ-TASK-001` - `REQ-TASK-007` | covered | `backend/app/routers/tasks.py`, `backend/app/services/task_service.py`, `backend/app/models/task.py`, `backend/app/schemas/task.py`, `frontend/src/features/tasks` | `backend/tests/test_task_workflow_api.py`, `backend/tests/test_task_service.py`, `backend/tests/test_task_review_and_testing_api.py`, `frontend/src/features/tasks/*.test.tsx`, `frontend/src/features/tasks/taskDocument.test.ts` |
| `REQ-VAL-001` - `REQ-VAL-004` | covered | `backend/app/routers/validation.py`, `backend/app/agents/validation_graph.py`, `backend/app/services/validation_question_service.py`, `frontend/src/features/tasks/ValidationPanel.tsx`, `frontend/src/features/admin/ValidationQuestionsPage.tsx` | `backend/tests/test_validation_graph.py`, `backend/tests/test_task_workflow_api.py`, `backend/tests/test_admin_validation_eval_api.py`, `frontend/src/features/tasks/ValidationPanel.test.tsx`, `frontend/src/features/admin/ValidationQuestionsPage.test.tsx` |
| `REQ-CHAT-001` - `REQ-CHAT-005` | covered | `backend/app/routers/chat.py`, `backend/app/routers/proposals.py`, `backend/app/services/chat_service.py`, `backend/app/agents/chat_graph.py`, `backend/app/agents/qa_agent_graph.py`, `backend/app/agents/change_tracker_agent_graph.py`, `backend/app/agents/subgraph_registry.py`, `frontend/src/features/chat` | `backend/tests/test_chat_agents.py`, `backend/tests/test_chat_routing.py`, `backend/tests/test_task_workflow_api.py`, `frontend/src/features/chat/*.test.tsx`; QA source-link behavior covered by focused chat agent and MessageBubble tests |
| `REQ-RAG-001` - `REQ-RAG-004` | covered | `backend/app/services/qdrant_service.py`, `backend/app/services/rag_service.py`, `backend/app/agents/rag_pipeline.py`, `backend/app/agents/rag_retrieval_graph.py`, `backend/app/services/admin_qdrant_service.py`, `frontend/src/features/admin/QdrantAdminPage.tsx` | `backend/tests/test_qdrant_service.py`, `backend/tests/test_qdrant_service_filters.py`, `backend/tests/test_rag_pipeline.py`, `backend/tests/test_rag_retrieval_graph.py`, `backend/tests/test_admin_qdrant_api.py`, `backend/tests/test_admin_qdrant_service.py`, `frontend/src/features/admin/QdrantAdminPage.test.tsx` |
| `REQ-NOTIF-001` - `REQ-NOTIF-003` | covered | `backend/app/routers/notifications.py`, `backend/app/routers/telegram.py`, `backend/app/services/notification_service.py`, `backend/app/services/telegram_service.py`, `frontend/src/features/notifications`, `frontend/src/shared/components/Layout.tsx` | `backend/tests/test_notifications_api.py`, `frontend/src/features/notifications/NotificationsPage.test.tsx`, `frontend/src/shared/components/Layout.test.tsx` |
| `REQ-ADMIN-001` | covered | `backend/app/routers/admin.py`, `backend/app/services/admin_llm_service.py`, `backend/app/services/llm_runtime_service.py`, `backend/app/services/llm_prompt_service.py`, `frontend/src/features/admin/ProviderSettingsPage.tsx`, `frontend/src/features/admin/AgentPromptsPage.tsx` | `backend/tests/test_admin_runtime_api.py`, `backend/tests/test_llm_runtime_service.py`, `frontend/src/features/admin/ProviderSettingsPage.test.tsx`, `frontend/src/features/admin/VisionTestPage.test.tsx` |
| `REQ-ADMIN-002` | covered | `backend/app/services/monitoring_service.py`, `backend/app/services/graph_run_tracing.py`, `backend/app/routers/admin.py`, `frontend/src/features/admin/MonitoringPage.tsx`, `frontend/src/features/admin/GraphRunsPage.tsx` | `backend/tests/test_graph_run_monitoring.py`, `backend/tests/test_admin_runtime_api.py`, `frontend/src/features/admin/MonitoringPage.test.tsx`, `frontend/src/features/admin/GraphRunsPage.test.tsx` |
| `REQ-ADMIN-003` | covered | `backend/app/services/admin_rag_eval_service.py`, `backend/app/services/admin_orchestrator_eval_service.py`, `backend/app/services/admin_adaptation_eval_service.py`, `backend/app/services/admin_validation_eval_service.py`, `backend/app/services/admin_qure_eval_service.py`, `frontend/src/features/admin/*EvalPage.tsx` | `backend/tests/test_admin_rag_eval_api.py`, `backend/tests/test_admin_orchestrator_eval_api.py`, `backend/tests/test_admin_adaptation_eval_api.py`, `backend/tests/test_admin_validation_eval_api.py`, `backend/tests/test_admin_qure_eval_api.py`, frontend eval page tests |
| `REQ-UI-001` - `REQ-UI-004` | covered | `frontend/src/App.tsx`, `frontend/src/auth`, `frontend/src/api`, `frontend/src/features` | `frontend/src/auth/RouteGuards.test.tsx`, `frontend/src/api/client.test.ts`, feature tests в `frontend/src/features` |
| `REQ-DEPLOY-001` - `REQ-DEPLOY-002` | partial | `backend/main.py`, `backend/app/core/config.py`, `docker-compose.yml`, Dockerfiles, nginx config | `backend/tests/test_system_api.py`, `backend/tests/test_langgraph_images_api.py`, Compose healthchecks |
| `REQ-NFR-001` - `REQ-NFR-003` | covered | `backend/app/services/audit_service.py`, `backend/app/services/graph_run_tracing.py`, `backend/app/models/llm_request_log.py`, `Makefile`, `backend/pyproject.toml`, `frontend/package.json` | `backend/tests/test_admin_runtime_api.py`, `backend/tests/test_graph_run_monitoring.py`, command definitions |

## Выполненные элементы документации

- [x] Описать текущий product context и actor model в `.kiro/steering/product.md`.
- [x] Описать stack, runtime services, env groups и quality commands в `.kiro/steering/tech.md`.
- [x] Описать repository ownership и safe edit boundaries в `.kiro/steering/structure.md`.
- [x] Описать текущие requirements со stable IDs в `requirements.md`.
- [x] Описать текущую architecture, workflows, data model и agent/RAG design в `design.md`.
- [x] Описать API route groups, auth conventions и schema ownership в `api-contract.md`.
- [x] Описать handoff rules для ИИ-агентов в `agent-context.md`.

## Правило сопровождения

Когда изменение модифицирует поведение, обновляйте эту матрицу в том же change set, что и код. Требование может оставаться `covered` только если существующие или новые тесты по-прежнему проверяют измененное поведение.
