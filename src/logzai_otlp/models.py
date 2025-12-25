from pydantic import BaseModel


class ToolCall(BaseModel):
    """Represents a tool call made by the assistant."""

    id: str
    name: str
    arguments: str  # JSON string of arguments


class Message(BaseModel):
    """
    OpenAI-style message format supporting text, tool calls, and tool results.

    Roles:
    - system: System prompt/instructions
    - user: User input
    - assistant: Model response (can include tool_calls)
    - tool: Tool execution result
    """

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None

    # For assistant messages that call tools
    tool_calls: list[ToolCall] | None = None

    # For tool messages (results)
    tool_call_id: str | None = None
    tool_name: str | None = None


class Usage(BaseModel):
    model: str | None = None
    provider: str | None = None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    messages: list[Message]
