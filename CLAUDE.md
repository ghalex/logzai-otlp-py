# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`logzai-otlp` is a lightweight OpenTelemetry logging and tracing client for LogzAI. It provides:
- Structured logging with OTLP export (HTTP or gRPC)
- Distributed tracing with spans
- Plugin system for framework integrations (FastAPI, PydanticAI)
- Graceful shutdown with automatic buffer flushing

## Development Commands

### Package Management
This project uses `uv` for dependency management:
```bash
# Install dependencies
uv sync

# Add a new dependency
uv add <package-name>

# Add a dev dependency
uv add --dev <package-name>

# Run Python with project dependencies
uv run python <script.py>
```

### Building and Publishing
```bash
# Build source distribution and wheel
uv run python -m build

# Publish to PyPI
./scripts/release.sh

# Publish to TestPyPI (for testing)
./scripts/release.sh --test
```

The release script automatically:
1. Cleans previous build artifacts
2. Builds sdist and wheel
3. Verifies artifacts with twine
4. Uploads to PyPI/TestPyPI

### Running Examples
```bash
# FastAPI example (requires FastAPI)
uv run examples/fastapi_example.py

# PydanticAI example (requires pydantic-ai)
uv run examples/pydantic_ai_example.py
```

## Architecture

### Core Components

**`src/logzai_otlp/main.py`**: Contains the main `LogzAI` class and singleton `logzai` instance.
- `LogzAI` class handles both logging (via OpenTelemetry LoggerProvider) and tracing (via TracerProvider)
- Singleton pattern: `logzai` is the default instance used throughout the library
- Supports both HTTP and gRPC OTLP protocols

**Key initialization flow**:
1. `logzai.init()` creates OTLP exporters (log + trace) with custom headers
2. Sets up OpenTelemetry providers with resource attributes (service name, namespace, environment)
3. Automatically appends `/logs` and `/traces` to the base endpoint URL
4. Registers providers globally so all logging/tracing flows through OTLP

### Plugin System

**`src/logzai_otlp/plugins/`**: Extensible plugin architecture for framework integrations.

**Plugin Lifecycle**:
1. Plugins are registered via `logzai.plugin(name, plugin_func, config)`
2. Plugin function executes immediately and can return an optional cleanup function
3. Cleanup functions (sync or async) are called during `logzai.shutdown()` in LIFO order
4. Plugins can monkey-patch classes, add middleware, or extend the `LogzAI` instance

**Standard Attributes Pattern**:
Both built-in plugins follow a convention of setting a `type` attribute on spans and log events:
- `type="http"` for HTTP requests (FastAPI plugin)
- `type="ai"` for AI agent calls (PydanticAI plugin)

This enables filtering and categorization in the LogzAI backend.

**OpenTelemetry Semantic Conventions Compliance**:
- **PydanticAI plugin**: Follows [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) using `gen_ai.*` attributes for model, provider, and token usage
- **FastAPI plugin**: Follows standard HTTP semantic conventions using `http.*` attributes
- **Custom attributes**: Both plugins add custom attributes (like `type`) for LogzAI-specific features while maintaining OTel compatibility

#### FastAPI Plugin (`plugins/fastapi.py`)

**What it does**:
- Adds Starlette middleware to create a span for each HTTP request
- Span name format: `{METHOD} → {route}` (e.g., `POST → /login`)
- **Selective logging**: Only creates log entries for errors (status >= 400) or slow requests (>= threshold)
- Sets comprehensive span attributes for all requests

**Span attributes captured**:
- `type="http"` - Request type identifier
- `http.method`, `http.route`, `http.url`, `http.scheme`, `http.host` - Request details
- `http.status_code`, `http.duration_ms` - Response details
- `http.client.ip`, `http.user_agent` - Client info
- `http.request.header.{name}`, `http.response.header.{name}` - Headers (if enabled)
  - Headers are normalized: lowercase with hyphens → underscores (e.g., `content-type` → `http.request.header.content_type`)

**Configuration options**:
```python
logzai.plugin('fastapi', fastapi_plugin, {
    "app": app,  # Required: FastAPI app instance
    "log_request_body": False,  # Capture request body in logs
    "log_response_body": False,  # Capture response body in logs
    "log_request_headers": False,  # Capture all request headers as span attributes
    "log_response_headers": False,  # Capture all response headers as span attributes
    "slow_request_threshold_ms": 1000  # Log warning for requests exceeding this duration
})
```

**Implementation details**:
- Uses `BaseHTTPMiddleware` inserted at position 0 (runs first)
- Timing starts before request processing, ends after response
- Request body reading is handled carefully to avoid consuming the stream
- Cleanup removes middleware and rebuilds FastAPI's middleware stack

#### PydanticAI Plugin (`plugins/pydantic_ai.py`)

**What it does**:
- Monkey-patches `Agent.run()` and `Agent.run_sync()` methods
- Creates a span for each agent execution: `pydantic_ai.agent.run` or `pydantic_ai.agent.run_sync`
- Extracts and logs token usage, model info, and message history
- Converts PydanticAI message format to OpenAI-style format for consistent logging

**Span attributes captured**:

OpenTelemetry GenAI semantic conventions (standard):
- `gen_ai.operation.name="chat"` - Operation type (required)
- `gen_ai.system` - GenAI provider (e.g., "openai", "anthropic")
- `gen_ai.request.model` - Model requested
- `gen_ai.response.model` - Model that responded
- `gen_ai.usage.input_tokens` - Input tokens consumed
- `gen_ai.usage.output_tokens` - Output tokens generated

Custom LogzAI attributes:
- `type="ai"` - LogzAI filtering identifier
- `agent.name` - Agent name (if set)
- `agent.prompt` - User prompt that triggered the agent
- `agent.total_tokens` - Total tokens (input + output)

**Log event structure**:
```python
{
    "event": "pydantic_ai.agent.run",
    "type": "ai",
    "model": "gpt-4o-mini",
    "provider": "openai",
    "input_tokens": 123,
    "output_tokens": 456,
    "total_tokens": 579,
    "user_prompt": "...",
    "agent_name": "...",
    "messages": [...]  # If include_messages=True
}
```

**Message extraction** ([pydantic_ai.py:98-157](src/logzai_otlp/plugins/pydantic_ai.py#L98-L157)):
The plugin converts PydanticAI's internal message format to OpenAI-style messages:
- `ModelRequest` → extracts system prompts, user prompts, and tool results
- `ModelResponse` → extracts assistant text and tool calls
- Handles multi-part messages (text + tool calls in same response)
- Deduplicates system instructions (only includes once)

**OpenAI-style message roles**:
- `system` - System prompts and agent instructions
- `user` - User input prompts
- `assistant` - Model responses (with optional `tool_calls` array)
- `tool` - Tool execution results (with `tool_call_id` and `tool_name`)

**Configuration options**:
```python
logzai.plugin('pydantic-ai', pydantic_ai_plugin, {
    "include_messages": True  # Include full message history in logs (default: True)
})
```

**Implementation details**:
- Stores original methods before patching for proper cleanup
- Handles both sync and async agent execution
- Cleanup restores original `Agent.run` and `Agent.run_sync` methods
- Model name extraction falls back to `self.model.model_name` if not in response
- **Follows OpenTelemetry GenAI semantic conventions** for interoperability with standard observability tools

#### LangChain Plugin (`plugins/langchain.py`)

**What it does**:
- Activates LangChain's built-in OpenTelemetry instrumentation
- Automatically creates spans for chains, LLM calls, tools, and agents
- Optionally adds `type="ai"` attribute for LogzAI filtering
- Follows OpenTelemetry GenAI semantic conventions

**How it works**:
- Sets `LANGSMITH_TRACING=true` and `LANGSMITH_OTEL_ENABLED=true` to activate LangChain's tracing system
- Suppresses LangSmith and OpenTelemetry logging to hide connection errors and warnings
- LangChain then uses the global TracerProvider configured by `logzai.init()`
- All LangChain operations are automatically traced to LogzAI via OpenTelemetry
- Optionally adds a custom SpanProcessor to enhance spans with LogzAI-specific attributes
- Clean console output with no LangSmith authentication errors

**CRITICAL: Import Order**:
The plugin MUST be registered BEFORE importing langchain or langgraph modules:
```python
# 1. Load environment (if using .env)
import dotenv
dotenv.load_dotenv()

# 2. Initialize LogzAI
from logzai_otlp import logzai
logzai.init(ingest_token="...", ingest_endpoint="...")

# 3. Register plugin
from logzai_otlp.plugins import langchain_plugin
logzai.plugin('langchain', langchain_plugin)

# 4. THEN import LangChain
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
```

**Configuration options**:
```python
logzai.plugin('langchain', langchain_plugin, {
    "add_type_attribute": True,  # Add type="ai" to spans (default: True)
    "include_messages": True,    # Include message history in gen_ai.messages (default: True)
    "warn_if_late": True         # Warn if LangChain already imported (default: True)
})
```

**Span attributes captured** (automatic via LangChain):

OpenTelemetry GenAI semantic conventions (standard):
- `gen_ai.system` - Provider (e.g., "openai", "anthropic")
- `gen_ai.request.model` - Model requested
- `gen_ai.response.model` - Model that responded
- `gen_ai.usage.input_tokens` - Input tokens consumed
- `gen_ai.usage.output_tokens` - Output tokens generated
- `gen_ai.messages` - Full conversation history in OpenAI format (when `include_messages=True`)

Custom LogzAI attributes (optional):
- `type="ai"` - LogzAI filtering identifier (when `add_type_attribute=True`)

**Message format** (when `include_messages=True`):
The plugin extracts messages from LangChain's `gen_ai.prompt` and `gen_ai.completion` attributes and normalizes them to OpenAI format, similar to the PydanticAI plugin:
```python
[
    {"role": "user", "content": "How old is Alexandru?"},
    {
        "role": "assistant",
        "tool_calls": [
            {
                "id": "call_aYVBNfp2v2NoRaupega5GcA1",
                "name": "get_age",
                "arguments": {"name": "Alexandru"}
            }
        ]
    },
    {
        "role": "tool",
        "content": "20",
        "tool_call_id": "call_aYVBNfp2v2NoRaupega5GcA1",
        "tool_name": "get_age"
    },
    {"role": "assistant", "content": "Alexandru is 20 years old."}
]
```

**Implementation details**:
- Uses LangChain's built-in OpenTelemetry instrumentation (no monkey-patching)
- Environment variables activate automatic tracing for all LangChain components
- Custom `LangChainSpanExporterWrapper` adds `type="ai"` attribute and normalizes messages
- Extracts messages from `gen_ai.prompt` and `gen_ai.completion` and converts to OpenAI format
- Cleanup restores original environment variables
- Works with LangChain, LangGraph, and all LangChain integrations
- **More maintainable than monkey-patching** - leverages LangChain's public API

**Advantages over monkey-patching approach**:
- Simpler implementation (~150 lines vs ~300 for PydanticAI)
- More robust - uses LangChain's official OTEL support
- Automatic instrumentation for all components (chains, agents, tools, retrievers)
- Future-proof - won't break when LangChain updates

#### Creating Custom Plugins

**Plugin function signature**:
```python
def my_plugin(instance: LogzAI, config: Optional[dict] = None) -> Optional[CleanupFunction]:
    """
    Args:
        instance: The LogzAI singleton instance
        config: Optional configuration dictionary

    Returns:
        Optional cleanup function (sync or async)
    """
    # Setup code here

    def cleanup():
        # Cleanup code here
        pass

    return cleanup
```

**Common plugin patterns**:
1. **Middleware pattern** (FastAPI): Add middleware/hooks to framework
2. **Monkey-patching pattern** (PydanticAI): Wrap existing methods to add instrumentation
3. **Extension pattern**: Add new methods to the LogzAI instance
4. **Event listener pattern**: Subscribe to framework events and log them

**Example - Custom database plugin**:
```python
def database_plugin(instance: LogzAI, config: Optional[dict] = None):
    """Plugin that logs all database queries."""
    import sqlalchemy
    from sqlalchemy import event

    engine = config.get("engine") if config else None
    if not engine:
        raise ValueError("database_plugin requires 'engine' in config")

    @event.listens_for(engine, "before_cursor_execute")
    def log_query(conn, cursor, statement, parameters, context, executemany):
        with instance.span("database.query") as span:
            span.set_attribute("type", "database")
            span.set_attribute("db.statement", statement)
            instance.info("Executing query", query=statement[:100])

    def cleanup():
        event.remove(engine, "before_cursor_execute", log_query)

    return cleanup
```

### Logging vs Tracing

- **Logging**: Uses OpenTelemetry `LoggingHandler` attached to Python's `logging` module. Logs flow through `logzai.info()`, `logzai.error()`, etc.
- **Tracing**: Uses OpenTelemetry `Tracer` to create spans. Spans created via `logzai.span()` context manager or `logzai.start_span()`.
- **Integration**: Logs emitted within a span context are automatically associated with that span in the OTLP backend.

### Headers and Metadata

The library adds custom headers to OTLP requests:
- `x-ingest-token`: Authentication token (required)
- `x-origin`: Optional origin identifier to help the backend identify the source (added to both headers and resource attributes)

## Important Implementation Details

### OTLP Endpoint Handling
The library automatically appends `/logs` and `/traces` to the base endpoint URL (see `_make_log_exporter` and `_make_trace_exporter` in [main.py](src/logzai_otlp/main.py:38-60)).

When working with endpoints, always use the base URL without these suffixes.

### Exception Handling in Logging
Exception information is captured automatically when:
- `exc_info=True` is passed (default for `error()`, `critical()`, and `exception()`)
- An exception is active in the current context (`sys.exc_info()`)

Exception data is logged as structured attributes: `exception.type`, `exception.message`, `exception.stacktrace`

### Plugin Thread Safety
Plugin registration uses a lock (`_plugin_lock`) to ensure thread-safe access to the plugin registry. Multiple plugins can be registered concurrently.

### Async Cleanup Handling
Plugin cleanup functions can be sync or async. The library detects async functions and:
- If in an async context (running event loop), schedules as a task
- Otherwise, runs in a new event loop via `asyncio.run()`

## Project Structure

```
src/logzai_otlp/
├── __init__.py          # Package exports
├── main.py              # Core LogzAI class, singleton instance
└── plugins/
    ├── __init__.py      # Plugin type definitions and exports
    ├── fastapi.py       # FastAPI HTTP middleware plugin
    ├── pydantic_ai.py   # PydanticAI agent instrumentation plugin
    └── langchain.py     # LangChain OTEL activation plugin
```

## Common Patterns and Best Practices

### Plugin Registration Order
**Important**: Register plugins AFTER `logzai.init()` but BEFORE using the framework:
```python
# 1. Initialize LogzAI first
logzai.init(ingest_token="...", ingest_endpoint="...")

# 2. Register plugins
logzai.plugin('pydantic-ai', pydantic_ai_plugin)

# 3. Now create and use agents/apps
agent = Agent(...)
```

### Graceful Shutdown
Always call `logzai.shutdown()` to ensure:
- All buffered logs/traces are flushed to the backend
- Plugin cleanup functions are called in reverse order (LIFO)
- OpenTelemetry providers are properly terminated

The library uses `BatchLogRecordProcessor` and `BatchSpanProcessor`, so logs/traces may be buffered for performance.

### Logging Within Spans
Logs emitted while a span is active are automatically associated with that span:
```python
with logzai.span("operation") as span:
    logzai.info("This log is linked to the span")
    span.set_attribute("custom", "value")
```

This is how the FastAPI plugin works: all logs during request handling are linked to the request span.

### Mirror to Console (Development)
For local development, use `mirror_to_console=True` to see logs in stdout while also sending to OTLP:
```python
logzai.init(
    ingest_token="...",
    ingest_endpoint="...",
    mirror_to_console=True  # Logs appear in terminal AND LogzAI
)
```

### Environment Variables
Examples typically use `python-dotenv` to load credentials from `.env`:
```env
# .env file
OPENAI_API_KEY=sk-...
LOGZAI_TOKEN=your-token
```

## Testing and Examples

Run examples with `uv run`:
```bash
# FastAPI example (includes uvicorn server)
uv run examples/fastapi_example.py

# PydanticAI example (requires OPENAI_API_KEY in .env)
uv run examples/pydantic_ai_example.py
```

**FastAPI example** demonstrates:
- Automatic span creation for each route
- Logs within request context
- Slow request detection (simulated with `asyncio.sleep(0.6)`)
- Error logging and exception handling

**PydanticAI example** demonstrates:
- Plugin registration before agent creation
- Token usage logging
- Message history capture (OpenAI format)
- Multi-turn conversation tracking

## Dependencies

**Core dependencies** (required):
- `opentelemetry-sdk>=1.27.0` - OpenTelemetry SDK for logging and tracing
- `opentelemetry-exporter-otlp>=1.27.0` - OTLP exporters (HTTP & gRPC)
- `python-dotenv>=1.0.0` - Environment variable loading

**Optional plugin dependencies** (not included by default):
- `fastapi` + `starlette` - Required for FastAPI plugin
- `pydantic-ai` - Required for PydanticAI plugin

**Development dependencies**:
- `build>=1.3.0` - For building distribution packages
- `twine>=6.2.0` - For uploading to PyPI

**Example dependencies** (in `examples/` group):
- `langchain`, `langchain-openai`, `langgraph` - For LangChain examples
- `pydantic-ai` - For PydanticAI examples

Plugins import their dependencies only when registered, making them truly optional. If a required dependency is missing, the plugin will raise an `ImportError` with installation instructions.
