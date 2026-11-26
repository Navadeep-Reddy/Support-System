import json

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

from support_agent.agent.prompt import SYSTEM_PROMPT
from support_agent.schemas.conversation import MessageData
from support_agent.tools.support import tool_definitions

# Separate from the 8,192-token history budget, reserve space for current-turn
# results and for the configured 1,024-token model completion.
MODEL_OUTPUT_TOKENS = 1024
TOOL_RESULT_RESERVE_TOKENS = 4096


class ContextError(ValueError):
    pass


def validate_context_capacity(messages: list[BaseMessage], model_context_budget: int) -> None:
    schemas = json.dumps(
        [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.model_json_schema(),
            }
            for tool in tool_definitions()
        ]
    )
    estimated = count_tokens_approximately(
        [SystemMessage(content=SYSTEM_PROMPT), *messages, SystemMessage(content=schemas)]
    )
    if estimated + MODEL_OUTPUT_TOKENS + TOOL_RESULT_RESERVE_TOKENS > model_context_budget:
        raise ContextError("The request exceeds the model context limit.")


def prepare_context(
    history: list[MessageData], current_message: str, history_token_budget: int
) -> list[BaseMessage]:
    """Select recent complete user-visible turns; current input has a separate budget.

    Tool results from previous turns are intentionally absent. The model's system
    prompt, tool definitions, current tool results and output use separate capacity.
    """
    if not current_message.strip():
        raise ContextError("The message must not be blank.")
    current = HumanMessage(content=current_message)
    if count_tokens_approximately([current]) > history_token_budget:
        raise ContextError("The message exceeds the input limit.")

    groups: list[list[BaseMessage]] = []
    for item in history:
        if item.role == "user":
            groups.append([HumanMessage(content=item.content or "")])
        elif item.role == "assistant":
            if not groups:
                continue
            groups[-1].append(AIMessage(content=item.content or ""))
        elif item.approval is not None and groups:
            card = item.approval
            description = f"Password reset approval status: {card.status}."
            if card.result is not None:
                description += f" Simulated reset link: {card.result.reset_url}"
            groups[-1].append(AIMessage(content=description))

    selected: list[BaseMessage] = []
    for group in reversed(groups):
        candidate = group + selected
        if count_tokens_approximately(candidate) > history_token_budget:
            break
        selected = candidate
    return [*selected, current]
