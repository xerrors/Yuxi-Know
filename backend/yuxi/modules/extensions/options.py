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
