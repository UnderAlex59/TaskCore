# План актуализации отчета по текущей реализации

Источник истины для технической части: текущий проект `mvp`.

Цель документа: зафиксировать, какие технические формулировки нужно использовать в отчете, чтобы он описывал фактическую реализацию, а не раннюю архитектурную гипотезу.

## Краткий вывод

Проект реализует платформу управления задачами и требованиями с FastAPI backend, React frontend, PostgreSQL, Qdrant, RAG и агентным слоем на LangGraph.

В отчете нужно последовательно отражать:

- AI-сценарии построены на LangGraph-графах и subgraphs;
- frontend использует собственные React-компоненты;
- RAG работает через Qdrant-коллекции `task_knowledge`, `project_questions`, `task_proposals`;
- workflow задачи включает статусы разработки и тестирования;
- в проекте есть админские разделы LLM runtime, prompts, Qdrant, monitoring, audit, tags, users, validation questions и Vision test;
- Docker Compose поднимает PostgreSQL, Qdrant, Ollama, миграции, backend и frontend.

## Что оставить в отчете

Можно сохранить следующие тезисы:

- качество требований критично для Agile-команд;
- платформа объединяет требования, задачи, чат и автоматическую проверку;
- PostgreSQL хранит транзакционные сущности;
- Qdrant используется для семантического поиска;
- RAG работает как память проекта;
- agentic-слой нужен для валидации, ответов на вопросы и сопровождения изменений;
- проект поддерживает облачные и локальные LLM-провайдеры.

## Раздел "Данные"

Нужно описать фактические сущности:

- `users` - пользователи, роли, профиль, avatar URL, активность;
- `refresh_tokens` - refresh-сессии и отзыв токенов;
- `projects` и `project_members` - проекты и участники;
- `custom_rules` - проектные правила проверки требований;
- `tasks` - требования с авторами, участниками, статусами, validation result и indexed timestamp;
- `task_attachments` - вложения, MIME-тип, путь хранения, `alt_text`;
- `messages` - сообщения `general`, `question`, `change_proposal`, `agent_answer`, `agent_proposal`;
- `change_proposals` - предложения изменений со статусами `new`, `accepted`, `rejected`;
- `validation_questions` - банк вопросов валидации;
- `task_tags` и `project_task_tags` - справочник тегов;
- `audit_events` - аудит действий;
- LLM runtime-таблицы: provider configs, agent overrides, request logs, runtime settings, prompt configs и prompt versions.

Статусы задачи нужно указывать полностью:

```text
draft -> validating -> needs_rework / awaiting_approval -> ready_for_dev -> in_progress -> ready_for_testing -> testing -> done
```

## Раздел "Технологический стек"

Рекомендуемая таблица:

| Слой | Технология | Обоснование |
| --- | --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, Zustand, Axios, Tailwind CSS | Типизированный SPA с рабочими и админскими экранами |
| Backend | FastAPI, SQLAlchemy AsyncIO, Alembic, Pydantic v2 | Асинхронный API, миграции, строгие схемы данных |
| БД | PostgreSQL | Транзакционные данные: пользователи, проекты, задачи, сообщения, аудит и настройки |
| Векторное хранилище | Qdrant | Семантический поиск по задачам, вопросам и предложениям |
| Agentic-слой | LangGraph, LangChain | Явные графы состояний, conditional routing, subgraph-per-agent |
| LLM runtime | OpenAI, Ollama, OpenRouter, GigaChat, OpenAI-compatible API | Переключение провайдеров без изменения бизнес-логики |
| Инфраструктура | Docker Compose | Локальный production-like запуск всех сервисов |

В обосновании AI-слоя использовать формулировку:

> LangGraph выбран как основной слой агентной оркестрации, потому что позволяет явно описывать состояние, узлы, условные переходы, subgraph-per-agent подход и экспортировать графы для визуального контроля.

## Раздел "Валидация требований"

Фактический сценарий:

- пользователь запускает validation endpoint;
- backend переводит задачу в `validating`;
- `validation_graph` нормализует вход;
- граф применяет базовые критерии качества;
- граф учитывает кастомные правила проекта;
- граф использует вопросы из `project_questions`;
- агрегатор формирует verdict `approved` или `needs_rework`;
- результат сохраняется в `tasks.validation_result`;
- задача переходит в `awaiting_approval` или `needs_rework`;
- результат добавляется в чат и RAG-контекст.

Нужно отдельно указать, что после успешной автоматической проверки требуется ручное подтверждение и назначение команды.

## Раздел "RAG"

Фактический RAG-контур:

- `rag_pipeline` готовит chunks;
- `QdrantService` управляет коллекциями;
- `task_knowledge` хранит контекст задач;
- `project_questions` хранит вопросы для повторного использования;
- `task_proposals` хранит предложения изменений и помогает искать дубли.

Источники chunks:

- заголовок задачи;
- описание;
- теги;
- текст и метаданные вложений;
- `alt_text` изображений при включенной Vision-обработке;
- результат валидации.

Параметры RAG задаются env-переменными:

- `RAG_CHUNK_TARGET_TOKENS`;
- `RAG_CHUNK_OVERLAP_TOKENS`;
- `RAG_ATTACHMENT_MAX_TEXT_CHARS`;
- `RAG_VISION_ENABLED`;
- `RAG_VISION_MAX_IMAGE_BYTES`.

В отчете не нужно обещать мультимодальную обработку для любого запуска: она зависит от включенного Vision-контура и доступного провайдера.

## Раздел "Чат и агенты"

Фактический поток:

- `ChatService` сохраняет пользовательское сообщение;
- тип сообщения предварительно определяется эвристически;
- `chat_graph` строит context;
- forced routing по prefix направляет сообщение в конкретный agent alias;
- без prefix agent выбирается через `subgraph_registry`;
- QA Agent отвечает на вопросы;
- ChangeTracker Agent формирует предложения изменений;
- Manager Agent работает как fallback;
- ответ сохраняется как message и рассылается через WebSocket;
- предложения изменений сохраняются в `change_proposals`;
- вопросы для будущих проверок сохраняются в `validation_questions`.

Примеры forced routing:

- `@qa`;
- `@change-tracker`;
- aliases внешних modules из `CHAT_AGENT_MODULES`.

## Раздел "Администрирование"

Нужно добавить или расширить описание админки:

- LLM providers: создание, редактирование, тест;
- runtime default provider и runtime settings;
- agent overrides;
- agent prompt configs, версии и restore;
- LLM request logs;
- Vision test;
- Qdrant overview, project coverage, scenario probes, task resync;
- monitoring summary, activity, LLM metrics;
- audit feed;
- validation questions;
- task tags;
- users;
- project custom rules.

## Раздел "Frontend"

Фактическое описание:

- SPA на React 19, TypeScript и Vite;
- маршрутизация через React Router;
- access token хранится в Zustand store;
- refresh token хранится в `httpOnly` cookie;
- Axios client выполняет refresh queue;
- рабочие экраны реализованы собственными компонентами.

Маршруты, которые стоит перечислить:

- `/projects`;
- `/projects/:projectId/tasks`;
- `/projects/:projectId/tasks/new`;
- `/projects/:projectId/tasks/:taskId`;
- `/projects/:projectId/tasks/:taskId/chat`;
- `/admin/monitoring`;
- `/admin/qdrant`;
- `/admin/llm-requests`;
- `/admin/validation-questions`;
- `/admin/task-tags`;
- `/admin/providers`;
- `/admin/vision-test`;
- `/admin/agent-prompts`;
- `/admin/users`;
- `/admin/projects/:projectId/rules`.

## Раздел "Инфраструктура"

Нужно описать Compose-сервисы:

- `postgres`;
- `qdrant`;
- `ollama`;
- `ollama-init`;
- `migrate`;
- `backend`;
- `frontend`.

Важные детали:

- миграции выполняются отдельным сервисом `migrate`;
- backend стартует после миграций;
- frontend публикуется на `${FRONTEND_PORT:-8080}`;
- backend доступен через proxy с префиксом `/api`;
- health endpoints: `/healthz`;
- readiness endpoint: `/readyz`.

## Раздел "Качество и сопровождение"

Команды:

```bash
make backend-lint
make backend-test
make frontend-lint
make frontend-test
make frontend-build
make check
```

Прямые backend-проверки:

```bash
ruff check .
ruff format --check .
mypy .
pytest
```

Прямые frontend-проверки:

```bash
npm run lint
npm run typecheck
npm run test -- --run
npm run build
```

## Стиль и кодировка

Текст отчета должен быть техническим и конкретным:

- не обещать функции, которые зависят от недоступного провайдера или не включены настройками;
- не смешивать старую гипотезу архитектуры с фактической реализацией;
- писать коллекции Qdrant только как `task_knowledge`, `project_questions`, `task_proposals`;
- сохранять русские тексты в UTF-8;
- исправлять mojibake-строки при обнаружении;
- избегать маркетинговых формулировок вместо описания реальных потоков данных.

## Приоритет правок отчета

| Приоритет | Правка | Причина |
| --- | --- | --- |
| P0 | Везде описать AI-слой как LangGraph | Это обязательный источник гибкости проекта |
| P0 | Обновить стек | Старый стек противоречит текущим зависимостям |
| P0 | Уточнить RAG и Qdrant | Нужно отделить реализованное от условий работы Vision |
| P1 | Обновить workflow задачи | В коде есть разработка и тестирование как отдельные статусы |
| P1 | Добавить LLM runtime и админку | Это существенная часть текущего продукта |
| P1 | Обновить frontend-описание | UI реализован собственными React-компонентами |
| P2 | Добавить Docker Compose и проверки | Важно для воспроизводимого запуска |
| P2 | Проверить UTF-8 и терминологию | Требование качества русскоязычной документации |
