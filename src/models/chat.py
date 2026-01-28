import os
import traceback

from openai import AsyncOpenAI
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src import config
from src.utils import logger


def split_model_spec(model_spec, sep="/"):
    """
    将 provider/model 形式的字符串拆分为 (provider, model)
    """
    if not model_spec or not isinstance(model_spec, str):
        return "", ""
    if not sep:
        return model_spec, ""
    try:
        provider, model_name = model_spec.split(sep, 1)
        return provider, model_name
    except ValueError:
        return model_spec, ""


class OpenAIBase:
    def __init__(self, api_key, base_url, model_name, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.info = kwargs

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=before_sleep_log(logger, log_level="WARNING"),
        reraise=True,
    )
    async def call(self, message, stream=False):
        if isinstance(message, str):
            messages = [{"role": "user", "content": message}]
        else:
            messages = message

        try:
            if stream:
                response = self._stream_response(messages)
            else:
                response = await self._get_response(messages)

        except Exception as e:
            err = (
                f"Error streaming response: {e}, URL: {self.base_url}, "
                f"API Key: {self.api_key[:5]}***, Model: {self.model_name}"
            )
            logger.error(err)
            raise Exception(err)

        return response

    async def _stream_response(self, messages):
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
        )
        async for chunk in response:
            if len(chunk.choices) > 0:
                yield chunk.choices[0].delta

    async def _get_response(self, messages):
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message

    async def get_models(self):
        try:
            return await self.client.models.list(extra_query={"type": "text"})
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []


class OpenModel(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "gpt-4o-mini"
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class GeneralResponse:
    def __init__(self, content):
        self.content = content
        self.is_full = False


def select_model(model_provider=None, model_name=None, model_spec=None):
    """根据模型提供者选择模型"""
    if model_spec:
        spec_provider, spec_model_name = split_model_spec(model_spec)
        model_provider = model_provider or spec_provider
        model_name = model_name or spec_model_name

    if model_provider is None or not model_name:
        default_provider, default_model = split_model_spec(getattr(config, "default_model", ""))
        model_provider = model_provider or default_provider
        model_name = model_name or default_model

    assert model_provider, "Model provider not specified"

    model_info = config.model_names.get(model_provider)
    if not model_info:
        raise ValueError(f"Unknown model provider: {model_provider}")

    model_name = model_name or model_info.default

    if not model_name:
        raise ValueError(f"Model name not specified for provider {model_provider}")

    logger.info(f"Selecting model from `{model_provider}` with `{model_name}`")

    if model_provider == "openai":
        return OpenModel(model_name)

    # 其他模型，默认使用OpenAIBase
    try:
        model = OpenAIBase(
            api_key=os.environ.get(model_info.env, model_info.env),
            base_url=model_info.base_url,
            model_name=model_name,
        )
        return model
    except Exception as e:
        raise ValueError(f"Model provider {model_provider} load failed, {e} \n {traceback.format_exc()}")


async def test_chat_model_status(provider: str, model_name: str) -> dict:
    """
    测试指定聊天模型的状态

    Args:
        provider: 模型提供商
        model_name: 模型名称

    Returns:
        dict: 包含状态信息的字典
    """
    try:
        # 加载模型
        logger.debug(f"Selecting chat model {provider}/{model_name}")
        model = select_model(provider, model_name)

        # 使用简单的测试消息
        test_messages = [{"role": "user", "content": "Say 1"}]

        # 发送测试请求
        response = await model.call(test_messages, stream=False)
        logger.debug(f"Test chat model status response: {response}")

        # 检查响应是否有效
        if response and response.content:
            return {"provider": provider, "model_name": model_name, "status": "available", "message": "连接正常"}
        else:
            return {"provider": provider, "model_name": model_name, "status": "unavailable", "message": "响应无效"}

    except Exception as e:
        logger.error(f"测试聊天模型状态失败 {provider}/{model_name}: {e}")
        return {"provider": provider, "model_name": model_name, "status": "error", "message": str(e)}


async def test_all_chat_models_status() -> dict:
    """
    测试所有支持的聊天模型状态

    Returns:
        dict: 包含所有模型状态的字典
    """
    from src import config

    results = {}

    # 获取所有可用的模型
    for provider, provider_info in config.model_names.items():
        # 处理普通模型
        for model_name in provider_info.models:
            model_id = f"{provider}/{model_name}"
            status = await test_chat_model_status(provider, model_name)
            results[model_id] = status

    available_count = len([m for m in results.values() if m["status"] == "available"])

    return {"models": results, "total": len(results), "available": available_count}


if __name__ == "__main__":
    pass
