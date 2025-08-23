import os
import asyncio
import traceback
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Body, Form, Query
from fastapi.responses import FileResponse

from src import executor, config, knowledge_base
from src.utils import logger, hashstr
from src.knowledge.indexing import process_file_to_markdown
from server.utils.auth_middleware import get_admin_user
from server.models.user_model import User

knowledge = APIRouter(prefix="/knowledge", tags=["knowledge"])

# =============================================================================
# === 数据库管理分组 ===
# =============================================================================

@knowledge.get("/databases")
async def get_databases(current_user: User = Depends(get_admin_user)):
    """获取所有知识库"""
    try:
        database = knowledge_base.get_databases()
        return database
    except Exception as e:
        logger.error(f"获取数据库列表失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取数据库列表失败 {e}", "databases": []}

@knowledge.post("/databases")
async def create_database(
    database_name: str = Body(...),
    description: str = Body(...),
    embed_model_name: str = Body(...),
    kb_type: str = Body("lightrag"),
    additional_params: dict = Body({}),
    llm_info: dict = Body(None),
    current_user: User = Depends(get_admin_user)
):
    """创建知识库"""
    logger.debug(f"Create database {database_name} with kb_type {kb_type}, additional_params {additional_params}, llm_info {llm_info}")
    try:
        embed_info = config.embed_model_names[embed_model_name]
        database_info = await knowledge_base.create_database(
            database_name,
            description,
            kb_type=kb_type,
            embed_info=embed_info,
            llm_info=llm_info,
            **additional_params
        )

        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager
        await agent_manager.reload_all()

        return database_info
    except Exception as e:
        logger.error(f"创建数据库失败 {e}, {traceback.format_exc()}")
        return {"message": f"创建数据库失败 {e}", "status": "failed"}

@knowledge.get("/databases/{db_id}")
async def get_database_info(db_id: str, current_user: User = Depends(get_admin_user)):
    """获取知识库详细信息"""
    database = knowledge_base.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@knowledge.put("/databases/{db_id}")
async def update_database_info(
    db_id: str,
    name: str = Body(...),
    description: str = Body(...),
    current_user: User = Depends(get_admin_user)
):
    """更新知识库信息"""
    logger.debug(f"Update database {db_id} info: {name}, {description}")
    try:
        database = await knowledge_base.update_database(db_id, name, description)
        return {"message": "更新成功", "database": database}
    except Exception as e:
        logger.error(f"更新数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"更新数据库失败: {e}")

@knowledge.delete("/databases/{db_id}")
async def delete_database(db_id: str, current_user: User = Depends(get_admin_user)):
    """删除知识库"""
    logger.debug(f"Delete database {db_id}")
    try:
        await knowledge_base.delete_database(db_id)

        # 需要重新加载所有智能体，因为工具刷新了
        from src.agents import agent_manager
        await agent_manager.reload_all()

        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除数据库失败: {e}")

@knowledge.get("/databases/{db_id}/export")
async def export_database(
    db_id: str,
    format: str = Query("csv", enum=["csv", "xlsx", "md", "txt"]),
    include_vectors: bool = Query(False, description="是否在导出中包含向量数据"),
    current_user: User = Depends(get_admin_user)
):
    """导出知识库数据"""
    logger.debug(f"Exporting database {db_id} with format {format}")
    try:
        file_path = await knowledge_base.export_data(
            db_id, format=format, include_vectors=include_vectors
        )

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Exported file not found.")

        media_types = {
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "md": "text/markdown",
            "txt": "text/plain"
        }
        media_type = media_types.get(format, "application/octet-stream")

        return FileResponse(
            path=file_path,
            filename=os.path.basename(file_path),
            media_type=media_type
        )
    except NotImplementedError as e:
        logger.warning(f"A disabled feature was accessed: {e}")
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"导出数据库失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"导出数据库失败: {e}")

# =============================================================================
# === 文档管理分组 ===
# =============================================================================

@knowledge.post("/databases/{db_id}/documents")
async def add_documents(
    db_id: str,
    items: list[str] = Body(...),
    params: dict = Body(...),
    current_user: User = Depends(get_admin_user)
):
    """添加文档到知识库"""
    logger.debug(f"Add documents for db_id {db_id}: {items} {params=}")

    content_type = params.get('content_type', 'file')

    try:
        processed_items = await knowledge_base.add_content(db_id, items, params=params)
        item_type = "URLs" if content_type == 'url' else "files"
        processed_failed_count = len([_p for _p in processed_items if _p['status'] == 'failed'])
        processed_info = f"Processed {len(processed_items)} {item_type}, {processed_failed_count} {item_type} failed"
        return {"message": processed_info, "items": processed_items, "status": "success"}
    except Exception as e:
        logger.error(f"Failed to process {content_type}s: {e}, {traceback.format_exc()}")
        return {"message": f"Failed to process {content_type}s: {e}", "status": "failed"}

@knowledge.get("/databases/{db_id}/documents/{doc_id}")
async def get_document_info(
    db_id: str,
    doc_id: str,
    current_user: User = Depends(get_admin_user)
):
    """获取文档详细信息"""
    logger.debug(f"GET document {doc_id} info in {db_id}")

    try:
        info = await knowledge_base.get_file_info(db_id, doc_id)
        return info
    except Exception as e:
        logger.error(f"Failed to get file info, {e}, {db_id=}, {doc_id=}, {traceback.format_exc()}")
        return {"message": "Failed to get file info", "status": "failed"}

@knowledge.delete("/databases/{db_id}/documents/{doc_id}")
async def delete_document(
    db_id: str,
    doc_id: str,
    current_user: User = Depends(get_admin_user)
):
    """删除文档"""
    logger.debug(f"DELETE document {doc_id} info in {db_id}")
    try:
        await knowledge_base.delete_file(db_id, doc_id)
        return {"message": "删除成功"}
    except Exception as e:
        logger.error(f"删除文档失败 {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=400, detail=f"删除文档失败: {e}")

# =============================================================================
# === 查询分组 ===
# =============================================================================

@knowledge.post("/databases/{db_id}/query")
async def query_knowledge_base(
    db_id: str,
    query: str = Body(...),
    meta: dict = Body(...),
    current_user: User = Depends(get_admin_user)
):
    """查询知识库"""
    logger.debug(f"Query knowledge base {db_id}: {query}")
    try:
        result = await knowledge_base.aquery(query, db_id=db_id, **meta)
        return {"result": result, "status": "success"}
    except Exception as e:
        logger.error(f"知识库查询失败 {e}, {traceback.format_exc()}")
        return {"message": f"知识库查询失败: {e}", "status": "failed"}

@knowledge.post("/databases/{db_id}/query-test")
async def query_test(
    db_id: str,
    query: str = Body(...),
    meta: dict = Body(...),
    current_user: User = Depends(get_admin_user)
):
    """测试查询知识库"""
    logger.debug(f"Query test in {db_id}: {query}")
    try:
        result = await knowledge_base.aquery(query, db_id=db_id, **meta)
        return result
    except Exception as e:
        logger.error(f"测试查询失败 {e}, {traceback.format_exc()}")
        return {"message": f"测试查询失败: {e}", "status": "failed"}

@knowledge.get("/databases/{db_id}/query-params")
async def get_knowledge_base_query_params(
    db_id: str,
    current_user: User = Depends(get_admin_user)
):
    """获取知识库类型特定的查询参数"""
    try:
        # 获取数据库信息
        db_info = knowledge_base.get_database_info(db_id)
        if not db_info:
            raise HTTPException(status_code=404, detail="Database not found")

        kb_type = db_info.get("kb_type", "lightrag")

        # 根据知识库类型返回不同的查询参数
        if kb_type == "lightrag":
            params = {
                "type": "lightrag",
                "options": [
                    {
                        "key": "mode",
                        "label": "检索模式",
                        "type": "select",
                        "default": "mix",
                        "options": [
                            {"value": "local", "label": "Local", "description": "上下文相关信息"},
                            {"value": "global", "label": "Global", "description": "全局知识"},
                            {"value": "hybrid", "label": "Hybrid", "description": "本地和全局混合"},
                            {"value": "naive", "label": "Naive", "description": "基本搜索"},
                            {"value": "mix", "label": "Mix", "description": "知识图谱和向量检索混合"},
                        ]
                    },
                    {
                        "key": "only_need_context",
                        "label": "只使用上下文",
                        "type": "boolean",
                        "default": True,
                        "description": "只返回上下文，不生成回答"
                    },
                    {
                        "key": "only_need_prompt",
                        "label": "只使用提示",
                        "type": "boolean",
                        "default": False,
                        "description": "只返回提示，不进行检索"
                    },
                    {
                        "key": "top_k",
                        "label": "TopK",
                        "type": "number",
                        "default": 10,
                        "min": 1,
                        "max": 100,
                        "description": "返回的最大结果数量"
                    }
                ]
            }
        elif kb_type == "chroma":
            params = {
                "type": "chroma",
                "options": [
                    {
                        "key": "top_k",
                        "label": "TopK",
                        "type": "number",
                        "default": 10,
                        "min": 1,
                        "max": 100,
                        "description": "返回的最大结果数量"
                    },
                    {
                        "key": "similarity_threshold",
                        "label": "相似度阈值",
                        "type": "number",
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.1,
                        "description": "过滤相似度低于此值的结果"
                    },
                    {
                        "key": "include_distances",
                        "label": "显示相似度",
                        "type": "boolean",
                        "default": True,
                        "description": "在结果中显示相似度分数"
                    }
                ]
            }
        elif kb_type == "milvus":
            params = {
                "type": "milvus",
                "options": [
                    {
                        "key": "top_k",
                        "label": "TopK",
                        "type": "number",
                        "default": 10,
                        "min": 1,
                        "max": 100,
                        "description": "返回的最大结果数量"
                    },
                    {
                        "key": "similarity_threshold",
                        "label": "相似度阈值",
                        "type": "number",
                        "default": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "step": 0.1,
                        "description": "过滤相似度低于此值的结果"
                    },
                    {
                        "key": "include_distances",
                        "label": "显示相似度",
                        "type": "boolean",
                        "default": True,
                        "description": "在结果中显示相似度分数"
                    },
                    {
                        "key": "metric_type",
                        "label": "距离度量类型",
                        "type": "select",
                        "default": "COSINE",
                        "options": [
                            {"value": "COSINE", "label": "余弦相似度", "description": "适合文本语义相似度"},
                            {"value": "L2", "label": "欧几里得距离", "description": "适合数值型数据"},
                            {"value": "IP", "label": "内积", "description": "适合标准化向量"}
                        ],
                        "description": "向量相似度计算方法"
                    }
                ]
            }
        else:
            # 未知类型，返回基本参数
            params = {
                "type": "unknown",
                "options": [
                    {
                        "key": "top_k",
                        "label": "TopK",
                        "type": "number",
                        "default": 10,
                        "min": 1,
                        "max": 100,
                        "description": "返回的最大结果数量"
                    }
                ]
            }

        return {"params": params, "message": "success"}

    except Exception as e:
        logger.error(f"获取知识库查询参数失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取知识库查询参数失败 {e}", "params": {}}

# =============================================================================
# === 文件管理分组 ===
# =============================================================================

@knowledge.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    db_id: str | None = Query(None),
    current_user: User = Depends(get_admin_user)
):
    """上传文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")

    # 根据db_id获取上传路径，如果db_id为None则使用默认路径
    if db_id:
        upload_dir = knowledge_base.get_db_upload_path(db_id)
    else:
        upload_dir = os.path.join(config.save_dir, "database", "uploads")

    basename, ext = os.path.splitext(file.filename)
    filename = f"{basename}_{hashstr(basename, 4, with_salt=True)}{ext}".lower()
    file_path = os.path.join(upload_dir, filename)
    os.makedirs(upload_dir, exist_ok=True)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"message": "File successfully uploaded", "file_path": file_path, "db_id": db_id}

@knowledge.post("/files/markdown")
async def mark_it_down(
    file: UploadFile = File(...),
    current_user: User = Depends(get_admin_user)
):
    """调用 src.knowledge.indexing 下面的 process_file_to_markdown 解析为 markdown，参数是文件，需要管理员权限"""
    try:
        content = await file.read()
        markdown_content = await process_file_to_markdown(content)
        return {"markdown_content": markdown_content, "message": "success"}
    except Exception as e:
        logger.error(f"文件解析失败 {e}, {traceback.format_exc()}")
        return {"message": f"文件解析失败 {e}", "markdown_content": ""}

# =============================================================================
# === 知识库类型分组 ===
# =============================================================================

@knowledge.get("/types")
async def get_knowledge_base_types(current_user: User = Depends(get_admin_user)):
    """获取支持的知识库类型"""
    try:
        kb_types = knowledge_base.get_supported_kb_types()
        return {"kb_types": kb_types, "message": "success"}
    except Exception as e:
        logger.error(f"获取知识库类型失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取知识库类型失败 {e}", "kb_types": {}}

@knowledge.get("/stats")
async def get_knowledge_base_statistics(current_user: User = Depends(get_admin_user)):
    """获取知识库统计信息"""
    try:
        stats = knowledge_base.get_statistics()
        return {"stats": stats, "message": "success"}
    except Exception as e:
        logger.error(f"获取知识库统计失败 {e}, {traceback.format_exc()}")
        return {"message": f"获取知识库统计失败 {e}", "stats": {}}
