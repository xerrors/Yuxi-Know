"""
思维导图路由模块

提供思维导图相关的API接口，包括：
- 获取知识库文件列表
- AI生成思维导图
- 保存和加载思维导图配置
"""

import json
import traceback
import textwrap

from fastapi import APIRouter, Body, Depends, HTTPException

from yuxi.storage.postgres.models_business import User
from server.utils.auth_middleware import get_admin_user
from yuxi import knowledge_base
from yuxi.models import select_model
from yuxi.utils import logger

mindmap = APIRouter(prefix="/mindmap", tags=["mindmap"])


# =============================================================================
# === 获取知识库文件列表 ===
# =============================================================================
MINDMAP_SYSTEM_PROMPT = """你是一个专业的知识整理助手。

你的任务是分析用户提供的文件列表，生成一个层次分明的思维导图结构。

**核心规则：每个文件名只能出现一次！不允许重复！**

要求：
1. 思维导图要有清晰的层级结构（2-4层）
2. 根节点是知识库名称
3. 第一层是主要分类（如：技术文档、规章制度、数据资源等）
4. 第二层是子分类
5. **叶子节点必须是具体的文件名称**
6. **每个文件名在整个思维导图中只能出现一次，不得重复！**
7. 如果一个文件可能属于多个分类，只选择最合适的一个分类放置
8. 使用合适的emoji图标增强可读性
9. 返回JSON格式，遵循以下结构：

```json
{
  "content": "知识库名称",
  "children": [
    {
      "content": "🎯 主分类1",
      "children": [
        {
          "content": "子分类1.1",
          "children": [
            {"content": "文件名1.txt", "children": []},
            {"content": "文件名2.pdf", "children": []}
          ]
        }
      ]
    },
    {
      "content": "💻 主分类2",
      "children": [
        {"content": "文件名3.docx", "children": []},
        {"content": "文件名4.md", "children": []}
      ]
    }
  ]
}
```

**重要约束：**
- 每个文件名在整个JSON中只能出现一次
- 不要按多个维度分类导致文件重复
- 选择最主要、最合适的分类维度
- 每个叶子节点的children必须是空数组[]
- 分类名称要简洁明了
- 使用emoji增强视觉效果
"""


@mindmap.get("/databases/{db_id}/files")
async def get_database_files(db_id: str, current_user: User = Depends(get_admin_user)):
    """
    获取指定知识库的所有文件列表

    Args:
        db_id: 知识库ID

    Returns:
        文件列表信息
    """
    try:
        # 获取知识库详细信息
        db_info = await knowledge_base.get_database_info(db_id)

        if not db_info:
            raise HTTPException(status_code=404, detail=f"知识库 {db_id} 不存在")

        # 提取文件信息
        files = db_info.get("files", {})

        # 转换为列表格式
        file_list = []
        for file_id, file_info in files.items():
            file_list.append(
                {
                    "file_id": file_id,
                    "filename": file_info.get("filename", ""),
                    "type": file_info.get("type", ""),
                    "status": file_info.get("status", ""),
                    "created_at": file_info.get("created_at", ""),
                }
            )

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


# =============================================================================
# === AI生成思维导图 ===
# =============================================================================


@mindmap.post("/generate")
async def generate_mindmap(
    db_id: str = Body(..., description="知识库ID"),
    file_ids: list[str] = Body(default=[], description="选择的文件ID列表"),
    user_prompt: str = Body(default="", description="用户自定义提示词"),
    current_user: User = Depends(get_admin_user),
):
    """
    使用AI分析知识库文件，生成思维导图结构

    Args:
        db_id: 知识库ID
        file_ids: 选择的文件ID列表（为空则使用所有文件）
        user_prompt: 用户自定义提示词

    Returns:
        Markmap格式的思维导图数据
    """
    try:
        # 获取知识库信息
        db_info = await knowledge_base.get_database_info(db_id)

        if not db_info:
            raise HTTPException(status_code=404, detail=f"知识库 {db_id} 不存在")

        db_name = db_info.get("name", "知识库")
        all_files = db_info.get("files", {})

        # 如果没有指定文件，则使用所有文件
        if not file_ids:
            file_ids = list(all_files.keys())

        if not file_ids:
            raise HTTPException(status_code=400, detail="知识库中没有文件")

        # 限制文件数量不超过100个，如果超过则选择前100个
        if len(file_ids) > 20:
            original_count = len(file_ids)
            file_ids = file_ids[:20]
            logger.info(f"文件数量超过限制，已从{original_count}个文件中选择前20个文件生成思维导图")

        # 收集文件信息
        files_info = []
        for file_id in file_ids:
            if file_id in all_files:
                file_info = all_files[file_id]
                files_info.append(
                    {
                        "filename": file_info.get("filename", ""),
                        "type": file_info.get("type", ""),
                    }
                )

        if not files_info:
            raise HTTPException(status_code=400, detail="选择的文件不存在")

        # 构建AI提示词
        system_prompt = MINDMAP_SYSTEM_PROMPT

        # 构建用户消息
        files_text = "\n".join([f"- {f['filename']} ({f['type']})" for f in files_info])

        user_message = textwrap.dedent(f"""请为知识库"{db_name}"生成思维导图结构。

            文件列表（共{len(files_info)}个文件）：
            {files_text}

            {f"用户补充说明：{user_prompt}" if user_prompt else ""}

            **重要提醒：**
            1. 这个知识库共有{len(files_info)}个文件
            2. 每个文件名只能在思维导图中出现一次
            3. 不要让同一个文件出现在多个分类下
            4. 为每个文件选择最合适的唯一分类

            请生成合理的思维导图结构。""")

        # 调用AI生成
        logger.info(f"开始生成思维导图，知识库: {db_name}, 文件数量: {len(files_info)}")

        # 选择模型并调用
        model = select_model()
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
        response = await model.call(messages, stream=False)

        # 解析AI返回的JSON
        try:
            # 提取JSON内容
            content = response.content if hasattr(response, "content") else str(response)

            # 尝试从markdown代码块中提取JSON
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()

            mindmap_data = json.loads(content)

            # 验证结构
            if not isinstance(mindmap_data, dict) or "content" not in mindmap_data:
                raise ValueError("思维导图结构不正确")

            logger.info("思维导图生成成功")

            # 保存思维导图到知识库元数据
            try:
                from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository

                await KnowledgeBaseRepository().update(db_id, {"mindmap": mindmap_data})
                logger.info(f"思维导图已保存到知识库: {db_id}")
            except Exception as save_error:
                logger.error(f"保存思维导图失败: {save_error}")
                # 不影响返回结果，只记录错误

            return {
                "message": "success",
                "mindmap": mindmap_data,
                "db_id": db_id,
                "db_name": db_name,
                "file_count": len(files_info),
                "original_file_count": original_count if "original_count" in locals() else len(files_info),
                "truncated": len(files_info) < (original_count if "original_count" in locals() else len(files_info)),
            }

        except json.JSONDecodeError as e:
            logger.error(f"AI返回的JSON解析失败: {e}, 原始内容: {content}")
            raise HTTPException(status_code=500, detail=f"AI返回格式错误: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成思维导图失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"生成思维导图失败: {str(e)}")


# =============================================================================
# === 获取所有知识库概览（用于选择） ===
# =============================================================================


@mindmap.get("/databases")
async def get_databases_overview(current_user: User = Depends(get_admin_user)):
    """
    获取所有知识库的概览信息，用于思维导图界面选择（根据用户权限过滤）

    Returns:
        知识库列表
    """
    try:
        databases = await knowledge_base.get_databases_by_user_id(current_user.user_id)

        # databases["databases"] 是一个列表，每个元素已经包含了基本信息
        db_list_raw = databases.get("databases", [])

        db_list = []
        for db_info in db_list_raw:
            db_id = db_info.get("db_id")
            if not db_id:
                continue

            # 获取详细信息以获取文件数量
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

        return {
            "message": "success",
            "databases": db_list,
            "total": len(db_list),
        }

    except Exception as e:
        logger.error(f"获取知识库列表失败: {e}, {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败: {str(e)}")


# =============================================================================
# === 知识库关联的思维导图管理 ===
# =============================================================================


@mindmap.get("/database/{db_id}")
async def get_database_mindmap(db_id: str, current_user: User = Depends(get_admin_user)):
    """
    获取知识库关联的思维导图

    Args:
        db_id: 知识库ID

    Returns:
        思维导图数据
    """
    try:
        from yuxi.repositories.knowledge_base_repository import KnowledgeBaseRepository

        kb_repo = KnowledgeBaseRepository()
        kb = await kb_repo.get_by_id(db_id)

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
