"""本模块拥有的管理员配置定义。"""

from yuxi.modules.system.services.options import Option

mineru_ocr_host_opts = Option(
    key="mineru_ocr_host_opts",
    name="MinerU 服务",
    description="配置自托管 MinerU 服务地址。",
    params={
        "fields": [
            {
                "key": "server_url",
                "label": "服务地址",
                "type": "url",
                "environment": "MINERU_API_URI",
                "placeholder": "http://mineru-api:30001",
                "help": "留空时读取 MINERU_API_URI。",
            }
        ]
    },
)

mineru_official_api_opts = Option(
    key="mineru_official_api_opts",
    name="MinerU Official",
    description="配置 MinerU 官方云服务凭证。",
    params={
        "fields": [
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "environment": "MINERU_API_KEY",
                "sensitive": True,
                "help": "留空时读取 MINERU_API_KEY，建议优先使用环境变量。",
            }
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
