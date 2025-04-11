"""
这里面存放是 RAG 相关的一些组件
"""

from src.utils import prompts

class BaseOperator:
    """
    基类
    """
    template = None

    def __init__(self):
        pass

    def call(self, **kwargs):
        pass

    def __call__(self, **kwargs):
        """
        所有 RAG 相关组件的调用接口
        """
        return self.call(**kwargs)



class HyDEOperator(BaseOperator):
    """
    HyDE 重写查询
    """
    template = prompts.HYDE_PROMPT_TEMPLATE

    def __init__(self):
        super().__init__()

    @classmethod
    def call(cls, model_callable, query, context_str, **kwargs):
        """
        重写查询

        Args:
            model_callable: 模型调用函数
            query: 查询
            context_str: 上下文
        """
        prompt = cls.template.format(query=query, context_str=context_str)
        response = model_callable(prompt)
        return response
