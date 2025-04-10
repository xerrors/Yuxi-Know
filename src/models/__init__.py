import os
import traceback
from src import config
from src.utils.logging_config import logger
from src.models.chat_model import OpenAIBase


def select_model(model_provider=None, model_name=None):
    """根据模型提供者选择模型"""
    model_provider = model_provider or config.model_provider
    model_info = config.model_names.get(model_provider, {})
    model_name = model_name or config.model_name or model_info.get("default", "")


    logger.info(f"Selecting model from `{model_provider}` with `{model_name}`")


    if model_provider is None:
        raise ValueError("Model provider not specified, please modify `model_provider` in `src/config/base.yaml`")

    if model_provider == "qianfan":
        from src.models.chat_model import Qianfan
        return Qianfan(model_name)

    if model_provider == "dashscope":
        from src.models.chat_model import DashScope
        return DashScope(model_name)

    if model_provider == "openai":
        from src.models.chat_model import OpenModel
        return OpenModel(model_name)

    if model_provider == "custom":
        model_info = next((x for x in config.custom_models if x["custom_id"] == model_name), None)
        if model_info is None:
            raise ValueError(f"Model {model_name} not found in custom models")

        from src.models.chat_model import CustomModel
        return CustomModel(model_info)

    # 其他模型，默认使用OpenAIBase
    try:
        model = OpenAIBase(
            api_key=os.getenv(model_info["env"][0]),
            base_url=model_info["base_url"],
            model_name=model_name,
        )
        return model
    except Exception as e:
        raise ValueError(f"Model provider {model_provider} load failed, {e} \n {traceback.format_exc()}")
