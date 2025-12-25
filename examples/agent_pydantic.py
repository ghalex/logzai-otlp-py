#!/usr/bin/env python3
import os
import asyncio
import dotenv

from logzai_otlp import logzai
from logzai_otlp.plugins import pydantic_ai_plugin

dotenv.load_dotenv(override=True)

import asyncio

from typing import List
from pydantic import BaseModel
from pydantic_ai import Agent, models

ingest_token = os.getenv("LOGZAI_TOKEN")
ingest_endpoint = os.getenv("LOGZAI_ENDPOINT")


logzai.init(
    ingest_token=os.getenv("LOGZAI_TOKEN", "pylz_v1_e"),
    ingest_endpoint=os.getenv("LOGZAI_ENDPOINT", "https://ingest.logzai.com"),
    service_name="pydantic-example",
    environment="dev",
    mirror_to_console=True,
)

logzai.plugin(
    "pydantic-ai",
    pydantic_ai_plugin,
    {
        "include_messages": True  # Include full message history (optional)
    },
)

# logfire.configure(token='pylf_v1_eu_wHD8f1mHpbZBm7t9HZJyXPcrj9NQtrLbJzgFKgvgqxl1')
# logfire.instrument_pydantic_ai()

# server = MCPServerStreamableHTTP(url='http://localhost:8000/mcp')
user_question = "How old is Alexandru?"

instructions = """
You are an expert AI assistant.
...
"""


def get_age_tool(name: str) -> int:
    """Get the age of a person."""
    return 20


agent = Agent(
    name="age_agent",
    model="openai:gpt-5.1",
    tools=[get_age_tool],
    instructions=instructions,
)


async def main():
    async with agent:
        result = await agent.run(user_question)
        print(result.output)

        if agent.model is models.Model:
            print(agent.model.model_name)
        # for task in result.output.tasks:
        #     task_index += 1
        #     print(f"Task {task_index}: {task}")


if __name__ == "__main__":
    asyncio.run(main())
