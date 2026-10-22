from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from sqlalchemy import func, select

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

SUPERADMIN_UID = "zwj"
SUPERADMIN_NAME = "张文杰"
SUPERADMIN_PHONE_NUMBER = "15251638888"
SUPERADMIN_PASSWORD = "zwj12138"
DEFAULT_USER_PASSWORD = "yuxi123456"


class DepartmentSeed(TypedDict):
    name: str
    description: str
    prefix: str
    normal_count: int


DEPARTMENTS: list[DepartmentSeed] = [
    {"name": "研发部", "description": "负责产品研发与技术平台建设", "prefix": "dev", "normal_count": 5},
    {"name": "产品部", "description": "负责产品规划、需求分析与项目推进", "prefix": "prod", "normal_count": 5},
    {"name": "运营部", "description": "负责业务运营、用户支持与内容维护", "prefix": "ops", "normal_count": 4},
]


class SeedError(Exception):
    pass


def load_project_env() -> None:
    load_dotenv(APP_ROOT / ".env", override=False)
    load_dotenv(APP_ROOT.parent / ".env", override=False)
    load_dotenv(Path.cwd() / ".env", override=False)


async def ensure_uninitialized(session) -> None:
    from yuxi.modules.identity.models import User

    user_count = await session.scalar(select(func.count(User.id)))
    if user_count:
        raise SeedError(f"系统已初始化：users 表已有 {user_count} 个用户，脚本已退出。")

    superadmin_count = await session.scalar(select(func.count(User.id)).where(User.role == "superadmin"))
    if superadmin_count:
        raise SeedError("系统已初始化：已存在超级管理员，脚本已退出。")


async def seed_initial_users() -> None:
    """注册完整模型并向尚未初始化的当前 Schema 写入种子用户。"""
    from yuxi.infrastructure.postgres.manager import pg_manager
    from yuxi.infrastructure.postgres.models import load_models
    from yuxi.modules.identity.models import Department, User
    from yuxi.modules.identity.security import AuthUtils
    from yuxi.shared.datetime import utc_now

    try:
        load_models()
        pg_manager.initialize()
        # Schema 由 Compose 中的 app-init 独占创建，这里只校验版本后写入种子数据。
        from yuxi.infrastructure.postgres.schema import require_current_schema

        await require_current_schema(pg_manager)

        async with pg_manager.get_async_session_context() as session:
            await ensure_uninitialized(session)

            departments: dict[str, Department] = {}
            for department_seed in DEPARTMENTS:
                department = Department(
                    name=department_seed["name"],
                    description=department_seed["description"],
                )
                session.add(department)
                departments[department_seed["prefix"]] = department

            await session.flush()

            users = [
                User(
                    username=SUPERADMIN_NAME,
                    uid=SUPERADMIN_UID,
                    phone_number=SUPERADMIN_PHONE_NUMBER,
                    password_hash=AuthUtils.hash_password(SUPERADMIN_PASSWORD),
                    role="superadmin",
                    department_id=departments["dev"].id,
                    last_login=utc_now(),
                )
            ]

            for department_seed in DEPARTMENTS:
                department = departments[department_seed["prefix"]]
                for index in range(1, 3):
                    users.append(
                        User(
                            username=f"{department_seed['name']}管理员{index}",
                            uid=f"{department_seed['prefix']}_admin_{index}",
                            password_hash=AuthUtils.hash_password(DEFAULT_USER_PASSWORD),
                            role="admin",
                            department_id=department.id,
                        )
                    )
                for index in range(1, department_seed["normal_count"] + 1):
                    users.append(
                        User(
                            username=f"{department_seed['name']}用户{index}",
                            uid=f"{department_seed['prefix']}_user_{index:02d}",
                            password_hash=AuthUtils.hash_password(DEFAULT_USER_PASSWORD),
                            role="user",
                            department_id=department.id,
                        )
                    )

            session.add_all(users)
    finally:
        await pg_manager.close()


def main() -> int:
    load_project_env()
    try:
        asyncio.run(seed_initial_users())
    except SeedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"初始化种子用户失败：{exc}", file=sys.stderr)
        return 1

    print(f"初始化完成：已创建超级管理员 {SUPERADMIN_NAME}（{SUPERADMIN_UID}）、3 个部门、6 个部门管理员和 14 个普通用户。")
    print("超级管理员密码：zwj12138")
    print("部门管理员和普通用户默认密码：yuxi123456")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
