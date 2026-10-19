"""远程 MCP 清单与持久化配置的输入契约。"""

from typing import Annotated, Any, Literal

from httpx import URL, InvalidURL
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


class RemoteMCPConfig(BaseModel):
    """校验远程连接和展示字段，拒绝进程配置。"""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    name: StrictStr = Field(min_length=1, max_length=100)
    transport: Literal["sse", "streamable_http"]
    url: StrictStr = Field(min_length=1, max_length=500)
    headers: dict[str, StrictStr] | None = None
    timeout: Annotated[StrictInt, Field(gt=0, le=2147483647)] | None = None
    sse_read_timeout: Annotated[StrictInt, Field(gt=0, le=2147483647)] | None = None
    description: StrictStr | None = Field(None, max_length=500)

    @field_validator("url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        """仅接受带主机名的 HTTP URL。"""
        try:
            parsed = URL(value)
        except InvalidURL as exc:
            raise ValueError("MCP 需要有效的 HTTP URL") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.host
            or "%" in parsed.host
            or (parsed.port is not None and not 0 <= parsed.port <= 65535)
        ):
            raise ValueError("MCP 需要有效的 HTTP URL")
        return value


def normalize_mcp_manifest_entry(slug: str, config: dict[str, Any]) -> dict[str, Any]:
    """将清单中的连接与 extra_data 转为持久化字段。"""
    if set(config) - {"type", "transport", "url", "headers", "timeout", "sse_read_timeout", "extra_data"}:
        raise ValueError(f"MCP '{slug}' 包含不支持的连接字段")
    extra_data = config.get("extra_data", {})
    if not isinstance(extra_data, dict) or set(extra_data) - {"name", "description"}:
        raise ValueError(f"MCP '{slug}' 的 extra_data 无效")

    transport = config.get("transport", config.get("type"))
    transport = "streamable_http" if transport == "http" else transport
    declared_type = config.get("type")
    declared_type = "streamable_http" if declared_type == "http" else declared_type
    if "type" in config and "transport" in config and declared_type != transport:
        raise ValueError(f"MCP '{slug}' 的 type 与 transport 不一致")

    fields = {key: value for key, value in config.items() if key not in {"type", "transport", "extra_data"}}
    return RemoteMCPConfig.model_validate(
        {**fields, **extra_data, "slug": slug, "name": extra_data.get("name") or slug, "transport": transport}
    ).model_dump()
