"""启动时汇总各域配置并同步持久定义。"""

from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.modules.system.options import get_option_definitions
from yuxi.modules.system.repositories.options import sync_option_definitions


async def ensure_options_in_db(db: AsyncSession):
    """保留管理员值，幂等更新代码拥有的定义。"""
    return await sync_option_definitions(db, get_option_definitions())
