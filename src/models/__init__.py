from src.utils.logging_config import logger


def select_model(config):

    model_provider = config.model_provider
    model_name = config.model_name

    logger.info(f"Selecting model from {model_provider} with {model_name}")

    if model_provider == "deepseek":
        from src.models.chat_model import DeepSeek
        return DeepSeek(model_name)

    elif model_provider == "zhipu":
        from src.models.chat_model import Zhipu
        return Zhipu(model_name)

    elif model_provider == "qianfan":
        from src.models.chat_model import Qianfan
        return Qianfan(model_name)

    elif model_provider == "dashscope":
        from src.models.chat_model import DashScope
        return DashScope(model_name)

    elif model_provider == "openai":
        from src.models.chat_model import OpenModel
        return OpenModel(model_name)

    elif model_provider == "siliconflow":
        from src.models.chat_model import SiliconFlow
        return SiliconFlow(model_name)

    elif model_provider == "custom":
        model_info = next((x for x in config.custom_models if x["custom_id"] == model_name), None)
        if model_info is None:
            raise ValueError(f"Model {model_name} not found in custom models")

        from src.models.chat_model import CustomModel
        return CustomModel(model_info)

    elif model_provider is None:
        raise ValueError("Model provider not specified, please modify `model_provider` in `src/config/base.yaml`")
    else:
        raise ValueError(f"Model provider {model_provider} not supported")
