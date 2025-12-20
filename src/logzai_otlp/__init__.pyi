# Type stubs for logzai_otlp
from contextlib import AbstractContextManager
from typing import Any, Dict, Optional, Generator, Callable, Union, TypeVar, Awaitable
from opentelemetry.trace import Span
import logging

# Plugin system types
T = TypeVar('T')
CleanupFunction = Union[Callable[[], None], Callable[[], Awaitable[None]]]
LogzAIPlugin = Callable[[LogzAI, Optional[T]], Optional[CleanupFunction]]

class LogzAI:
    def init(
        self,
        ingest_token: str,
        ingest_endpoint: str = ...,
        min_level: int = ...,
        *,
        service_name: str = ...,
        service_namespace: str = ...,
        environment: str = ...,
        protocol: str = ...,
        mirror_to_console: bool = ...,
    ) -> None: ...
    
    def log(
        self,
        level: int,
        message: str,
        *,
        stacklevel: int = ...,
        exc_info: bool = ...,
        **kwargs: Any
    ) -> None: ...
    
    def debug(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def info(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def warning(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def warn(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def error(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def critical(self, message: str, exc_info: bool = ..., **kwargs: Any) -> None: ...
    def exception(self, message: str, **kwargs: Any) -> None: ...
    
    def start_span(self, name: str, **kwargs: Any) -> Span: ...
    def span(self, name: str, **kwargs: Any) -> AbstractContextManager[Span]: ...
    def set_span_attribute(self, span: Span, key: str, value: Any) -> None: ...

    def plugin(
        self,
        name: str,
        plugin_func: LogzAIPlugin[T],
        config: Optional[T] = ...
    ) -> None: ...
    def unregister_plugin(self, name: str) -> bool: ...

    def shutdown(self) -> None: ...

logzai: LogzAI
