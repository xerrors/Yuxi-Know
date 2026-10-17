"""本模块拥有的管理员配置定义。"""

from yuxi.modules.system.services.options import Option

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
    provider: Option(
        key=f"{provider}_search_opts",
        name=name,
        description="网页搜索与正文抓取凭据。" if provider != "doubao" else "豆包 Custom 网页搜索凭据。",
        params={
            "fields": [
                {
                    "key": "api_key",
                    "label": "API Key",
                    "type": "password",
                    "sensitive": True,
                    "environment": environment,
                }
            ],
        },
    )
    for provider, name, environment in (
        ("tavily", "Tavily", "TAVILY_API_KEY"),
        ("deepseek", "DeepSeek", "DEEPSEEK_API_KEY"),
        ("doubao", "豆包 Custom", "DOUBAO_SEARCH_API_KEY"),
    )
}
