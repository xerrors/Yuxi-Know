"""各域配置定义的显式汇总，持久化与运行时读取由各自 Owner 提供。"""

from yuxi.modules.system.services.options import Option

system_options = Option(
    key="system_options",
    name="系统配置",
    description="API 与 worker 共用的管理员配置。",
    params={
        "internal": True,
        "fields": [
            {
                "key": "web_search_provider",
                "label": "默认搜索供应商",
                "type": "string",
                "environment": "WEB_SEARCH_PROVIDER",
                "default": "",
                "choices": ["", "tavily", "deepseek", "doubao"],
            },
            {
                "key": "web_fetch_provider",
                "label": "默认网页抓取供应商",
                "type": "string",
                "default": "",
                "choices": ["", "tavily", "deepseek"],
            },
            {
                "key": "default_model",
                "label": "默认对话模型",
                "type": "model",
                "default": "siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash",
            },
            {
                "key": "fast_model",
                "label": "快速响应模型",
                "type": "model",
                "default": "siliconflow-cn:deepseek-ai/DeepSeek-V4-Flash",
            },
            {
                "key": "embed_model",
                "label": "默认 Embedding 模型",
                "type": "model",
                "default": "siliconflow-cn:Pro/BAAI/bge-m3",
            },
            {
                "key": "reranker",
                "label": "默认 Re-Ranker 模型",
                "type": "model",
                "default": "siliconflow-cn:Pro/BAAI/bge-reranker-v2-m3",
            },
            {
                "key": "max_cooperation_depth",
                "label": "最大协作深度",
                "type": "integer",
                "min": 0,
                "default": 2,
            },
            {
                "key": "default_ocr_engine",
                "label": "默认 OCR 解析引擎",
                "type": "ocr_engine",
                "default": "rapid_ocr",
            },
        ],
    },
)


def get_option_definitions() -> dict[str, Option]:
    """显式汇总各模块配置，系统管理机制不拥有领域定义。"""
    from yuxi.modules.documents.options import DOCUMENT_OPTIONS
    from yuxi.modules.extensions.options import WEB_PROVIDER_OPTIONS, remote_skill_source_policy

    return {
        option.key: option for option in (*DOCUMENT_OPTIONS, *WEB_PROVIDER_OPTIONS.values(), remote_skill_source_policy, system_options)
    }
