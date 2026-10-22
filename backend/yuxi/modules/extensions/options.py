"""本模块拥有的管理员配置定义。"""

from yuxi.modules.system.services.options import Option
from yuxi.shared.web_providers import WEB_PROVIDERS

remote_skill_source_policy = Option(
    key="remote_skill_source_policy",
    name="远程 Skill 来源",
    description="配置允许远程安装 Skill 的来源域名。",
    params={
        "fields": [
            {
                "key": "allowed_hosts",
                "label": "允许的来源域名",
                "type": "list[str]",
                "default": ["github.com", "modelscope.cn"],
                "help": "仅精确匹配域名；保存空列表会关闭远程安装。",
            }
        ]
    },
)

WEB_PROVIDER_OPTIONS = {
    provider.id: Option(
        key=f"{provider.id}_search_opts",
        name=provider.name,
        description="网页搜索与正文抓取凭据。" if provider.supports_fetch else f"{provider.name} 网页搜索凭据。",
        params={
            "provider": {
                "id": provider.id,
                "supports_fetch": provider.supports_fetch,
                "environment": provider.environment,
            },
            "fields": [
                {
                    "key": "api_key",
                    "label": "API Key",
                    "type": "password",
                    "sensitive": True,
                    "environment": provider.environment,
                }
            ],
        },
    )
    for provider in WEB_PROVIDERS
}
