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

### Requirements

- Python >= 3.9
- `opentelemetry-sdk>=1.27.0`
- `opentelemetry-exporter-otlp>=1.27.0`

### License

MIT – see `LICENSE` for details.


