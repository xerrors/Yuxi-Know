import os
from openai import OpenAI
from src.utils.logging_config import setup_logger


logger = setup_logger(__name__)

class OpenAIBase():
    def __init__(self, api_key, base_url, model_name):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def predict(self, message, stream=False):

        logger.debug(message)
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


class DeepSeek(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "deepseek-chat"
        api_key = os.getenv("DEEPSEEKAPI")
        base_url = "https://api.deepseek.com"
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)


class Zhipu(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "glm-4"
        api_key = os.getenv("ZHIPUAPI")
        base_url = "https://open.bigmodel.cn/api/paas/v4/"
        super().__init__(api_key=api_key, base_url=base_url, model_name=model_name)

class VLLM(OpenAIBase):
    def __init__(self, model_name=None):
        model_name = model_name or "vllm"
        api_key = os.getenv("VLLM_API_KEY")
        base_url = os.getenv("VLLM_API_BASE")
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

    def __init__(self, model_name="qwen-long") -> None:
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
    model = DashScope()
    for a in model.predict("你好", stream=True):
        print(a.content)