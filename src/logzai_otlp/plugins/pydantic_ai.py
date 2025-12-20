"""
LogzAI plugin for PydanticAI agents.
Instruments Agent.run() and Agent.run_sync() to automatically log usage and messages.

Note: pydantic_ai is imported only when the plugin is registered,
making it an optional dependency.
"""
from typing import Optional, Any
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


def pydantic_ai_plugin(instance, config: Optional[dict] = None):
    """
    LogzAI plugin for PydanticAI agents.

    Patches Agent.run() and Agent.run_sync() to automatically log usage and messages.
    Uses spans to track execution time.

    Args:
        instance: LogzAI instance
        config: Optional configuration dict with keys:
            - include_messages: bool (default: True) - whether to include full message history

    Returns:
        Cleanup function that restores original Agent methods

    Raises:
        ImportError: If pydantic_ai is not installed

    Example:
        from logzai_otlp import logzai, pydantic_ai_plugin

        logzai.init(ingest_token="token", ingest_endpoint="http://localhost")
        logzai.plugin('pydantic-ai', pydantic_ai_plugin, {"include_messages": True})

        # Now all Agent.run() calls are automatically logged with spans
        agent = Agent(model=model, instructions="...")
        result = await agent.run("Hello")
    """
    # Import pydantic_ai only when plugin is registered (optional dependency)
    try:
        from pydantic_ai import Agent
        from pydantic_ai import messages as _messages
    except ImportError as e:
        raise ImportError(
            "pydantic_ai is required to use the pydantic_ai_plugin. "
            "Install it with: pip install pydantic-ai"
        ) from e

    # Get config options
    include_messages = config.get("include_messages", True) if config else True

    # Helper functions for extracting data from PydanticAI results
    def extract_model_info(result) -> tuple[str | None, str | None]:
        """Extract model name and provider from the last ModelResponse."""
        for msg in reversed(result.all_messages()):
            if isinstance(msg, _messages.ModelResponse):
                return msg.model_name, msg.provider_name
        return None, None

    def extract_messages(result) -> list[Message]:
        """
        Extract messages from PydanticAI result in OpenAI-style format.
        Handles: system prompts, user messages, assistant responses, tool calls, and tool results.
        """
        extracted: list[Message] = []
        seen_instructions = False

        for msg in result.all_messages():
            if isinstance(msg, _messages.ModelRequest):
                # Handle instructions (system prompt) - only add once
                if msg.instructions and not seen_instructions:
                    extracted.append(Message(role="system", content=msg.instructions))
                    seen_instructions = True

                # Handle message parts
                for part in msg.parts:
                    if isinstance(part, _messages.SystemPromptPart):
                        extracted.append(Message(role="system", content=part.content))

                    elif isinstance(part, _messages.UserPromptPart):
                        content = part.content if isinstance(part.content, str) else str(part.content)
                        extracted.append(Message(role="user", content=content))

                    elif isinstance(part, _messages.ToolReturnPart):
                        # Tool result message
                        extracted.append(Message(
                            role="tool",
                            content=str(part.content),
                            tool_call_id=part.tool_call_id,
                            tool_name=part.tool_name
                        ))

            elif isinstance(msg, _messages.ModelResponse):
                # Collect text parts and tool calls separately
                text_parts = []
                tool_calls = []

                for part in msg.parts:
                    if isinstance(part, _messages.TextPart):
                        text_parts.append(part.content)

                    elif isinstance(part, _messages.ToolCallPart):
                        tool_calls.append(ToolCall(
                            id=part.tool_call_id,
                            name=part.tool_name,
                            arguments=part.args_as_json_str()
                        ))

                # Create assistant message
                text_content = "".join(text_parts) if text_parts else None

                if text_content or tool_calls:
                    extracted.append(Message(
                        role="assistant",
                        content=text_content,
                        tool_calls=tool_calls if tool_calls else None
                    ))

        return extracted

    # Store original methods before patching
    original_run = Agent.run
    original_run_sync = Agent.run_sync

    async def instrumented_run(self, *args, **kwargs):
        """Wrapped async run method that captures agent execution."""
        user_prompt = args[0] if args else kwargs.get('user_prompt', '')
        agent_name = getattr(self, 'name', 'unnamed_agent')

        # Create span for agent execution
        with instance.span(f"pydantic_ai.agent.run") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("agent.prompt", user_prompt if isinstance(user_prompt, str) else str(user_prompt))

            try:
                # Call original run method
                result = await original_run(self, *args, **kwargs)

                # Extract usage information
                messages = extract_messages(result)
                model_name, provider = extract_model_info(result)

                usage = Usage(
                    model=model_name,
                    provider=provider,
                    input_tokens=result.usage().input_tokens,
                    output_tokens=result.usage().output_tokens,
                    total_tokens=result.usage().total_tokens,
                    messages=messages
                )

                # Add span attributes
                span.set_attribute("agent.model", usage.model or "unknown")
                span.set_attribute("agent.provider", usage.provider or "unknown")
                span.set_attribute("agent.input_tokens", usage.input_tokens)
                span.set_attribute("agent.output_tokens", usage.output_tokens)
                span.set_attribute("agent.total_tokens", usage.total_tokens)

                # Log to LogzAI
                log_data = {
                    "event": "pydantic_ai.agent.run",
                    "model": usage.model,
                    "provider": usage.provider,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "user_prompt": user_prompt if isinstance(user_prompt, str) else str(user_prompt),
                    "agent_name": agent_name,
                }

                # Optionally include full message history
                if include_messages:
                    log_data["messages"] = [msg.model_dump() for msg in usage.messages]

                instance.info(
                    f"PydanticAI agent completed: {usage.total_tokens} tokens",
                    **log_data
                )

                return result

            except Exception as e:
                # Log error
                instance.error(
                    f"PydanticAI agent error: {str(e)}",
                    event="pydantic_ai.agent.error",
                    user_prompt=user_prompt if isinstance(user_prompt, str) else str(user_prompt),
                    error=str(e),
                    exc_info=True
                )
                raise

    def instrumented_run_sync(self, *args, **kwargs):
        """Wrapped sync run method."""
        user_prompt = args[0] if args else kwargs.get('user_prompt', '')
        agent_name = getattr(self, 'name', 'unnamed_agent')

        # Create span for agent execution
        with instance.span(f"pydantic_ai.agent.run_sync") as span:
            span.set_attribute("agent.name", agent_name)
            span.set_attribute("agent.prompt", user_prompt if isinstance(user_prompt, str) else str(user_prompt))

            try:
                # Call original run_sync method
                result = original_run_sync(self, *args, **kwargs)

                # Extract usage information
                messages = extract_messages(result)
                model_name, provider = extract_model_info(result)

                usage = Usage(
                    model=model_name,
                    provider=provider,
                    input_tokens=result.usage().input_tokens,
                    output_tokens=result.usage().output_tokens,
                    total_tokens=result.usage().total_tokens,
                    messages=messages
                )

                # Add span attributes
                span.set_attribute("agent.model", usage.model or "unknown")
                span.set_attribute("agent.provider", usage.provider or "unknown")
                span.set_attribute("agent.input_tokens", usage.input_tokens)
                span.set_attribute("agent.output_tokens", usage.output_tokens)
                span.set_attribute("agent.total_tokens", usage.total_tokens)

                # Log to LogzAI
                log_data = {
                    "event": "pydantic_ai.agent.run_sync",
                    "model": usage.model,
                    "provider": usage.provider,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                    "user_prompt": user_prompt if isinstance(user_prompt, str) else str(user_prompt),
                    "agent_name": agent_name,
                }

                # Optionally include full message history
                if include_messages:
                    log_data["messages"] = [msg.model_dump() for msg in usage.messages]

                instance.info(
                    f"PydanticAI agent completed (sync): {usage.total_tokens} tokens",
                    **log_data
                )

                return result

            except Exception as e:
                # Log error
                instance.error(
                    f"PydanticAI agent error (sync): {str(e)}",
                    event="pydantic_ai.agent.error",
                    user_prompt=user_prompt if isinstance(user_prompt, str) else str(user_prompt),
                    error=str(e),
                    exc_info=True
                )
                raise

    # Monkey-patch the Agent class
    Agent.run = instrumented_run
    Agent.run_sync = instrumented_run_sync

    # Return cleanup function
    def cleanup():
        """Restore original Agent methods."""
        Agent.run = original_run
        Agent.run_sync = original_run_sync

    return cleanup
