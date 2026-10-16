"""
部门管理路由
提供部门的增删改查接口，仅超级管理员可访问
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from yuxi.api.dependencies.auth import get_admin_user, get_db, get_superadmin_user
from yuxi.modules.identity.models import User
from yuxi.modules.identity.repositories.departments import DepartmentRepository
from yuxi.modules.identity.services import administration
from yuxi.modules.identity.services.administration import IdentityConflictError, create_department_with_admin

# 创建路由器
department = APIRouter(prefix="/departments", tags=["department"])


# =============================================================================
# === 请求和响应模型 ===
# =============================================================================


class DepartmentCreate(BaseModel):
    """创建部门请求"""

    name: str
    description: str | None = None
    # 必需的管理员信息
    admin_uid: str
    admin_password: str = Field(min_length=8)
    admin_phone: str | None = None


class DepartmentUpdate(BaseModel):
    """更新部门请求"""

    name: str | None = None
    description: str | None = None


class DepartmentResponse(BaseModel):
    """部门响应"""

    id: int
    name: str
    description: str | None = None
    created_at: str
    user_count: int = 0


# =============================================================================
# === 部门管理路由 ===
# =============================================================================


@department.get("", response_model=list[DepartmentResponse])
async def get_departments(current_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    """获取所有部门列表（管理员可访问）"""
    dept_repo = DepartmentRepository(db)
    return await dept_repo.list_with_user_count()


@department.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定部门详情"""
    department = await DepartmentRepository(db).get_with_user_count(department_id)
    if department is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部门不存在")
    return department


@department.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    department_data: DepartmentCreate,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    """适配部门与首位管理员的原子创建。"""
    try:
        created = await create_department_with_admin(db, **department_data.model_dump())
    except IdentityConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {**created.department.to_dict(), "user_count": 1}


@department.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    department_data: DepartmentUpdate,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await administration.update_department(db, department_id=department_id, **department_data.model_dump())


@department.delete("/{department_id}", status_code=status.HTTP_200_OK)
async def delete_department(
    department_id: int,
    current_user: User = Depends(get_superadmin_user),
    db: AsyncSession = Depends(get_db),
):
    return await administration.delete_department(db, department_id=department_id)
