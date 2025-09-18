import os
import traceback

from openai import OpenAI

from src import config
from src.utils import get_docker_safe_url, logger


class OpenAIBase:
    def __init__(self, api_key, base_url, model_name, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.info = kwargs

    def predict(self, message, stream=False):
        if isinstance(message, str):
            messages = [{"role": "user", "content": message}]
        else:
            messages = message

        if stream:
            return self._stream_response(messages)
        else:
            return self._get_response(messages)

    def _stream_response(self, messages):
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                stream=True,
            )
            for chunk in response:
                if len(chunk.choices) > 0:
                    yield chunk.choices[0].delta

        except Exception as e:
            err = (
                f"Error streaming response: {e}, URL: {self.base_url}, "
                f"API Key: {self.api_key[:5]}***, Model: {self.model_name}"
            )
            logger.error(err)
            raise Exception(err)

    def _get_response(self, messages):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message

    def get_models(self):
        try:
            return self.client.models.list(extra_query={"type": "text"})
        except Exception as e:
            logger.error(f"Error getting models: {e}")
            return []


class OpenModel(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "gpt-4o-mini"
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class CustomModel(OpenAIBase):
    def __init__(self, model_info):
        model_name = model_info["name"]
        api_key = model_info.get("api_key") or "custom_model"
        base_url = get_docker_safe_url(model_info["api_base"])
        logger.info(f"> Custom model: {model_name}, base_url: {base_url}")

        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class GeneralResponse:
    def __init__(self, content):
        self.content = content
        self.is_full = False


def select_model(model_provider, model_name=None):
    """根据模型提供者选择模型"""
    assert model_provider is not None, "Model provider not specified"
    model_info = config.model_names.get(model_provider, {})
    model_name = model_name or model_info.get("default", "")

    logger.info(f"Selecting model from `{model_provider}` with `{model_name}`")

    if model_provider == "openai":
        return OpenModel(model_name)

    if model_provider == "custom":
        model_info = get_custom_model(model_name)
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


def get_custom_model(model_id):
    """return model_info"""
    assert config.custom_models is not None, "custom_models is not set"
    modle_info = next((x for x in config.custom_models if x["custom_id"] == model_id), None)
    if modle_info is None:
        raise ValueError(f"Model {model_id} not found in custom models")
    return modle_info


if __name__ == "__main__":
    pass
