from fastapi import Request, Body, Depends
from fastapi import APIRouter
from fastapi import Request, Body

base = APIRouter()

from src import config, retriever, knowledge_base, graph_base
from src.utils import logger
from server.utils.auth_middleware import get_admin_user, get_superadmin_user
from server.models.user_model import User


@base.get("/")
async def route_index():
    return {"message": "You Got It!"}

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

    with open(LOG_FILE, 'r') as f:
        last_lines = deque(f, maxlen=1000)

    log = ''.join(last_lines)
    return {"log": log, "message": "success", "log_file": LOG_FILE}


