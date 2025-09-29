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
from logzai_otlp import init, info, error, shutdown

init(
    org="your-org-id",
    api_key="your-api-key",
    service_name="orders-api",
    environment="prod",
    endpoint="https://collector.your-domain.tld/v1/logs",  # OTLP/HTTP endpoint
    protocol="http",  # default
)

info("User logged in", user_id="123", method="oauth")
error("Payment failed", order_id="42", reason="card_declined")

# optional – logs are flushed automatically at process exit
shutdown()
```

### Quick start (gRPC OTLP)

```python
from logzai_otlp import init, info

init(
    org="your-org-id",
    api_key="your-api-key",
    # gRPC OTLP endpoints are host:port (no path)
    endpoint="collector.your-domain.tld:4317",
    protocol="grpc",
)

info("Started via gRPC", node="worker-1")
```

### Using standard `logging`

This client installs an OpenTelemetry handler on the `logzai` logger. You can use the standard library `logging` API if you prefer:

```python
import logging
from logzai_otlp import init

init(org="org", api_key="key")

logger = logging.getLogger("logzai")
logger.info("Inventory updated", extra={"sku": "A-42", "qty": 3})
```

### API

```python
init(
    org: str,
    api_key: str,
    *,
    service_name: str = "app",
    environment: str = "prod",
    endpoint: str = "http://localhost:4318/v1/logs",
    protocol: str = "http",  # "http" | "grpc"
) -> None
```

- **org**: Your organization identifier; included in resource attributes
- **api_key**: Sent as `x-api-key` header for OTLP/HTTP
- **service_name**: OpenTelemetry `service.name` resource attribute
- **environment**: OpenTelemetry `deployment.environment` resource attribute
- **endpoint**: OTLP collector endpoint
  - HTTP example: `https://collector.example.com/v1/logs`
  - gRPC example: `collector.example.com:4317`
- **protocol**: `http` (default) or `grpc`

Convenience logging helpers:

```python
debug(message: str, **attrs) -> None
info(message: str, **attrs) -> None
warning(message: str, **attrs) -> None
warn(message: str, **attrs) -> None  # alias of warning
error(message: str, **attrs) -> None
critical(message: str, **attrs) -> None
shutdown() -> None  # flush and shutdown provider
```

All extra keyword arguments are sent as structured log attributes.

### Requirements

- Python >= 3.9
- `opentelemetry-sdk>=1.27.0`
- `opentelemetry-exporter-otlp>=1.27.0`

### License

MIT – see `LICENSE` for details.


