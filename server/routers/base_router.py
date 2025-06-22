import os
import yaml
from pathlib import Path
from fastapi import Request, Body, Depends, HTTPException
from fastapi import APIRouter

from src import config, retriever, knowledge_base, graph_base
from server.utils.auth_middleware import get_admin_user, get_superadmin_user
from server.models.user_model import User
from src.utils.logging_config import logger


base = APIRouter()

def load_info_config():
    """加载信息配置文件"""
    try:
        # 配置文件路径
        config_path = Path("src/static/info.local.yaml")

        # 检查文件是否存在
        if not config_path.exists():
            logger.warning(f"配置文件 {config_path} 不存在，使用默认配置")
            return get_default_info_config()

        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)

        # logger.info(f"成功加载信息配置文件: {config_path}")
        return config

    except Exception as e:
        logger.error(f"加载信息配置文件失败: {e}")
        return get_default_info_config()

def get_default_info_config():
    """获取默认信息配置"""
    return {
        "organization": {
            "name": "江南大学",
            "short_name": "语析",
            "logo": "/favicon.svg",
            "avatar": "/avatar.jpg"
        },
        "branding": {
            "title": "Yuxi-Know",
            "subtitle": "大模型驱动的知识库管理工具",
            "description": "结合知识库与知识图谱，提供更准确、更全面的回答"
        },
        "features": [
            "📚 灵活知识库",
            "🕸️ 知识图谱集成",
            "🤖 多模型支持"
        ],
        "footer": {
            "copyright": "© 江南大学 2025 [WIP] v0.12.138"
        }
    }

@base.get("/")
async def route_index():
    return {"message": "You Got It!"}

@base.get("/health")
async def health_check():
    """简单的健康检查接口"""
    return {"status": "ok", "message": "服务正常运行"}

@base.get("/config")
def get_config(current_user: User = Depends(get_admin_user)):
    return config.dump_config()

@base.post("/config")
async def update_config(
    key = Body(...),
    value = Body(...),
    current_user: User = Depends(get_admin_user)
) -> dict:
    config[key] = value
    config.save()
    return config.dump_config()

@base.post("/config/update")
async def update_config_item(
    items: dict = Body(...),
    current_user: User = Depends(get_admin_user)
) -> dict:
    config.update(items)
    config.save()
    return config.dump_config()

@base.post("/restart")
async def restart(current_user: User = Depends(get_superadmin_user)):
    knowledge_base.restart()
    graph_base.start()
    retriever.restart()
    return {"message": "Restarted!"}

@base.get("/log")
def get_log(current_user: User = Depends(get_admin_user)):
    from src.utils.logging_config import LOG_FILE
    from collections import deque

    with open(LOG_FILE) as f:
        last_lines = deque(f, maxlen=1000)

    log = ''.join(last_lines)
    return {"log": log, "message": "success", "log_file": LOG_FILE}

@base.get("/info")
async def get_info_config():
    """获取系统信息配置（公开接口，无需认证）"""
    try:
        config = load_info_config()
        return {
            "success": True,
            "data": config
        }
    except Exception as e:
        logger.error(f"获取信息配置失败: {e}")
        raise HTTPException(status_code=500, detail="获取信息配置失败")

@base.get("/info/reload")
async def reload_info_config():
    """重新加载信息配置（管理员接口）"""
    # 注：这里暂时不添加权限验证，后续可以根据需要添加
    try:
        config = load_info_config()
        return {
            "success": True,
            "message": "配置重新加载成功",
            "data": config
        }
    except Exception as e:
        logger.error(f"重新加载信息配置失败: {e}")
        raise HTTPException(status_code=500, detail="重新加载信息配置失败")


