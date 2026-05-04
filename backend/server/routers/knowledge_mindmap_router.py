"""
知识库思维导图路由模块。

提供思维导图相关的 API 接口，包括：
- 获取知识库文件列表
- AI 生成思维导图
- 保存和加载思维导图配置
"""

import traceback

from fastapi import APIRouter, Body, Depends, HTTPException

from server.utils.auth_middleware import get_admin_user
from yuxi import config, knowledge_base
from yuxi.knowledge.utils.mindmap_utils import (
    MINDMAP_SYSTEM_PROMPT,
    build_database_file_list,
    build_mindmap_user_message,
    collect_mindmap_files,
    parse_mindmap_content,
)
from yuxi.models import select_model
from yuxi.storage.postgres.models_business import User
from yuxi.utils import logger

mindmap = APIRouter(prefix="/mindmap", tags=["mindmap"])


@mindmap.get("/databases/{db_id}/files")
async def get_database_files(db_id: str, current_user: User = Depends(get_admin_user)):
    """获取指定知识库的所有文件列表。"""
    try:
        db_info = await knowledge_base.get_database_info(db_id)
        if not db_info:
            raise HTTPException(status_code=404, detail=f"知识库 {db_id} 不存在")

        file_list = build_database_file_list(db_info.get("files", {}))
        return {
            "message": "success",
            "db_id": db_id,
            "db_name": db_info.get("name", ""),
            "files": file_list,
            "total": len(file_list),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库文件列表失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取文件列表失败: {str(e)}")


@mindmap.post("/generate")
async def generate_mindmap(
    db_id: str = Body(..., description="知识库ID"),
    file_ids: list[str] = Body(default=[], description="选择的文件ID列表"),
    user_prompt: str = Body(default="", description="用户自定义提示词"),
    current_user: User = Depends(get_admin_user),
):
    """使用 AI 分析知识库文件，生成思维导图结构。"""
    try:
        db_info = await knowledge_base.get_database_info(db_id)
        if not db_info:
            raise HTTPException(status_code=404, detail=f"知识库 {db_id} 不存在")

        db_name = db_info.get("name", "知识库")
        all_files = db_info.get("files", {})

        if not file_ids:
            file_ids = list(all_files.keys())
        if not file_ids:
            raise HTTPException(status_code=400, detail="知识库中没有文件")

        original_count = len(file_ids)
        if len(file_ids) > 20:
            file_ids = file_ids[:20]
            logger.info(f"文件数量超过限制，已从{original_count}个文件中选择前20个文件生成思维导图")

        files_info = collect_mindmap_files(all_files, file_ids)
        if not files_info:
            raise HTTPException(status_code=400, detail="选择的文件不存在")

        logger.info(f"开始生成思维导图，知识库: {db_name}, 文件数量: {len(files_info)}")

        model = select_model(model_spec=config.default_model)
        messages = [
            {"role": "system", "content": MINDMAP_SYSTEM_PROMPT},
            {"role": "user", "content": build_mindmap_user_message(db_name, files_info, user_prompt)},
        ]
        response = await model.call(messages, stream=False)
        content = response.content if hasattr(response, "content") else str(response)

        try:
            mindmap_data = parse_mindmap_content(content)
        except ValueError as e:
            logger.error(f"AI返回的JSON解析失败: {e}, 原始内容: {content}")
            raise HTTPException(status_code=500, detail=f"AI返回格式错误: {str(e)}")

        logger.info("思维导图生成成功")

        try:
            from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository

            await KnowledgeBaseRepository().update(db_id, {"mindmap": mindmap_data})
            logger.info(f"思维导图已保存到知识库: {db_id}")
        except Exception as save_error:
            logger.error(f"保存思维导图失败: {save_error}")

        return {
            "message": "success",
            "mindmap": mindmap_data,
            "db_id": db_id,
            "db_name": db_name,
            "file_count": len(files_info),
            "original_file_count": original_count,
            "truncated": len(files_info) < original_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成思维导图失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"生成思维导图失败: {str(e)}")


@mindmap.get("/databases")
async def get_databases_overview(current_user: User = Depends(get_admin_user)):
    """获取所有知识库的概览信息，用于思维导图界面选择。"""
    try:
        databases = await knowledge_base.get_databases_by_user_id(current_user.user_id)
        db_list = []
        for db_info in databases.get("databases", []):
            db_id = db_info.get("db_id")
            if not db_id:
                continue

            detail_info = await knowledge_base.get_database_info(db_id)
            file_count = len(detail_info.get("files", {})) if detail_info else 0
            db_list.append(
                {
                    "db_id": db_id,
                    "name": db_info.get("name", ""),
                    "description": db_info.get("description", ""),
                    "kb_type": db_info.get("kb_type", ""),
                    "file_count": file_count,
                }
            )

        return {"message": "success", "databases": db_list, "total": len(db_list)}

    except Exception as e:
        logger.error(f"获取知识库列表失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


@mindmap.get("/database/{db_id}")
async def get_database_mindmap(db_id: str, current_user: User = Depends(get_admin_user)):
    """获取知识库关联的思维导图。"""
    try:
        from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository

        kb = await KnowledgeBaseRepository().get_by_id(db_id)
        if kb is None:
            raise HTTPException(status_code=404, detail=f"知识库 {db_id} 不存在")

        return {
            "message": "success",
            "mindmap": kb.mindmap,
            "db_id": db_id,
            "db_name": kb.name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库思维导图失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取思维导图失败: {str(e)}")
