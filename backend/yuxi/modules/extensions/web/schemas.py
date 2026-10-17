"""网页工具输入与归一化结果。"""

from datetime import date
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

SearchProvider = Literal["tavily", "deepseek", "doubao"]
FetchProvider = Literal["tavily", "deepseek"]


class SearchInput(BaseModel):
    """各供应商共用的搜索输入。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="精准描述检索需求的搜索词")
    count: int = Field(default=10, ge=1, le=50, description="结果条数；Tavily 最多 20 条，其他供应商最多 50 条")
    time_range: str | None = Field(default=None, description="OneDay/OneWeek/OneMonth/OneYear 或 YYYY-MM-DD..YYYY-MM-DD")
    sites: list[str] | None = Field(default=None, max_length=20, description="限定完整域名")
    block_hosts: list[str] | None = Field(default=None, max_length=5, description="排除完整域名")
    content_format: Literal["text", "markdown"] = "markdown"
    include_raw_content: bool = Field(default=False, description="是否同时返回可用的网页正文")

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        """拒绝空白查询，不静默截断供应商输入。"""
        if not value.strip():
            raise ValueError("搜索词不能为空白")
        return value.strip()

    @field_validator("time_range")
    @classmethod
    def validate_time_range(cls, value: str | None) -> str | None:
        """校验跨供应商时间筛选语义。"""
        if value is None or value in {"OneDay", "OneWeek", "OneMonth", "OneYear"}:
            return value
        start, separator, end = value.partition("..")
        if not separator or date.fromisoformat(start) > date.fromisoformat(end):
            raise ValueError("时间范围必须是有效的起止日期")
        return value

    @field_validator("sites", "block_hosts")
    @classmethod
    def validate_domains(cls, value: list[str] | None) -> list[str] | None:
        """站点过滤仅接受域名，避免拼接供应商查询语法。"""
        if value is not None:
            for domain in value:
                if not domain or any(not (character.isalnum() or character in ".-") for character in domain):
                    raise ValueError("站点过滤必须填写完整域名")
        return value


class FetchInput(BaseModel):
    """单页抓取输入。"""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(min_length=1, max_length=8192, description="要读取的公开 HTTP/HTTPS 网页 URL")

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        """拒绝非网页协议、缺少主机或夹带凭据的 URL。"""
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(character.isspace() or ord(character) < 32 for character in value)
        ):
            raise ValueError("URL 必须为不含账号密码的 HTTP/HTTPS 网页地址")
        _ = parsed.port
        return value


class SearchResult(BaseModel):
    """保留摘要、相关片段、正文和供应商原始分数。"""

    title: str
    url: str
    snippet: str = ""
    relevant_content: str = ""
    raw_content: str = ""
    score: float | None = None
    score_max: int
    site_name: str | None = None
    publish_time: str | None = None

    @field_validator("url")
    @classmethod
    def validate_result_url(cls, value: str) -> str:
        """供应商链接只能作为普通网页地址展示。"""
        return FetchInput.validate_url(value)
