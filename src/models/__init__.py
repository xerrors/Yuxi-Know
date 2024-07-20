from utils.logging_config import logger


def select_model(config):

    model_provider = config.model_provider
    model_name = config.model_name

    logger.info(f"Selecting model from {model_provider} with name {model_name}")

    if model_provider == "deepseek":
        from models.chat_model import DeepSeek
        return DeepSeek(model_name)

    elif model_provider == "zhipu":
        from models.chat_model import Zhipu
        return Zhipu(model_name)

    elif model_provider == "qianfan":
        from models.chat_model import Qianfan
        return Qianfan(model_name)

    elif model_provider == "vllm":
        from models.chat_model import VLLM
        return VLLM(model_name)

    elif model_provider is None:
        raise ValueError("Model provider not specified, please modify `model_provider` in `src/config/base.yaml`")
    else:
        raise ValueError(f"Model provider {model_provider} not supported")
