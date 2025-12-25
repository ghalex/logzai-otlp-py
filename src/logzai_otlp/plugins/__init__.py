"""Plugin system for LogzAI."""

from typing import Optional, Any, Callable, Union, TypeVar, Awaitable, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..main import LogzAI

# Type definitions
T = TypeVar("T")
CleanupFunction = Union[Callable[[], None], Callable[[], Awaitable[None]]]
LogzAIPlugin = Callable[["LogzAI", Optional[T]], Optional[CleanupFunction]]


@dataclass
class PluginEntry:
    """Entry for a registered plugin.

    Attributes:
        name: Unique identifier for the plugin
        plugin_func: The plugin function that was registered
        cleanup_func: Optional cleanup function returned by the plugin
        config: Optional configuration passed to the plugin
    """

    name: str
    plugin_func: Callable[["LogzAI", Optional[Any]], Optional[CleanupFunction]]
    cleanup_func: Optional[CleanupFunction]
    config: Optional[Any] = None


# Import built-in plugins
from .pydantic_ai import pydantic_ai_plugin  # noqa: E402
from .fastapi import fastapi_plugin  # noqa: E402
from .langchain import langchain_plugin  # noqa: E402

__all__ = [
    "T",
    "CleanupFunction",
    "LogzAIPlugin",
    "PluginEntry",
    "pydantic_ai_plugin",
    "fastapi_plugin",
    "langchain_plugin",
]
