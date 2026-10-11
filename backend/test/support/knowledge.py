"""知识库集成测试的默认模型配置。"""

from yuxi.modules.system.options import system_options


def default_embedding_model_spec() -> str:
    """读取产品配置声明的默认 Embedding 模型。"""
    field = next(field for field in system_options.fields if field.get("key") == "embed_model")
    default = field.get("default")
    assert isinstance(default, str) and default
    return default
