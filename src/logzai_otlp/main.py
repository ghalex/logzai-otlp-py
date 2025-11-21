# logzai.py
import logging
import traceback
import sys
import os
import socket
from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, Status, StatusCode

# Remove global variables - using singleton pattern only


class LogzAIBase:
    """Base class for LogzAI implementations."""
    
    def __init__(self):
        self.log_provider: Optional[LoggerProvider] = None
        self.tracer_provider: Optional[TracerProvider] = None
        self.logger: Optional[logging.Logger] = None
        self.tracer: Optional[trace.Tracer] = None
        self.mirror_to_console: bool = False
    
    def _make_log_exporter(self, endpoint: str, headers: Dict[str, str], protocol: str = "http"):
        """Create a log exporter based on protocol."""
        # Append /logs to the endpoint, removing any trailing slashes first
        log_url = endpoint.rstrip('/') + '/logs'
        
        if protocol.lower() == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            return OTLPLogExporter(endpoint=log_url, headers=list(headers.items()))
        else:
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            return OTLPLogExporter(endpoint=log_url, headers=list(headers.items()))
    
    def _make_trace_exporter(self, endpoint: str, headers: Dict[str, str], protocol: str = "http"):
        """Create a trace exporter based on protocol."""
        # Append /traces to the endpoint, removing any trailing slashes first
        trace_url = endpoint.rstrip('/') + '/traces'
        
        if protocol.lower() == "grpc":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(endpoint=trace_url, headers=list(headers.items()))
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(endpoint=trace_url, headers=list(headers.items()))

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
        handler = LoggingHandler(level=logging.NOTSET, logger_provider=self.log_provider)
        self.logger = logging.getLogger("logzai")
        self.logger.setLevel(min_level)
        self.logger.addHandler(handler)
        self.logger.propagate = False
        
        # Add console handler if mirror_to_console is enabled
        if self.mirror_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(min_level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
    
    def log(self, level: int, message: str, *, stacklevel: int = 2, exc_info: bool = False, **kwargs) -> None:
        """Send a log with an explicit level."""
        if not self.logger:
            raise RuntimeError("LogzAI not initialized. Call logzai.init(...) first.")
        
        # Handle exception information
        if exc_info or sys.exc_info()[0] is not None:
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_type is not None:
                kwargs['is_exception'] = True
                kwargs['exception.type'] = exc_type.__name__
                kwargs['exception.message'] = str(exc_value)
                kwargs['exception.stacktrace'] = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        
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
    
    def shutdown(self) -> None:
        """Shutdown both logging and tracing providers."""
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


# Create singleton instance
logzai = LogzAI()

# Export the class for direct instantiation
__all__ = ['LogzAI', 'logzai']
