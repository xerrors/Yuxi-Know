import os
import traceback

from openai import AsyncOpenAI
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from yuxi import config
from yuxi.services.model_cache import is_v2_spec_format
from yuxi.utils import logger


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


def select_model_v2(spec: str) -> OpenAIBase:
    """根据 v2 spec（provider_id:model_id）选择聊天模型。

    v2 spec 格式使用冒号分隔，如: siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash
    数据来源为数据库中的 model_providers 表，通过全局缓存访问。
    """
    from yuxi.services.model_cache import model_cache

    info = model_cache.get_model_info(spec)
    if not info:
        raise ValueError(f"Unknown v2 model spec: {spec}")

    if info.model_type != "chat":
        raise ValueError(f"Model {spec} is not a chat model (type={info.model_type})")

    logger.info(f"Selecting v2 model: {spec} (provider_type={info.provider_type})")

    return OpenAIBase(
        api_key=info.api_key,
        base_url=info.base_url,
        model_name=info.model_id,
    )


def select_model(model_provider=None, model_name=None, model_spec=None):
    """根据模型提供者选择模型"""
    if model_spec and is_v2_spec_format(model_spec):
        from yuxi.services.model_cache import model_cache

        if model_cache.is_v2_spec(model_spec):
            return select_model_v2(model_spec)

        available = model_cache.get_all_specs("chat")
        available_ids = [s.spec for s in available[:10]]
        raise ValueError(f"未找到 V2 模型: '{model_spec}'。可用聊天模型 ({len(available)}): {available_ids}")

    logger.warning(
        f"旧版本的模型选择逻辑已废弃，建议尽快迁移至新的模型配置；"
        f"当前模型选择参数: provider={model_provider}, model_name={model_name}, spec={model_spec}"
    )

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


async def test_chat_model_status_by_spec(spec: str) -> dict:
    """根据 full spec 测试聊天模型状态（自动识别 V1/V2）。

    V1 spec 格式: provider/model_name（斜杠分隔）
    V2 spec 格式: provider_id:model_id（冒号分隔）
    """
    try:
        logger.debug(f"Testing model status by spec: {spec}")
        model = select_model(model_spec=spec)

        test_messages = [{"role": "user", "content": "Say 1"}]
        response = await model.call(test_messages, stream=False)

        if response and response.content:
            return {"spec": spec, "status": "available", "message": "连接正常"}
        else:
            return {"spec": spec, "status": "unavailable", "message": "响应无效"}

    except Exception as e:
        logger.error(f"测试模型状态失败 {spec}: {e}")
        return {"spec": spec, "status": "error", "message": str(e)}


if __name__ == "__main__":
    pass
