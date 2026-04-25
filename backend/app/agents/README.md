# LangGraph Agents

Этот модуль содержит agentic-слой проекта. Взаимодействие с ИИ в текущей реализации идет через LangGraph, а не через CrewAI. Каждый сценарий оформлен как граф или subgraph, что упрощает маршрутизацию, расширение и визуализацию.

## Структура

```text
backend/app/agents/
├── chat_agents/                  # базовые классы и registry чат-агентов
├── change_tracker_agent_graph.py # обработка предложений изменений
├── chat_graph.py                 # общий граф маршрутизации сообщений
├── chat_routing.py               # эвристики и routing helpers
├── graph_export.py               # экспорт PNG/HTML схем графов
├── manager_agent_graph.py        # fallback/manager subgraph
├── provider_test_graph.py        # проверка LLM-провайдера
├── qa_agent_graph.py             # ответы на вопросы по задаче
├── rag_pipeline.py               # подготовка chunks для Qdrant
├── state.py                      # TypedDict-состояния графов
├── subgraph_registry.py          # регистрация и выбор subgraphs
└── validation_graph.py           # валидация требований
```

## Основной поток чата

1. Пользователь отправляет сообщение в задаче.
2. `ChatService` сохраняет сообщение и определяет грубый тип: `general`, `question`, `change_proposal`.
3. `chat_graph` готовит контекст и выбирает agent subgraph.
4. Если пользователь указал префикс `@qa`, `@change-tracker` или другой alias, используется forced routing.
5. Если префикса нет, registry вызывает `can_handle(context)` у зарегистрированных subgraphs.
6. Выбранный subgraph возвращает ответ, source reference и при необходимости `proposal_text`.
7. `chat_graph` сохраняет связанные артефакты: change proposal или validation backlog question.
8. Ответ агента публикуется в чат через WebSocket.

## Встроенные subgraphs

### Manager Agent

Файл: `manager_agent_graph.py`

Fallback-агент. Используется, когда forced agent не найден или когда нужен системный ответ о маршрутизации. Не заменяет основную бизнес-логику чата.

### QA Agent

Файл: `qa_agent_graph.py`

Отвечает на вопросы по требованиям и контексту задачи. Использует:

- текст текущей задачи;
- результат валидации;
- похожие задачи из `task_knowledge`;
- LLM runtime;
- source references для прозрачности ответа.

Если вопрос выявляет недостающий контекст, граф может передать вопрос в backlog валидации.

### ChangeTracker Agent

Файл: `change_tracker_agent_graph.py`

Выделяет предложение изменения из сообщения, проверяет дубли через `task_proposals`, формирует agent proposal и передает данные для сохранения в `change_proposals`.

### Validation Graph

Файл: `validation_graph.py`

Проверяет задачу по трем блокам:

- базовые критерии качества требования;
- кастомные правила проекта;
- контекстные вопросы из `project_questions` и похожие задачи.

Граф возвращает `approved` или `needs_rework`, список issues и уточняющие questions.

### RAG Pipeline

Файл: `rag_pipeline.py`

Готовит документы для Qdrant. Текущая реализация формирует chunks из:

- заголовка;
- основного текста;
- тегов;
- метаданных вложений;
- результата валидации.

Важно: полноценная интерпретация изображений Vision-моделью и chunking по 300-500 токенов пока не реализованы как отдельные шаги. Если это нужно описывать в отчете, следует писать как план развития, а не как уже готовую функцию.

## Qdrant-коллекции

- `task_knowledge` - знания о задачах и результатах валидации.
- `project_questions` - вопросы, которые используются как расширяемый чек-лист валидации.
- `task_proposals` - предложения изменений и поиск дублей.

## Расширение внешними агентами

Внешний agent subgraph можно подключить через `CHAT_AGENT_MODULES`. Модуль должен импортироваться при bootstrap и зарегистрировать `AgentSubgraphSpec` через `register_agent_subgraph(...)`.

Минимальная структура:

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

## LLM runtime

Графы не обращаются напрямую к конкретному провайдеру. Вызовы идут через `LLMRuntimeService`, который учитывает:

- дефолтный provider;
- provider configs из админки;
- agent overrides;
- provider default из админ-панели;
- параметры модели и температуры.

Это позволяет переключать агенты между OpenAI, Ollama, OpenRouter, GigaChat и OpenAI-compatible API без переписывания графов.
