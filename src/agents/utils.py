from datetime import datetime, timezone, UTC
import asyncio
import os
import traceback

from src import config
from src.utils import logger, get_docker_safe_url
from src.models import get_custom_model
from src.agents.registry import BaseAgent
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessageChunk, ToolMessage
from pydantic import SecretStr




def load_chat_model(fully_specified_name: str, **kwargs) -> BaseChatModel:
    """
    Load a chat model from a fully specified name.
    """
    provider, model = fully_specified_name.split("/", maxsplit=1)

    if provider == "custom":
        from langchain_openai import ChatOpenAI
        model_info = get_custom_model(model)
        api_key = model_info.get("api_key") or "custom_model"
        base_url = get_docker_safe_url(model_info["api_base"])
        model_name = model_info.get("name") or "custom_model"
        return ChatOpenAI(
            model=model_name,
            api_key=SecretStr(api_key),
            base_url=base_url,
        )

    model_info = config.model_names.get(provider, {})
    api_key = os.getenv(model_info["env"][0], model_info["env"][0])
    base_url = get_docker_safe_url(model_info["base_url"])

    if provider in ["deepseek", "dashscope"]:
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            api_base=base_url,
        )

    elif provider == "together":
        from langchain_together import ChatTogether
        return ChatTogether(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
        )

    else:
        try:  # 其他模型，默认使用OpenAIBase, like openai, zhipuai
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                api_key=SecretStr(api_key),
                base_url=base_url,
            )
        except Exception as e:
            raise ValueError(f"Model provider {provider} load failed, {e} \n {traceback.format_exc()}")



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

