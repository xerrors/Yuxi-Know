from models.chat_model import DeepSeek, Zhipu



def select_model(config):

    model_provider = config.model_provider
    model_name = config.model_name

    if model_provider == "deepseek":
        from models.chat_model import DeepSeek
        return DeepSeek(model_name)

    elif model_provider == "zhipu":
        from models.chat_model import Zhipu
        return Zhipu(model_name)

    elif model_provider == "wenxin":
        from models.chat_model import Wenxin
        return Wenxin(model_name)

    elif model_provider is None:
        raise ValueError("Model provider not specified, please modify `model_provider` in `src/config/base.yaml`")
    else:
        raise ValueError(f"Model provider {model_provider} not supported")
