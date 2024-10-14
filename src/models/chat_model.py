import os
from openai import OpenAI
from src.utils.logging_config import setup_logger


logger = setup_logger(__name__)

class OpenAIBase():
    def __init__(self, api_key, base_url, model_name):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

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
            yield chunk.choices[0].delta

    def _get_response(self, messages):
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message


class OpenModel(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "gpt-4o-mini"
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class DeepSeek(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "deepseek-chat"
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = "https://api.deepseek.com"
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class Zhipu(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "glm-4-flash"
        api_key = os.getenv("ZHIPUAI_API_KEY", "270ea71e9560c0ff406acbcdd48bfd97.e3XOMdWKuZb7Q1Sk")
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)

class SiliconFlow(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "meta-llama/Meta-Llama-3.1-8B-Instruct"
        api_key = os.getenv("SILICONFLOW_API_KEY")
        base_url = "https://api.siliconflow.cn/v1"
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)

class CustomModel(OpenAIBase):
    def __init__(self, model_info):
        model_name = model_info["name"]
        api_key = model_info["api_key"]
        base_url = model_info["api_base"]
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class GeneralResponse:
    def __init__(self, content):
        self.content = content
        self.is_full = False


class Qianfan:

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



class DashScope:

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
            message.is_full = True
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
    model = SiliconFlow()
    for a in model.predict("你好", stream=True):
        print(a.content, end="")