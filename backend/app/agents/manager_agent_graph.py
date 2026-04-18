from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agents.state import ChatState

MANAGER_AGENT_KEY = "manager"
MANAGER_AGENT_NAME = "ManagerAgent"
MANAGER_AGENT_DESCRIPTION = (
    "Резервный агент, который оставляет сообщение в треде и объясняет маршрутизацию."
)
MANAGER_AGENT_ALIASES = ("router", "default")


class ManagerGraphState(ChatState, total=False):
    requested_agent: str | None
    routing_mode: str


def _build_manager_response(state: ManagerGraphState) -> ManagerGraphState:
    requested_agent = state.get("requested_agent")
    routing_mode = str(state.get("routing_mode", "auto"))
    manager_aliases = {MANAGER_AGENT_KEY, *MANAGER_AGENT_ALIASES}

    if (
        requested_agent is not None
        and routing_mode == "forced"
        and requested_agent not in manager_aliases
    ):
        from app.agents.subgraph_registry import list_agent_subgraph_metadata

        available_agents = [
            {"key": item.key, "name": item.name}
            for item in list_agent_subgraph_metadata()
        ]
        available_keys = ", ".join(item["key"] for item in available_agents)
        return {
            "agent_name": MANAGER_AGENT_NAME,
            "message_type": "agent_answer",
            "response": (
                f"Agent '{requested_agent}' не зарегистрирован. "
                f"Доступные агенты: {available_keys}."
            ),
            "source_ref": {
                "collection": "messages",
                "routing_mode": "forced",
                "requested_agent": requested_agent,
                "available_agents": available_agents,
                "agent_key": MANAGER_AGENT_KEY,
                "agent_description": MANAGER_AGENT_DESCRIPTION,
            },
        }

    response = (
        "Сообщение сохранено в обсуждении. Чтобы получить автоматический ответ, "
        "сформулируйте вопрос или явное предложение по изменению требования."
    )
    if requested_agent is None:
        response += (
            " При необходимости можно явно выбрать агента через префикс вида "
            "`@qa` или `@change-tracker`."
        )

    return {
        "agent_name": MANAGER_AGENT_NAME,
        "message_type": "agent_answer",
        "response": response,
        "source_ref": {
            "collection": "messages",
            "routing_mode": routing_mode,
            "agent_key": MANAGER_AGENT_KEY,
            "agent_description": MANAGER_AGENT_DESCRIPTION,
        },
    }


@lru_cache
def get_manager_agent_graph():
    graph = StateGraph(ManagerGraphState)
    graph.add_node("build_manager_response", _build_manager_response)
    graph.add_edge(START, "build_manager_response")
    graph.add_edge("build_manager_response", END)
    return graph.compile()


async def run_manager_agent_graph(
    *,
    requested_agent: str | None,
    routing_mode: str,
) -> ChatState:
    state = await get_manager_agent_graph().ainvoke(
        {
            "requested_agent": requested_agent,
            "routing_mode": routing_mode,
        }
    )
    return {
        "agent_name": str(state.get("agent_name", MANAGER_AGENT_NAME)),
        "message_type": str(state.get("message_type", "agent_answer")),
        "response": str(state.get("response", "")),
        "source_ref": dict(state.get("source_ref", {})),
    }
