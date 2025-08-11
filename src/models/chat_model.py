import os
import requests
from openai import OpenAI
from src.utils import logger, get_docker_safe_url
from langchain_openai import ChatOpenAI

class OpenAIBase:
    def __init__(self, api_key, base_url, model_name, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.info = kwargs

    def predict(self, message, stream=False):
        if isinstance(message, str):
            messages=[{"role": "user", "content": message}]
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
            err = f"Error streaming response: {e}, URL: {self.base_url}, API Key: {self.api_key[:5]}***, Model: {self.model_name}"
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
            return self.client.models.list(
                extra_query={
                    "type": "text"
                }
            )
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

if __name__ == "__main__":
    pass
