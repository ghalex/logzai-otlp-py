## logzai-otlp

Lightweight OpenTelemetry logging client for LogzAI.

- **Transport**: OTLP over HTTP or gRPC
- **Structured logs**: pass arbitrary keyword args as attributes
- **Graceful shutdown**: buffers flushed on process exit

### Installation

```bash
pip install logzai-otlp
```

### Quick start (HTTP OTLP)

```python
from logzai_otlp import logzai

logzai.init(
    ingest_token="your-ingest-token",
    ingest_endpoint="https://ingest.logzai.com",  # Base OTLP endpoint
    service_name="orders-api",
    environment="prod",
    protocol="http",  # default
)

logzai.info("User logged in", user_id="123", method="oauth")
logzai.error("Payment failed", order_id="42", reason="card_declined")

# optional – logs are flushed automatically at process exit
logzai.shutdown()
```

### Using standard `logging`

This client installs an OpenTelemetry handler on the `logzai` logger. You can use the standard library `logging` API if you prefer:

```python
import logging
from logzai_otlp import logzai

logzai.init(ingest_token="your-token", ingest_endpoint="https://ingest.logzai.com")

logger = logging.getLogger("logzai")
logger.info("Inventory updated", extra={"sku": "A-42", "qty": 3})
```

### API

```python
logzai.init(
    ingest_token: str,
    ingest_endpoint: str = "http://ingest.logzai.com",
    min_level: int = logging.DEBUG,
    *,
    service_name: str = "app",
    service_namespace: str = "default",
    environment: str = "prod",
    protocol: str = "http",  # "http" | "grpc"
    mirror_to_console: bool = False,
) -> None
```

- **ingest_token**: Your LogzAI ingest token; sent as `x-ingest-token` header
- **ingest_endpoint**: Base OTLP collector endpoint (paths `/logs` and `/traces` are appended automatically)
  - HTTP example: `https://ingest.logzai.com`
  - gRPC example: `ingest.logzai.com:4317`
- **min_level**: Minimum logging level (default: `logging.DEBUG`)
- **service_name**: OpenTelemetry `service.name` resource attribute
- **service_namespace**: OpenTelemetry `service.namespace` resource attribute  
- **environment**: OpenTelemetry `deployment.environment` resource attribute
- **protocol**: `http` (default) or `grpc`
- **mirror_to_console**: Also log to console/stdout (default: `False`)

Convenience logging helpers:

```python
logzai.debug(message: str, exc_info: bool = False, **attrs) -> None
logzai.info(message: str, exc_info: bool = False, **attrs) -> None
logzai.warning(message: str, exc_info: bool = False, **attrs) -> None
logzai.warn(message: str, exc_info: bool = False, **attrs) -> None  # alias of warning
logzai.error(message: str, exc_info: bool = True, **attrs) -> None
logzai.critical(message: str, exc_info: bool = True, **attrs) -> None
logzai.exception(message: str, **attrs) -> None  # logs with full exception info
logzai.shutdown() -> None  # flush and shutdown provider
```

All extra keyword arguments are sent as structured log attributes. The `exc_info` parameter controls whether exception information is automatically captured when available.

### Tracing

LogzAI now includes distributed tracing capabilities alongside logging:

```python
from logzai_otlp import logzai

logzai.init(ingest_token="your-token", ingest_endpoint="https://ingest.logzai.com")

# Create spans manually
span = logzai.start_span("database_query")
span.set_attribute("table", "users")
span.end()

# Use context manager for automatic span lifecycle
with logzai.span("api_request") as span:
    logzai.info("Processing request", request_id="123")
    span.set_attribute("method", "GET")
    span.set_attribute("path", "/api/users")
    # span ends automatically, even on exceptions
```

Tracing methods:

```python
logzai.start_span(name: str, **kwargs) -> Span
logzai.span(name: str, **kwargs)  # context manager
logzai.set_span_attribute(span: Span, key: str, value: Any) -> None
```

### Plugins

LogzAI supports a plugin system that enables framework integrations and custom functionality. Plugins receive the LogzAI instance and can extend logging/tracing behavior.

#### Built-in Plugins

LogzAI includes built-in plugins for popular frameworks:

##### FastAPI Plugin

Automatically logs HTTP requests/responses and creates spans for distributed tracing:

```python
from fastapi import FastAPI
from logzai_otlp import logzai, fastapi_plugin

app = FastAPI()

logzai.init(
    ingest_token="your-token",
    ingest_endpoint="https://ingest.logzai.com",
    service_name="my-api"
)

# Enable FastAPI instrumentation
logzai.plugin('fastapi', fastapi_plugin, {
    "app": app,  # Required: your FastAPI app
    "log_request_body": True,  # Optional: log request bodies
    "slow_request_threshold_ms": 500  # Optional: warn on slow requests
})

@app.post("/login")
async def login(username: str):
    # All logs here are automatically in the POST /login span
    logzai.info("User logging in", username=username)
    return {"status": "ok"}

# Each request creates a span with:
# - Route: POST /login
# - Status code, duration, client IP
# - All logs during request handling
```

##### PydanticAI Plugin

Automatically logs all agent usage and messages with distributed tracing:

```python
from logzai_otlp import logzai, pydantic_ai_plugin
from pydantic_ai import Agent

# Initialize LogzAI
logzai.init(
    ingest_token="your-token",
    ingest_endpoint="https://ingest.logzai.com",
    service_name="my-ai-app"
)

# Enable PydanticAI instrumentation
logzai.plugin('pydantic-ai', pydantic_ai_plugin, {
    "include_messages": True  # Optional: include full message history
})

# Use PydanticAI normally - all calls are automatically logged and traced
agent = Agent('openai:gpt-4', instructions="You are helpful")
result = await agent.run("Hello!")

# Creates spans for:
# - Agent execution time (pydantic_ai.agent.run)
# - Span attributes: agent name, model, provider, token usage
#
# Logs will include:
# - Token usage (input/output/total)
# - Model and provider info
# - Full message history (if enabled)
# - User prompts and responses
```

#### Creating Custom Plugins

Plugin functions receive the LogzAI instance and optional config, and return an optional cleanup function:

```python
from typing import Optional
from logzai_otlp import logzai

def my_plugin(instance, config: Optional[dict] = None):
    """Plugin receives LogzAI instance and optional config."""

    # Add custom functionality
    def custom_log(message, **kwargs):
        instance.info(f"[CUSTOM] {message}", **kwargs)

    instance.custom_log = custom_log

    # Optional: return cleanup function (sync or async)
    def cleanup():
        if hasattr(instance, 'custom_log'):
            delattr(instance, 'custom_log')

    return cleanup

# Initialize and register
logzai.init(ingest_token="token", ingest_endpoint="https://ingest.logzai.com")
logzai.plugin("my-plugin", my_plugin, {"enabled": True})

# Use plugin
logzai.custom_log("Hello from plugin!")

# Cleanup (optional - happens automatically on shutdown)
logzai.unregister_plugin("my-plugin")
```

#### Plugin API

```python
# Register a plugin
logzai.plugin(
    name: str,                    # Unique identifier
    plugin_func: LogzAIPlugin[T], # Plugin function
    config: Optional[T] = None    # Optional configuration
) -> None

# Unregister a plugin
logzai.unregister_plugin(name: str) -> bool

# Plugins are automatically cleaned up on shutdown
logzai.shutdown()
```

**Plugin Lifecycle:**
- Plugins execute immediately upon registration
- Can return optional cleanup function (sync or async)
- Cleaned up in reverse order (LIFO) during shutdown
- Duplicate registration replaces existing plugin with warning

### Requirements

- Python >= 3.9
- `opentelemetry-sdk>=1.27.0`
- `opentelemetry-exporter-otlp>=1.27.0`

### License

MIT – see `LICENSE` for details.


