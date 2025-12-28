# logzai.py
import logging
import traceback
import sys
import threading
import asyncio

from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

from .plugins import PluginEntry, CleanupFunction, LogzAIPlugin, T

# Remove global variables - using singleton pattern only


class LogzAIBase:
    """Base class for LogzAI implementations."""

    def __init__(self):
        self.log_provider: Optional[LoggerProvider] = None
        self.tracer_provider: Optional[TracerProvider] = None
        self.logger: Optional[logging.Logger] = None
        self.tracer: Optional[trace.Tracer] = None
        self.mirror_to_console: bool = False

        # Plugin registry
        self._plugins: Dict[str, PluginEntry] = {}
        self._plugin_lock: threading.Lock = threading.Lock()

    def _make_log_exporter(
        self, endpoint: str, headers: Dict[str, str], protocol: str = "http"
    ):
        """Create a log exporter based on protocol."""
        # Append /logs to the endpoint, removing any trailing slashes first
        log_url = endpoint.rstrip("/") + "/logs"

        if protocol.lower() == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import (
                OTLPLogExporter,
            )

            return OTLPLogExporter(endpoint=log_url, headers=list(headers.items()))
        else:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import (
                OTLPLogExporter,
            )

            return OTLPLogExporter(endpoint=log_url, headers=list(headers.items()))  # type: ignore

    def _make_trace_exporter(
        self, endpoint: str, headers: Dict[str, str], protocol: str = "http"
    ):
        """Create a trace exporter based on protocol."""
        # Append /traces to the endpoint, removing any trailing slashes first
        trace_url = endpoint.rstrip("/") + "/traces"

        if protocol.lower() == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=trace_url, headers=list(headers.items()))
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=trace_url, headers=list(headers.items()))  # type: ignore


class LogzAI(LogzAIBase):
    """Main LogzAI class with logging and tracing capabilities."""

    def init(
        self,
        ingest_token: str,
        ingest_endpoint: str = "http://ingest.logzai.com",
        min_level: int = logging.DEBUG,
        *,
        service_name: str = "app",
        service_namespace: str = "default",
        environment: str = "prod",
        protocol: str = "http",
        mirror_to_console: bool = False,
        origin: Optional[str] = None,
    ) -> None:
        """Initialize LogzAI with both logging and tracing.

        Args:
            ingest_token: Authentication token for the LogzAI ingest endpoint
            ingest_endpoint: URL of the LogzAI ingest endpoint
            min_level: Minimum logging level to capture
            service_name: Name of the service generating logs/traces
            service_namespace: Namespace for the service
            environment: Deployment environment (e.g., 'prod', 'dev', 'staging')
            protocol: Protocol to use for OTLP export ('http' or 'grpc')
            mirror_to_console: Whether to also log to console
            origin: Origin identifier to help the ingestor identify the source
        """
        self.mirror_to_console = mirror_to_console

        # Create resource attributes
        resource_attrs = {
            "service.name": service_name,
            "service.namespace": service_namespace,
            "deployment.environment": environment,
        }

        # Add origin to resource attributes if provided
        if origin:
            resource_attrs["origin"] = origin

        resource = Resource.create(resource_attrs)

        # Create headers with ingest token
        headers = {"x-ingest-token": ingest_token}

        # Add origin to headers if provided
        if origin:
            headers["x-origin"] = origin

        # Setup tracing
        span_processor = BatchSpanProcessor(
            self._make_trace_exporter(ingest_endpoint, headers, protocol)
        )

        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(span_processor)

        # Register the tracer provider globally
        trace.set_tracer_provider(self.tracer_provider)
        self.tracer = trace.get_tracer("logzai")

        # Setup logging
        log_processor = BatchLogRecordProcessor(
            self._make_log_exporter(ingest_endpoint, headers, protocol)
        )

        self.log_provider = LoggerProvider(resource=resource)
        self.log_provider.add_log_record_processor(log_processor)

        # Setup logger
        handler = LoggingHandler(
            level=logging.NOTSET, logger_provider=self.log_provider
        )
        self.logger = logging.getLogger("logzai")
        self.logger.setLevel(min_level)
        self.logger.addHandler(handler)
        self.logger.propagate = False

        # Add console handler if mirror_to_console is enabled
        if self.mirror_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(min_level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    def log(
        self,
        level: int,
        message: str,
        *,
        stacklevel: int = 2,
        exc_info: bool = False,
        **kwargs,
    ) -> None:
        """Send a log with an explicit level."""
        if not self.logger:
            raise RuntimeError("LogzAI not initialized. Call logzai.init(...) first.")

        # Handle exception information
        if exc_info or sys.exc_info()[0] is not None:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_type is not None:
                kwargs["is_exception"] = True
                kwargs["exception.type"] = exc_type.__name__
                kwargs["exception.message"] = str(exc_value)
                kwargs["exception.stacktrace"] = "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                )

        self.logger.log(level, message, extra=kwargs, stacklevel=stacklevel)

    def debug(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self.log(logging.DEBUG, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def info(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self.log(logging.INFO, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def warning(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self.log(logging.WARNING, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def warn(self, message: str, exc_info: bool = False, **kwargs) -> None:
        self.log(logging.WARNING, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def error(self, message: str, exc_info: bool = True, **kwargs) -> None:
        """Log an error. By default, captures exception info if available."""
        self.log(logging.ERROR, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: bool = True, **kwargs) -> None:
        """Log a critical error. By default, captures exception info if available."""
        self.log(logging.CRITICAL, message, stacklevel=3, exc_info=exc_info, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """Log an exception with full stack trace. Should be called from an exception handler."""
        self.log(logging.ERROR, message, stacklevel=3, exc_info=True, **kwargs)

    def start_span(self, name: str, **kwargs) -> Span:
        """Start a new span."""
        if not self.tracer:
            raise RuntimeError("LogzAI not initialized. Call logzai.init(...) first.")
        return self.tracer.start_span(name, **kwargs)

    @contextmanager
    def span(self, name: str, **kwargs) -> Generator[Span, None, None]:
        """Context manager for creating spans."""
        span = self.start_span(name, **kwargs)
        try:
            with trace.use_span(span, end_on_exit=True):
                yield span
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise

    def set_span_attribute(self, span: Span, key: str, value: Any) -> None:
        """Set an attribute on a span."""
        span.set_attribute(key, value)

    def plugin(
        self, name: str, plugin_func: LogzAIPlugin[T], config: Optional[T] = None
    ) -> None:
        """Register and execute a plugin.

        Args:
            name: Unique identifier for the plugin
            plugin_func: Plugin function that receives the LogzAI instance and config
            config: Optional configuration object passed to the plugin

        Raises:
            RuntimeError: If LogzAI not initialized

        Example:
            def my_plugin(instance, config):
                print(f"Plugin loaded with config: {config}")
                def cleanup():
                    print("Cleaning up plugin")
                return cleanup

            logzai.plugin("my-plugin", my_plugin, {"setting": "value"})
        """
        if not self.logger or not self.tracer:
            raise RuntimeError("LogzAI not initialized. Call logzai.init(...) first.")

        with self._plugin_lock:
            # Warn if plugin already registered (matches JS behavior)
            if name in self._plugins:
                if self.logger:
                    self.logger.warning(
                        f"Plugin '{name}' is already registered. Replacing existing plugin.",
                        extra={"plugin_name": name},
                    )
                # Cleanup existing plugin before replacing
                self._cleanup_plugin(name)

            cleanup_func: Optional[CleanupFunction] = None

            try:
                # Execute plugin immediately (matches JS behavior)
                cleanup_func = plugin_func(self, config)

                # Store plugin entry
                self._plugins[name] = PluginEntry(
                    name=name,
                    plugin_func=plugin_func,
                    cleanup_func=cleanup_func,
                    config=config,
                )

                # if self.logger:
                #     self.logger.debug(
                #         f"Plugin '{name}' registered successfully",
                #         extra={"plugin_name": name, "has_cleanup": cleanup_func is not None}
                #     )

            except Exception as e:
                # Log error but don't crash (matches JS try-catch behavior)
                if self.logger:
                    self.logger.error(
                        f"Failed to register plugin '{name}': {str(e)}",
                        extra={"plugin_name": name, "error": str(e)},
                        exc_info=True,
                    )
                raise

    def unregister_plugin(self, name: str) -> bool:
        """Unregister a plugin and call its cleanup function.

        Args:
            name: Name of the plugin to unregister

        Returns:
            True if plugin was found and unregistered, False otherwise

        Example:
            logzai.unregister_plugin("my-plugin")
        """
        with self._plugin_lock:
            if name not in self._plugins:
                if self.logger:
                    self.logger.warning(
                        f"Plugin '{name}' not found", extra={"plugin_name": name}
                    )
                return False

            self._cleanup_plugin(name)
            del self._plugins[name]

            # if self.logger:
            #     self.logger.debug(
            #         f"Plugin '{name}' unregistered",
            #         extra={"plugin_name": name}
            #     )

            return True

    def _cleanup_plugin(self, name: str) -> None:
        """Internal helper to cleanup a single plugin.

        Args:
            name: Name of the plugin to cleanup
        """
        if name not in self._plugins:
            return

        entry = self._plugins[name]
        if entry.cleanup_func is None:
            return

        try:
            # Check if cleanup function is async
            result = entry.cleanup_func()

            # Handle async cleanup functions
            if hasattr(result, "__await__"):
                try:
                    # Try to get running loop - if we're in an async context, create task
                    asyncio.get_running_loop()
                    asyncio.create_task(result)  # type: ignore
                except RuntimeError:
                    # No running loop, run in new loop
                    asyncio.run(result)  # type: ignore

            # if self.logger:
            #     self.logger.debug(
            #         f"Plugin '{name}' cleanup completed", extra={"plugin_name": name}
            #     )

        except Exception as e:
            # Log but don't crash (matches JS behavior)
            if self.logger:
                self.logger.error(
                    f"Error during plugin '{name}' cleanup: {str(e)}",
                    extra={"plugin_name": name, "error": str(e)},
                    exc_info=True,
                )

    def _shutdown_plugins(self) -> None:
        """Cleanup all registered plugins.

        Called during shutdown to ensure proper cleanup of all plugins.
        Plugins are cleaned up in reverse registration order.
        """
        with self._plugin_lock:
            # Get plugin names in reverse order (LIFO - like JavaScript)
            plugin_names = list(reversed(self._plugins.keys()))

            for name in plugin_names:
                try:
                    self._cleanup_plugin(name)
                except Exception as e:
                    # Continue cleanup even if one fails
                    if self.logger:
                        self.logger.error(
                            f"Error during shutdown cleanup of plugin '{name}': {str(e)}",
                            extra={"plugin_name": name, "error": str(e)},
                            exc_info=True,
                        )

            # Clear all plugins
            self._plugins.clear()

    def shutdown(self) -> None:
        """Shutdown logging, tracing providers, and all registered plugins."""
        # Shutdown providers first to flush any pending spans/logs
        # This ensures plugin modifications (e.g., span attribute changes) are applied during export
        if self.log_provider:
            try:
                self.log_provider.shutdown()
            except Exception:
                pass

        if self.tracer_provider:
            try:
                self.tracer_provider.shutdown()
            except Exception:
                pass

        # Cleanup all plugins after providers are shut down
        self._shutdown_plugins()


class LogzAIHandler(logging.Handler):
    """A logging handler that sends logs to LogzAI via OpenTelemetry.

    This handler can be used with Python's standard logging module to send
    logs to LogzAI without using the logzai singleton methods.

    Example:
        logzai.init(ingest_token="...", ingest_endpoint="...")

        logging.basicConfig(
            level=logging.INFO,
            handlers=[LogzAIHandler()],
            force=True,
        )

        logging.info("This goes to LogzAI")
    """

    def __init__(self, level: int = logging.NOTSET):
        """Initialize the LogzAI handler.

        Args:
            level: Minimum logging level to handle

        Raises:
            RuntimeError: If LogzAI not initialized via logzai.init()
        """
        super().__init__(level)

        # Get the singleton instance to access the log provider
        if not logzai.log_provider:
            raise RuntimeError(
                "LogzAI not initialized. Call logzai.init(...) before creating LogzAIHandler."
            )

        # Create an internal OpenTelemetry LoggingHandler
        self._otel_handler = LoggingHandler(
            level=level,
            logger_provider=logzai.log_provider
        )

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to LogzAI.

        Args:
            record: The log record to emit
        """
        try:
            # Handle exception information if present
            if record.exc_info:
                exc_type, exc_value, exc_tb = record.exc_info
                if exc_type is not None:
                    # Add exception info to the record's extra data
                    if not hasattr(record, 'is_exception'):
                        setattr(record, 'is_exception', True)
                    if not hasattr(record, 'exception.type'):
                        setattr(record, 'exception.type', exc_type.__name__)
                    if not hasattr(record, 'exception.message'):
                        setattr(record, 'exception.message', str(exc_value))
                    if not hasattr(record, 'exception.stacktrace'):
                        setattr(record, 'exception.stacktrace', ''.join(
                            traceback.format_exception(exc_type, exc_value, exc_tb)
                        ))

            # Forward to the OpenTelemetry handler
            self._otel_handler.emit(record)
        except Exception:
            self.handleError(record)


# Create singleton instance
logzai = LogzAI()

# Export the class for direct instantiation
__all__ = ["LogzAI", "logzai", "LogzAIHandler"]
