import os
import traceback

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src import config
from src.models import get_custom_model
from src.utils import get_docker_safe_url


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
            stream_usage=True,
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
            stream_usage=True,
        )

    elif provider == "together":
        from langchain_together import ChatTogether

        return ChatTogether(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            stream_usage=True,
        )

    else:
        try:  # 其他模型，默认使用OpenAIBase, like openai, zhipuai
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                api_key=SecretStr(api_key),
                base_url=base_url,
                stream_usage=True,
            )
        except Exception as e:
            raise ValueError(f"Model provider {provider} load failed, {e} \n {traceback.format_exc()}")
