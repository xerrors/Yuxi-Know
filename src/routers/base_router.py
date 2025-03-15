from fastapi import APIRouter
from fastapi import Request, Body

base = APIRouter()

from src import config, dbm, retriever
from src.utils import logger


@base.get("/")
async def route_index():
    return {"message": "You Got It!"}

@base.get("/config")
def get_config():
    return config

@base.post("/config")
async def update_config(key = Body(...), value = Body(...)):
    config[key] = value
    config.save()
    return config

@base.post("/restart")
async def restart():
    dbm.restart()
    retriever.restart()
    return {"message": "Restarted!"}

@base.get("/log")
def get_log():
    from src.utils.logging_config import LOG_FILE
    from collections import deque

    with open(LOG_FILE, 'r') as f:
        last_lines = deque(f, maxlen=1000)

    log = ''.join(last_lines)
    return {"log": log, "message": "success", "log_file": LOG_FILE}


