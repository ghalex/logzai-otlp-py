#!/usr/bin/env python3
import os
import asyncio
import dotenv

dotenv.load_dotenv(override=True)

# Import logzai and plugin BEFORE LangChain
from logzai_otlp import logzai  # noqa: E402
from logzai_otlp.plugins import langchain_plugin  # noqa: E402

# os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
# os.environ['LANGSMITH_TRACING'] = 'true'

# logfire.configure(token=os.getenv('LOGFIRE_TOKEN'), service_name='test-langchain')

# Initialize LogzAI first
logzai.init(
    ingest_token=os.getenv("LOGZAI_TOKEN", "pylz_v1_e"),
    ingest_endpoint=os.getenv("LOGZAI_ENDPOINT", "https://ingest.logzai.com"),
    service_name="langchain-example",
    environment="dev",
    mirror_to_console=True,
)

# Register plugin BEFORE importing LangChain
logzai.plugin(
    "langchain",
    langchain_plugin,
    {"include_messages": True, "log_token_usage": True},
)

# NOW import LangChain (after plugin registration)
from langchain_openai import ChatOpenAI  # noqa: E402
from langchain.agents import create_agent  # noqa: E402


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


def get_age(name: str) -> int:
    """Get the age of a person."""
    return 20


async def main():
    # Create the LLM
    llm = ChatOpenAI(model="gpt-4o")

    # Define tools
    tools = [add, get_age]

    # Create the agent using the new API
    agent = create_agent(llm, tools)

    # Run the agent
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "How old is Alexandru?"}]}
    )

    # Extract the final message
    logzai.info(result["messages"][-1].content)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        logzai.shutdown()
