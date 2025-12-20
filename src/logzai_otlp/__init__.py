from .main import LogzAI, logzai
from .plugins import LogzAIPlugin, CleanupFunction, PluginEntry, pydantic_ai_plugin, fastapi_plugin

# Export the class for direct instantiation and singleton instance
__all__ = [
    'LogzAI',
    'logzai',
    'LogzAIPlugin',
    'CleanupFunction',
    'PluginEntry',
    'pydantic_ai_plugin',
    'fastapi_plugin',
]