#!/usr/bin/env python3
"""
Example: Using LogzAI with PydanticAI plugin.
Demonstrates automatic logging of agent usage and messages.
"""
import asyncio
from pydantic_ai import Agent
from logzai_otlp import logzai, pydantic_ai_plugin


def get_age_tool(name: str) -> int:
    """Get the age of a person."""
    if name.lower() == "alexandru":
        return 20
    return 25


async def main():
    """Demonstrate PydanticAI plugin with LogzAI."""
    # 1. Initialize LogzAI
    logzai.init(
        ingest_token="your-token",
        ingest_endpoint="http://localhost:4318",  # or https://ingest.logzai.com
        service_name="pydantic-ai-demo",
        environment="dev",
        mirror_to_console=True  # Also print to console for demo
    )

    # 2. Register the PydanticAI plugin BEFORE creating agents
    logzai.plugin('pydantic-ai', pydantic_ai_plugin, {
        "include_messages": True    # Include full message history (optional)
    })

    # 3. Create and use your PydanticAI agent normally
    # The plugin will automatically log all agent calls
    agent = Agent(
        'openai:gpt-4o-mini',  # or use create_chat_llm() from your config
        instructions="You are a helpful AI assistant.",
        tools=[get_age_tool]
    )

    async with agent:
        # First agent call
        result = await agent.run("How old is Alexandru?")
        print(f"\n✓ Answer: {result.output}")

        # Second agent call
        result = await agent.run("What was the person's name I just asked about?")
        print(f"\n✓ Answer: {result.output}")

    # 4. Shutdown LogzAI (cleanup plugins and flush logs)
    logzai.shutdown()


if __name__ == "__main__":
    # Optional: Load environment variables
    try:
        import dotenv
        dotenv.load_dotenv(override=True)
    except ImportError:
        pass

    asyncio.run(main())
