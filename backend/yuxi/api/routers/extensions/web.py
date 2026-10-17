"""超级管理员网页工具测试入口。"""

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_db, get_superadmin_user
from yuxi.modules.extensions.web.schemas import FetchInput, FetchProvider, SearchInput, SearchProvider
from yuxi.modules.extensions.web.services import fetch_web, search_web
from yuxi.modules.identity.models import User


class WebToolRoute(APIRoute):
    """网页测试表单校验失败时不回显输入中的凭据。"""

    def get_route_handler(self):
        """只保留错误定位与类型，不序列化原始 input 或 ctx。"""
        handler = super().get_route_handler()

        async def validate_without_inputs(request):
            """将本路由的请求校验错误转换为脱敏协议结果。"""
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": [{"loc": list(error["loc"]), "type": error["type"], "msg": "网页工具参数无效"} for error in exc.errors()],
                    },
                )

        return validate_without_inputs


web_tools = APIRouter(prefix="/system/web-tools", tags=["web-tools"], route_class=WebToolRoute)


class SearchTestInput(SearchInput):
    """管理员指定供应商与可选的本次测试凭据。"""

    provider: SearchProvider
    api_key: str | None = Field(default=None, repr=False)


class FetchTestInput(FetchInput):
    """管理员指定正文接口与可选的本次测试凭据。"""

    provider: FetchProvider
    api_key: str | None = Field(default=None, repr=False)


@web_tools.post("/search/test")
async def test_search(
    payload: SearchTestInput,
    user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """搜索测试不持久化草稿，不改变系统默认项。"""
    request = SearchInput.model_validate(payload.model_dump(exclude={"provider", "api_key"}))
    return await search_web(request, provider=payload.provider, api_key=payload.api_key, db=db)


@web_tools.post("/fetch/test")
async def test_fetch(
    payload: FetchTestInput,
    user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """网页正文测试与 Agent 工具使用相同的服务边界。"""
    return await fetch_web(FetchInput(url=payload.url), provider=payload.provider, api_key=payload.api_key, db=db)
