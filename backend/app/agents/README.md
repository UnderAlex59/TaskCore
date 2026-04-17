# Chat Agents

Chat agents are now pluggable.

## Fast path for a new agent

1. Add a new module in `app/agents/chat_agents/`.
2. Create a class that inherits from `BaseChatAgent`.
3. Add `metadata` with a unique `key`, human-readable `name`, optional `aliases`, and `priority`.
4. Decorate the class with `@register_chat_agent`.
5. Implement:
   - `can_handle(context)` for automatic routing
   - `handle(context)` for the final response
6. If the agent should call an LLM, use:
   - `self.get_llm_profile()` to inspect the resolved per-agent provider/model
   - `self.build_chat_model()` to construct the LangChain chat model

## Manual routing from chat

The chat supports explicit targeting:

- `@qa How should acceptance criteria look?`
- `@change Update the API contract`
- `@manager Save this note in the thread`

The prefix is stripped before the agent handles the content.

## External modules

If you want to keep agents outside `app/agents/chat_agents/`, set:

```env
CHAT_AGENT_MODULES=["your.package.agent_module"]
```

Each imported module can register one or more agents through the same decorator.

## Per-agent LLM provider overrides

Each agent can have its own provider and model, including a local Ollama runtime.

For OpenAI-compatible local endpoints such as LM Studio or vLLM, keep `provider: "openai"` and override `base_url` and `api_key` per agent.

Example:

```env
CHAT_AGENT_LLM_OVERRIDES={
  "qa": {
    "provider": "ollama",
    "model": "llama3.1",
    "base_url": "http://localhost:11434",
    "temperature": 0.1
  },
  "change-tracker": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.0
  }
}
```

Resolution order:

1. Agent default profile from code.
2. `CHAT_AGENT_LLM_OVERRIDES[agent_key]`.
3. Provider-specific global defaults like `OPENAI_MODEL`, `OLLAMA_MODEL`, `OPENAI_BASE_URL`, `OLLAMA_BASE_URL`.
