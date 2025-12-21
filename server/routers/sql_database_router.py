# =================================
# 数据库连接和表选择接口
# =================================

import traceback

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.responses import FileResponse as StarletteFileResponse
from sympy import EX

from src.storage.db.models import User
from src import sql_database
from src.utils import logger

sql_db = APIRouter(prefix="/db", tags=["database"])


@sql_db.get("/databases")
async def get_databases(
    # current_user: User = Depends(get_admin_user)
    ):
    """获取所有数据库"""
    try:
        database = sql_database.get_databases()
        return database
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}


@sql_db.post("/database")
async def create_database(
    database_name: str = Body(...),
    description: str = Body(...),
    db_type: str = Body("mysql"),
    connection_info: dict = Body({}),
    # current_user: User = Depends(get_admin_user),
):
    """创建数据库"""
    logger.debug(
        f"Create database {database_name} with kb_type {db_type}"
    )
    try:
        sql_database.test_connection(connection_info)
        database_info = await sql_database.create_database(database_name, description, db_type, connection_info=connection_info)
        # 初始化数据库表信息
        init_tables_info = await sql_database.initialize_tables(database_info["db_id"])
        database_info["tables"] = init_tables_info
        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager

        await agent_manager.reload_all()

        return database_info
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"创建数据库失败 {e}", "status": "failed"}


@sql_db.get("/database/{db_id}")
async def get_database_info(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
    ):
    """获取数据库详细信息"""
    database = sql_database.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@sql_db.delete("/database/{db_id}")
async def delete_database(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
    ):
    """删除数据库"""
    logger.debug(f"Delete database {db_id}")
    try:
        await sql_database.delete_database(db_id)

        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager

        await agent_manager.reload_all()

        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除数据库失败: {e}")

@sql_db.get("/databases/{db_id}/tables")
async def get_tables(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
    ):
    """获取数据库表信息"""
    logger.debug(f"GET tables info in {db_id}")

    try:
        info = await sql_database.get_tables(db_id)
        return info
    except Exception as e:
        logger.error(f"Failed to get table info, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to get table info", "status": "failed"}

@sql_db.get("/databases/{db_id}/tables/selected")
async def get_tables(
    db_id: str, 
    # current_user: User = Depends(get_admin_user)
    ):
    logger.debug(f"GET tables info in {db_id}")

    try:
        info = await sql_database.get_selected_tables(db_id)
        return info
    except Exception as e:
        logger.error(f"Failed to get selected table info, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to get selected table info", "status": "failed"}

@sql_db.post("/databases/{db_id}/tables/choose")
async def choose_tables(
    db_id: str, 
    table_ids: list[str] = Body(...), 
    # current_user: User = Depends(get_admin_user)
):
    logger.debug(f"Choose tables for db_id {db_id}: {table_ids}")
    try:
        if not table_ids:
            raise Exception("Table IDs cannot be empty")
        # 选择需要使用的表
        table_info = await sql_database.select_tables(db_id, table_ids)
        from src.agents import agent_manager
        await agent_manager.reload_all()
        return table_info
    except Exception as e:
        logger.error(f"Failed to choose tables, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to choose tables", "status": "failed"}

@sql_db.delete("/databases/{db_id}/tables/{table_id}")
async def unchoose_tables(
    db_id: str, 
    table_id: str, 
    # current_user: User = Depends(get_admin_user)
):
    """取消选择数据库表"""
    logger.debug(f"Unchoose tables for db_id {db_id}: {table_id}")
    try:
        if not table_id:
            raise Exception("Table IDs cannot be empty")
        # 选择需要使用的表
        table_info = await sql_database.unselect_table(db_id, table_id)
        from src.agents import agent_manager
        await agent_manager.reload_all()
        return table_info
    except Exception as e:
        logger.error(f"Failed to unchoose tables, {e}, {db_id=}, {traceback.format_exc()}")
        return {"message": "Failed to unchoose tables", "status": "failed"}
