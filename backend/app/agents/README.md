# Agent Graphs

Проект использует `subgraph-per-agent` как основной способ orchestration для AI-сценариев.

## Встроенные agent subgraphs

Встроенные чат-агенты оформлены как отдельные LangGraph subgraphs:

- `qa_agent_graph`
- `change_tracker_agent_graph`
- `manager_agent_graph`

Главный `chat_graph` не вызывает `handle()` напрямую. Он:

1. собирает `ChatAgentContext`
2. выбирает подходящий agent subgraph через `subgraph_registry`
3. запускает subgraph runner
4. затем выполняет общие persistence side-effects

## External agent subgraphs

Внешние агенты теперь тоже можно подключать без возврата к старому `dispatch_chat_agent`-подходу.

Для этого внешний модуль должен:

1. импортироваться через `CHAT_AGENT_MODULES`
2. зарегистрировать `AgentSubgraphSpec` через `register_agent_subgraph(...)`
3. предоставить:
   - `metadata`
   - `runner(context, routing_mode)`
   - `can_handle(context)` для auto-routing
   - при необходимости `graph_factory` для экспорта диаграмм
   - при необходимости `llm_profile` для bootstrap per-agent provider overrides

Минимальный пример:

```python
from app.agents.chat_agents.base import ChatAgentContext, ChatAgentMetadata
from app.agents.chat_agents.llm import ChatAgentLLMProfile
from app.agents.state import ChatState
from app.agents.subgraph_registry import AgentSubgraphSpec, register_agent_subgraph


async def can_handle(context: ChatAgentContext) -> bool:
    return context.message_type == "question" and "#risk" in context.message_content.lower()


async def run_risk_agent(context: ChatAgentContext, routing_mode: str) -> ChatState:
    return {
        "agent_name": "RiskAgent",
        "message_type": "agent_answer",
        "response": "Нужен отдельный анализ рисков.",
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
        llm_profile=ChatAgentLLMProfile(
            provider="openai",
            model="gpt-4o-mini",
            temperature=0.1,
        ),
    )
)
```

## Routing

Поддерживаются оба режима:

- auto-routing через `can_handle(context)`
- forced routing через префиксы вида `@qa`, `@change-tracker`, `@risk`

Если requested agent не найден, управление уходит в `ManagerAgent`, который возвращает список зарегистрированных subgraphs.

## LLM overrides

`LLMRuntimeService` теперь bootstrap-ит provider overrides по `subgraph_registry`, а не по старому chat-agent dispatch registry. Это значит, что внешние agent subgraphs тоже могут иметь собственный `llm_profile` и собственные настройки через `CHAT_AGENT_LLM_OVERRIDES`.
