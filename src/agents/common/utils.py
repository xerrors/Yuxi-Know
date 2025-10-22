from datetime import UTC, datetime

from langchain.messages import AIMessageChunk, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.agents.common.base import BaseAgent


async def agent_cli(agent: BaseAgent, config: RunnableConfig | None = None):
    config = config or {}
    if "configurable" not in config:
        config["configurable"] = {}

    while True:
        user_input = input("\nUser: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        stream_flag = False
        async for msg, metadata in agent.stream_messages([{"role": "user", "content": user_input}], config):
            if isinstance(msg, AIMessageChunk):
                content = msg.content or msg.tool_calls

                if not content:
                    if stream_flag:
                        print()
                        stream_flag = False
                    continue

                if not stream_flag and content:
                    print(f"AI: {content}", end="", flush=True)
                    stream_flag = True
                    continue

                elif content:
                    print(f"{content}", end="", flush=True)

            if isinstance(msg, ToolMessage):
                print(f"Tool: {msg.content}")


def get_cur_time_with_utc():
    return datetime.now(tz=UTC).isoformat()
