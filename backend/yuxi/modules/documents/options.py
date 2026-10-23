"""本模块拥有的管理员配置定义。"""

from yuxi.modules.system.services.options import Option

mineru_ocr_host_opts = Option(
    key="mineru_ocr_host_opts",
    name="MinerU 服务",
    description="配置自托管 MinerU 服务地址、默认解析后端与强度。",
    params={
        "fields": [
            {
                "key": "server_url",
                "label": "服务地址",
                "type": "url",
                "environment": "MINERU_API_URI",
                "placeholder": "http://mineru-api:30001",
                "help": "留空时读取 MINERU_API_URI。",
            },
            {
                "key": "backend",
                "label": "解析后端",
                "type": "string",
                "default": "hybrid-engine",
                "choices": ["hybrid-engine", "vlm-engine"],
                "choice_labels": {"hybrid-engine": "Hybrid（混合解析）", "vlm-engine": "VLM（视觉模型解析）"},
                "help": "Hybrid 结合传统解析与视觉模型；VLM 使用视觉模型解析。",
            },
            {
                "key": "effort",
                "label": "解析强度",
                "type": "string",
                "default": "medium",
                "choices": ["medium", "high"],
                "choice_labels": {"medium": "标准（medium）", "high": "高精度（high）"},
                "help": "仅对 Hybrid 生效。标准模式更快，不分析图片与图表；高精度模式支持图片与图表分析，耗时更长。",
            },
        ]
    },
)

mineru_official_api_opts = Option(
    key="mineru_official_api_opts",
    name="MinerU Official",
    description="配置 MinerU 官方云服务凭证与默认解析模型。",
    params={
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "environment": "MINERU_API_KEY",
                "sensitive": True,
                "help": "留空时读取 MINERU_API_KEY，建议优先使用环境变量。",
            },
            {
                "key": "model_version",
                "label": "解析模型",
                "type": "string",
                "default": "pipeline",
                "choices": ["pipeline", "vlm"],
                "choice_labels": {"pipeline": "Pipeline（传统解析）", "vlm": "VLM（视觉模型解析）"},
                "help": "Pipeline 使用传统解析流程；VLM 使用视觉模型解析。保存后对后续解析生效。",
            },
        ]
    },
)

pp_structure_v3_ocr_host_opts = Option(
    key="pp_structure_v3_ocr_host_opts",
    name="PP-Structure-V3 服务",
    description="配置自托管 PaddleX 服务地址。",
    params={
        "fields": [
            {
                "key": "server_url",
                "label": "服务地址",
                "type": "url",
                "environment": "PADDLEX_URI",
                "placeholder": "http://paddlex:8080",
                "help": "留空时读取 PADDLEX_URI。",
            }
        ]
    },
)

paddleocr_api_opts = Option(
    key="paddleocr_api_opts",
    name="PaddleOCR API",
    description="PaddleOCR-VL 和 PP-OCRv6 共用此配置。",
    params={
        "fields": [
            {
                "key": "api_url",
                "label": "API 地址",
                "type": "url",
                "environment": "PADDLEOCR_API_URL",
                "placeholder": "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
                "help": "留空时读取 PADDLEOCR_API_URL。",
            },
            {
                "key": "api_token",
                "label": "Access Token",
                "type": "password",
                "environment": "PADDLEOCR_API_TOKEN",
                "sensitive": True,
                "help": "留空时读取 PADDLEOCR_API_TOKEN，建议优先使用环境变量。",
            },
        ]
    },
)

DOCUMENT_OPTIONS = (mineru_ocr_host_opts, mineru_official_api_opts, pp_structure_v3_ocr_host_opts, paddleocr_api_opts)
