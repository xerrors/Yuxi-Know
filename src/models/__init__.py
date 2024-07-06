from models.chat_model import DeepSeek, Zhipu



def select_model(config):

    model_provider = config.model_provider
    model_name = config.model_name

    if model_provider == "deepseek":
        return DeepSeek(model_name)
    elif model_provider == "zhipu":
        return Zhipu(model_name)
    elif model_provider is None:
        raise ValueError("Model provider not specified, please modify `model_provider` in `src/config/base.yaml`")
    else:
        raise ValueError(f"Model provider {model_provider} not supported")
