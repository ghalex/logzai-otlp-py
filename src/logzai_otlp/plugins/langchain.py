"""
LangChain plugin for LogzAI OTLP.

This plugin activates LangChain's built-in OpenTelemetry instrumentation by setting
environment variables before LangChain is imported. LangChain will then automatically
use the global TracerProvider configured by logzai.init().
"""

import os
import sys
import json
from typing import Optional

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from typing import Sequence

from ..plugins import CleanupFunction


def _convert_langchain_messages_to_openai_format(messages_list: list) -> list:
    """
    Convert LangChain message format to OpenAI-style format.

    LangChain format uses:
    - type: "human", "ai", "tool", "system"
    - content: message content
    - tool_calls: array of tool calls (for AI messages)
    - tool_call_id: ID of the tool call (for tool messages)
    - name: tool name (for tool messages)

    OpenAI format uses:
    - role: "system", "user", "assistant", "tool"
    - content: message content (optional)
    - tool_calls: array of tool calls (for assistant, optional)
    - tool_call_id: ID of the tool call (for tool, optional)
    - tool_name: tool name (for tool, optional)
    """
    openai_messages = []

    for msg in messages_list:
        msg_type = msg.get("type")
        content = msg.get("content", "")

        if msg_type == "system":
            openai_messages.append({"role": "system", "content": content})
        elif msg_type == "human":
            openai_messages.append({"role": "user", "content": content})
        elif msg_type == "ai":
            # AI messages might have tool calls
            message = {"role": "assistant"}

            # Only add content if it's non-empty
            if content:
                message["content"] = content

            # Add tool calls if present
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                message["tool_calls"] = [  # type: ignore
                    {
                        "id": tc.get("id"),
                        "name": tc.get("name"),
                        "arguments": tc.get("args", {}),
                    }
                    for tc in tool_calls
                ]

            openai_messages.append(message)
        elif msg_type == "tool":
            openai_messages.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": msg.get("tool_call_id"),
                    "tool_name": msg.get("name"),
                }
            )

    return openai_messages


class LangChainSpanExporterWrapper(SpanExporter):
    """
    Wrapper for span exporters that modifies LangChain spans before export.

    This wrapper intercepts spans before they're exported and:
    - Adds type="ai" attribute to LangChain spans
    - Extracts and normalizes messages from gen_ai.prompt and gen_ai.completion
    - Stores normalized messages in gen_ai.messages attribute
    """

    def __init__(
        self,
        wrapped_exporter: SpanExporter,
        add_type: bool = True,
        include_messages: bool = True,
    ):
        self.wrapped_exporter = wrapped_exporter
        self.add_type = add_type
        self.include_messages = include_messages

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans after modifying LangChain-specific attributes."""
        for span in spans:
            # Check if this is a LangChain span
            # LangChain's OTEL instrumentation uses "langsmith" as the scope name
            is_langchain = False
            if span.instrumentation_scope and span.instrumentation_scope.name:
                scope_name = span.instrumentation_scope.name.lower()
                is_langchain = (
                    "langchain" in scope_name
                    or "langgraph" in scope_name
                    or "langsmith" in scope_name
                )

            if is_langchain and span.attributes:
                # Add type="ai" attribute
                if self.add_type and "type" not in span.attributes:
                    try:
                        # Access internal attributes dict to add the type attribute
                        if hasattr(span, "_attributes"):
                            span._attributes["type"] = "ai"  # type: ignore
                        elif hasattr(span, "attributes") and hasattr(
                            span.attributes, "_mapping"
                        ):
                            span.attributes._mapping["type"] = "ai"  # type: ignore
                    except (AttributeError, TypeError):
                        pass

                # Extract and normalize messages from gen_ai.prompt and gen_ai.completion
                if self.include_messages:
                    try:
                        all_messages = []

                        # Access span.attributes - it's a BoundedAttributes object with dict-like access
                        attrs = span.attributes

                        # Extract prompt messages (user input)
                        prompt_attr = (
                            attrs.get("gen_ai.prompt")
                            if hasattr(attrs, "get")
                            else None
                        )

                        if prompt_attr:
                            # prompt_attr could be a string (JSON) or already a dict
                            if isinstance(prompt_attr, str):
                                try:
                                    prompt_data = json.loads(prompt_attr)
                                except json.JSONDecodeError:
                                    prompt_data = None
                            else:
                                prompt_data = prompt_attr

                            if isinstance(prompt_data, dict):
                                prompt_messages = prompt_data.get("messages", [])
                                all_messages.extend(prompt_messages)

                        # Extract completion messages (AI responses, tool calls, tool results)
                        completion_attr = (
                            attrs.get("gen_ai.completion")
                            if hasattr(attrs, "get")
                            else None
                        )

                        if completion_attr:
                            # completion_attr could be a string (JSON) or already a dict
                            if isinstance(completion_attr, str):
                                try:
                                    completion_data = json.loads(completion_attr)
                                except json.JSONDecodeError:
                                    completion_data = None
                            else:
                                completion_data = completion_attr

                            if isinstance(completion_data, dict):
                                completion_messages = completion_data.get(
                                    "messages", []
                                )
                                all_messages.extend(completion_messages)

                        # Convert to OpenAI format if we have messages
                        if all_messages:
                            openai_messages = (
                                _convert_langchain_messages_to_openai_format(
                                    all_messages
                                )
                            )

                            # Store in gen_ai.messages attribute as JSON string (for backend parsing)
                            messages_json = json.dumps(openai_messages or {})
                            if hasattr(span, "_attributes"):
                                span._attributes["gen_ai.messages"] = messages_json  # type: ignore
                            elif hasattr(span, "attributes") and hasattr(
                                span.attributes, "_mapping"
                            ):
                                span.attributes._mapping["gen_ai.messages"] = (  # type: ignore
                                    messages_json  # type: ignore
                                )

                    except (json.JSONDecodeError, KeyError, AttributeError, TypeError):
                        # If message extraction fails, continue without messages
                        pass

        return self.wrapped_exporter.export(spans)

    def shutdown(self) -> None:
        """Shutdown the wrapped exporter."""
        return self.wrapped_exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush the wrapped exporter."""
        return self.wrapped_exporter.force_flush(timeout_millis)


def langchain_plugin(
    instance, config: Optional[dict] = None
) -> Optional[CleanupFunction]:
    """
    LogzAI plugin for LangChain applications.

    This plugin activates LangChain's built-in OpenTelemetry instrumentation
    by setting both LANGSMITH_TRACING=true and LANGSMITH_OTEL_ENABLED=true.
    LangChain will then automatically use the global TracerProvider configured
    by logzai.init().

    To prevent LangSmith error messages from appearing in the console, the plugin
    suppresses logging from the 'langsmith' and 'opentelemetry' modules. This way
    we get clean OpenTelemetry traces to LogzAI without LangSmith backend errors.

    IMPORTANT: Register this plugin AFTER logzai.init() but BEFORE importing
    langchain or langgraph for best results.

    Args:
        instance: LogzAI instance
        config: Optional configuration dict with keys:
            - add_type_attribute: bool (default: True) - Add type="ai" to LangChain spans
            - include_messages: bool (default: True) - Include message history in gen_ai.messages
            - warn_if_late: bool (default: True) - Warn if LangChain already imported

    Returns:
        Cleanup function that restores environment variables and removes processors

    Example:
        ```python
        import os
        import dotenv

        dotenv.load_dotenv()

        from logzai_otlp import logzai
        from logzai_otlp.plugins import langchain_plugin

        # Initialize LogzAI first
        logzai.init(
            ingest_token=os.getenv('LOGZAI_TOKEN'),
            ingest_endpoint=os.getenv('LOGZAI_ENDPOINT'),
            service_name="langchain-example",
            environment="dev"
        )

        # Register plugin BEFORE importing LangChain
        logzai.plugin('langchain', langchain_plugin, {
            "add_type_attribute": True
        })

        # NOW import and use LangChain
        from langchain_openai import ChatOpenAI
        from langchain.agents import create_agent
        # ... agent usage automatically traced
        ```
    """
    # Validate config
    if config is None:
        config = {}

    add_type_attribute = config.get("add_type_attribute", True)
    include_messages = config.get("include_messages", True)
    warn_if_late = config.get("warn_if_late", True)

    # Check if LangChain already imported
    langchain_modules = [
        m for m in sys.modules.keys() if m.startswith(("langchain", "langgraph"))
    ]

    if langchain_modules and warn_if_late:
        instance.warning(
            "LangChain/LangGraph already imported before plugin registration. "
            "Environment variables may not take effect properly. "
            "For best results, register this plugin BEFORE importing langchain or langgraph.",
            event="langchain.plugin.late_registration",
            imported_modules=langchain_modules[:5],  # Show first 5 modules
        )

    # Store original environment variables for cleanup
    original_otel_enabled = os.environ.get("LANGSMITH_OTEL_ENABLED")
    original_tracing = os.environ.get("LANGSMITH_TRACING")

    # Set environment variables to activate LangChain's OTEL instrumentation
    # IMPORTANT: We need BOTH variables:
    # - LANGSMITH_TRACING=true: Activates the tracing system
    # - LANGSMITH_OTEL_ENABLED=true: Enables OpenTelemetry export within that system
    os.environ["LANGSMITH_OTEL_ENABLED"] = "true"
    os.environ["LANGSMITH_TRACING"] = "true"

    # Suppress LangSmith error messages by adjusting logging levels
    # This prevents connection errors from showing in console while keeping OTEL working
    import logging
    import warnings

    # Suppress LangSmith warnings and errors completely
    langsmith_logger = logging.getLogger("langsmith")
    langsmith_logger.setLevel(logging.CRITICAL + 10)  # Completely suppress all messages

    # Suppress OpenTelemetry warnings about mixed types
    otel_logger = logging.getLogger("opentelemetry")
    otel_logger.setLevel(logging.ERROR)  # Only show errors, not warnings

    # Suppress all warnings from langsmith and opentelemetry modules
    warnings.filterwarnings("ignore", module="langsmith")
    warnings.filterwarnings("ignore", module="opentelemetry")
    warnings.filterwarnings("ignore", message=".*langsmith.*")
    warnings.filterwarnings("ignore", message=".*mixes types.*")

    # instance.debug(
    #     "LangChain plugin: environment variables set",
    #     event="langchain.plugin.env_vars_set",
    #     LANGSMITH_OTEL_ENABLED="true",
    #     LANGSMITH_TRACING="true",
    # )

    # Store references for cleanup
    wrapped_exporters = []

    if not instance.tracer_provider:
        instance.warning(
            "LogzAI not initialized. Call logzai.init() before registering plugins.",
            event="langchain.plugin.not_initialized",
        )
    else:
        # Wrap all existing span exporters to modify gen_ai.prompt and gen_ai.completion
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        for (
            processor
        ) in instance.tracer_provider._active_span_processor._span_processors:  # type: ignore
            if isinstance(processor, BatchSpanProcessor):
                # BatchSpanProcessor wraps a BatchProcessor which holds the actual exporter
                # We need to modify the exporter in the BatchProcessor
                batch_processor = processor._batch_processor  # type: ignore
                original_exporter = batch_processor._exporter  # type: ignore
                wrapped_exporter = LangChainSpanExporterWrapper(
                    original_exporter,  # type: ignore
                    add_type=add_type_attribute,  # type: ignore
                    include_messages=include_messages,  # type: ignore
                )
                # Replace the exporter in the BatchProcessor
                batch_processor._exporter = wrapped_exporter  # type: ignore
                wrapped_exporters.append((batch_processor, original_exporter))

        # instance.debug(
        #     "LangChain plugin: exporter wrapper added",
        #     event="langchain.plugin.wrapper_added",
        #     add_type_attribute=add_type_attribute,
        #     wrapped_count=len(wrapped_exporters),
        # )

    def cleanup():
        """Restore environment variables, exporters, and remove custom span processor."""
        # Restore original exporters
        for batch_processor, original_exporter in wrapped_exporters:
            batch_processor._exporter = original_exporter  # type: ignore

        # Restore LANGSMITH_OTEL_ENABLED
        if original_otel_enabled is not None:
            os.environ["LANGSMITH_OTEL_ENABLED"] = original_otel_enabled
        else:
            os.environ.pop("LANGSMITH_OTEL_ENABLED", None)

        # Restore LANGSMITH_TRACING
        if original_tracing is not None:
            os.environ["LANGSMITH_TRACING"] = original_tracing
        else:
            os.environ.pop("LANGSMITH_TRACING", None)

        # Note: We intentionally do NOT restore the logging levels for langsmith/opentelemetry
        # to prevent error messages during shutdown. The suppression remains active.

        # Note: OpenTelemetry SDK doesn't provide remove_span_processor,
        # but the processor will be cleaned up when the provider is shut down

        # instance.debug(
        #     "LangChain plugin cleanup completed", event="langchain.plugin.cleanup"
        # )

    return cleanup
