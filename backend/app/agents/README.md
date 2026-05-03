# LangGraph Agents

`backend/app/agents` содержит agentic-слой проекта. Взаимодействие с ИИ идет через LangGraph и LangChain. Каждый сценарий оформлен как граф или subgraph, чтобы маршрутизация, расширение, тестирование и визуализация оставались управляемыми.

## Структура

```text
backend/app/agents/
|-- chat_agents/                  # базовые классы и registry чат-агентов
|-- attachment_vision_graph.py    # Vision-описание вложений
|-- change_tracker_agent_graph.py # обработка предложений изменений
|-- chat_graph.py                 # общий граф маршрутизации сообщений
|-- chat_routing.py               # forced routing и эвристики типа сообщения
|-- graph_export.py               # экспорт PNG/HTML схем графов
|-- manager_agent_graph.py        # fallback/manager subgraph
|-- provider_test_graph.py        # проверка LLM-провайдера
|-- qa_agent_graph.py             # ответы на вопросы по задаче
|-- rag_pipeline.py               # подготовка chunks для Qdrant
|-- state.py                      # TypedDict-состояния графов
|-- subgraph_registry.py          # регистрация и выбор subgraphs
|-- system_prompts.py             # системные prompt templates
|-- task_tag_suggestion_graph.py  # подсказки тегов задачи
|-- validation_graph.py           # валидация требований
`-- vision_test_graph.py          # админская проверка Vision
```

## Общий поток чата

1. Пользователь отправляет сообщение в задаче.
2. `ChatService` сохраняет сообщение.
3. Тип сообщения предварительно определяется как `general`, `question` или `change_proposal`.
4. `chat_graph` собирает `ChatAgentContext`.
5. Если сообщение начинается с agent prefix, включается forced routing.
6. Если forced routing нет, `subgraph_registry` вызывает `can_handle(context)` у зарегистрированных subgraphs.
7. Выбранный subgraph возвращает `ChatState`: ответ, `agent_name`, `message_type`, `source_ref`, иногда `proposal_text`.
8. `chat_graph` сохраняет связанные артефакты: agent message, change proposal или validation backlog question.
9. `ChatRealtimeService` публикует обновления через WebSocket.

## Forced routing

Forced routing нужен, когда пользователь явно указывает агента в сообщении. Поддерживаются built-in aliases, например:

- `@qa` - отправить сообщение в QA Agent.
- `@change-tracker` - извлечь предложение изменения.
- aliases внешних subgraphs, зарегистрированных через `CHAT_AGENT_MODULES`.

Если alias не найден, управление получает `ManagerAgent`, который возвращает понятный fallback-ответ.

## Встроенные graph/subgraph сценарии

### Chat Graph

Файл: `chat_graph.py`

Оркестрирует обработку сообщений. Граф не является отдельным "умным агентом": он собирает контекст, выбирает subgraph, запускает его и сохраняет результат.

### Manager Agent

Файл: `manager_agent_graph.py`

Fallback-subgraph. Используется, когда forced agent не найден или когда нужно объяснить маршрутизацию. Не заменяет QA, ChangeTracker или Validation.

### QA Agent

Файл: `qa_agent_graph.py`

Отвечает на вопросы по задаче. Использует:

- текущий текст задачи;
- результат последней валидации;
- похожие задачи из `task_knowledge`;
- вопросы и контекст из RAG;
- LLM runtime;
- `source_ref` для прозрачности ответа.

Если вопрос выявляет недостающий контекст, граф может сформировать вопрос для будущей валидации.

### ChangeTracker Agent

Файл: `change_tracker_agent_graph.py`

Извлекает предложение изменения из сообщения, проверяет дубли через `task_proposals`, формирует agent proposal и передает данные для сохранения в `change_proposals`.

### Validation Graph

Файл: `validation_graph.py`

Проверяет требование по нескольким блокам:

- нормализация входа;
- базовые критерии качества требования;
- кастомные правила проекта;
- контекстные вопросы из `project_questions`;
- агрегированный verdict `approved` или `needs_rework`;
- issues и уточняющие questions.

Результат сохраняется в `tasks.validation_result`, влияет на статус задачи и добавляется в контекст для RAG.

### RAG Pipeline

Файл: `rag_pipeline.py`

Готовит документы для Qdrant. Текущий контур работает с:

- заголовком;
- описанием;
- тегами;
- метаданными и извлеченным текстом вложений;
- `alt_text` для изображений, если Vision-обработка включена и доступна;
- результатом валидации.

Параметры chunking и вложений задаются через `RAG_CHUNK_TARGET_TOKENS`, `RAG_CHUNK_OVERLAP_TOKENS`, `RAG_ATTACHMENT_MAX_TEXT_CHARS`, `RAG_VISION_ENABLED`, `RAG_VISION_MAX_IMAGE_BYTES`.

### Attachment Vision Graph

Файл: `attachment_vision_graph.py`

Описывает изображение вложения через LLM runtime, если включен Vision-контур. Результат используется как `alt_text` и может попадать в RAG.

### Vision Test Graph

Файл: `vision_test_graph.py`

Админский тест Vision-провайдера. Используется страницей `/admin/vision-test` и endpoint `POST /admin/llm/vision-test`.

### Provider Test Graph

Файл: `provider_test_graph.py`

Проверяет LLM provider config из админки. Нужен для безопасной проверки ключей, base URL, модели и совместимости до включения провайдера в runtime.

### Task Tag Suggestion Graph

Файл: `task_tag_suggestion_graph.py`

Предлагает теги для задачи на основе текста, проекта и доступного справочника тегов.

## Qdrant-коллекции

- `task_knowledge` - индекс задач, результатов валидации, вложений и контекстных фрагментов.
- `project_questions` - вопросы, используемые как расширяемый чек-лист валидации.
- `task_proposals` - предложения изменений и база для поиска дублей.

Сервисный слой Qdrant находится в `app/services/qdrant_service.py` и `app/services/rag_service.py`.

## LLM runtime

Графы не должны напрямую создавать клиентов OpenAI, Ollama, GigaChat или OpenRouter. Вызовы идут через `LLMRuntimeService`, который учитывает:

- runtime default provider;
- provider configs из админки;
- agent overrides;
- prompt configs;
- model, temperature и provider-specific параметры;
- логирование запросов в `llm_request_logs`.

Такой слой позволяет переключать провайдеры без переписывания графов.

## Расширение внешними subgraphs

Внешний agent subgraph подключается через `CHAT_AGENT_MODULES`. Модуль импортируется при bootstrap и должен зарегистрировать `AgentSubgraphSpec` через `register_agent_subgraph(...)`.

Минимальный пример:

```python
from app.agents.chat_agents.base import ChatAgentContext, ChatAgentMetadata
from app.agents.state import ChatState
from app.agents.subgraph_registry import AgentSubgraphSpec, register_agent_subgraph


async def can_handle(context: ChatAgentContext) -> bool:
    return "#risk" in context.message_content.lower()


async def run_risk_agent(context: ChatAgentContext, routing_mode: str) -> ChatState:
    return {
        "agent_name": "RiskAgent",
        "message_type": "agent_answer",
        "response": "Нужно отдельно проверить риски требования.",
        "source_ref": {"collection": "messages"},
    }


register_agent_subgraph(
    AgentSubgraphSpec(
        metadata=ChatAgentMetadata(
            key="risk",
            name="RiskAgent",
            description="Анализирует риски по задаче.",
            aliases=("risk-review",),
            priority=40,
        ),
        can_handle=can_handle,
        runner=run_risk_agent,
    )
)
```

## Экспорт схем

`graph_export.py` экспортирует PNG/HTML-схемы графов в `LANGGRAPH_IMAGES_DIR`. В Docker Compose этот каталог монтируется в `./langgraph_graphs`, а backend раздает его через `/api/langgraph-images`.
