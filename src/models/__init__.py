from src.utils.logging_config import logger
from src.models.chat_model import OpenModel, DeepSeek, Zhipu, Qianfan, DashScope, SiliconFlow
from src.models.embedding import get_embedding_model


def select_model(config):
    """
    根据配置选择模型
    """
    if config.model_provider == "deepseek":
        return DeepSeek(config.model_name)
    elif config.model_provider == "zhipu":
        return Zhipu(config.model_name)
    elif config.model_provider == "openai":
        return OpenModel(config.model_name)
    elif config.model_provider == "qianfan":
        return Qianfan(config.model_name)
    elif config.model_provider == "dashscope":
        return DashScope(config.model_name)
    elif config.model_provider == "siliconflow":
        return SiliconFlow(config.model_name)
    else:
        raise ValueError(f"Unsupported model provider: {config.model_provider}")
