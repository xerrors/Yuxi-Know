import os
import requests
from openai import OpenAI
from src.utils import logger, get_docker_safe_url
from langchain_openai import ChatOpenAI

class OpenAIBase():
    def __init__(self, api_key, base_url, model_name, **kwargs):
        self.api_key = api_key
        self.base_url = base_url
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name
        self.info = kwargs
        self.chat_open_ai = ChatOpenAI(model=model_name,
                                       api_key=api_key,
                                       base_url=base_url)

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
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
        )
        for chunk in response:
            if len(chunk.choices) > 0:
                yield chunk.choices[0].delta

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

    def _get_model_by_model_url(self, model_url):
        """
        Refs: https://docs.together.ai/reference/models-1

        Return: [
            {
                "id": "meta-llama/Meta-Llama-3-70B-Instruct-Turbo",
                "object": "model",
                "created": 0,
                "type": "chat",
                "running": false,
                "display_name": "Meta Llama 3 70B Instruct Turbo",
                "organization": "Meta",
                "link": "https://huggingface.co/meta-llama/Meta-Llama-3-70B-Instruct",
                "license": "Llama-3 (Other)",
                "context_length": 8192,
                "config": {
                    "chat_template": "{% set loop_messages = messages %}{% for message in loop_messages %}{% set content = '<|start_header_id|>' + message['role'] + '<|end_header_id|>\n\n'+ message['content'] | trim + '<|eot_id|>' %}{% if loop.index0 == 0 %}{% set content = bos_token + content %}{% endif %}{{ content }}{% endfor %}{{ '<|start_header_id|>assistant<|end_header_id|>\n\n' }}",
                    "stop": [
                        "<|eot_id|>"
                    ],
                    "bos_token": "<|begin_of_text|>",
                    "eos_token": "<|end_of_text|>"
                },
                "pricing": {
                    "hourly": 0,
                    "input": 0.88,
                    "output": 0.88,
                    "base": 0,
                    "finetune": 0
                }
            },
        ]

        """
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.api_key}"
        }
        response = requests.get(model_url, headers=headers)
        return response.json()



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


class Qianfan(OpenAIBase):
    """弃用"""

    def __init__(self, model_name="ernie_speed") -> None:
        import qianfan
        self.model_name = model_name
        access_key = os.getenv("QIANFAN_ACCESS_KEY")
        secret_key = os.getenv("QIANFAN_SECRET_KEY")
        self.client = qianfan.ChatCompletion(ak=access_key, sk=secret_key)

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
        response = self.client.do(
            model=self.model_name,
            messages=messages,
            stream=True,
        )
        for chunk in response:
            yield GeneralResponse(chunk["body"]["result"])

    def _get_response(self, messages):
        response = self.client.do(
            model=self.model_name,
            messages=messages,
            stream=False,
        )
        return GeneralResponse(response["body"]["result"])



class DashScope(OpenAIBase):

    def __init__(self, model_name="qwen-max-latest") -> None:
        self.model_name = model_name
        self.api_key= os.getenv("DASHSCOPE_API_KEY")

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
        import dashscope
        response = dashscope.Generation.call(
            api_key=self.api_key,
            model=self.model_name,
            messages=messages,
            result_format='message',
            stream=True,
        )
        for chunk in response:
            message = chunk.output.choices[0].message
            message.is_full = False
            yield chunk.output.choices[0].message

    def _get_response(self, messages):
        import dashscope
        response = dashscope.Generation.call(
            api_key=self.api_key,
            model=self.model_name,
            messages=messages,
            result_format='message',
            stream=False,
        )
        return response.output.choices[0].message


if __name__ == "__main__":
    pass