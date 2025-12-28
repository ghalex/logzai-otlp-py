from .main import LogzAI, logzai, LogzAIHandler
from .plugins import (
    LogzAIPlugin,
    CleanupFunction,
    PluginEntry,
    pydantic_ai_plugin,
    fastapi_plugin,
    langchain_plugin,
)

# Export the class for direct instantiation and singleton instance
__all__ = [
    "LogzAI",
    "logzai",
    "LogzAIHandler",
    "LogzAIPlugin",
    "CleanupFunction",
    "PluginEntry",
    "pydantic_ai_plugin",
    "fastapi_plugin",
    "langchain_plugin",
]
