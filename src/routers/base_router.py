from fastapi import APIRouter

base = APIRouter()

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi import Request
from src.core import HistoryManager
from src.utils.logging_config import setup_logger
from src.core.startup import startup

logger = setup_logger("server-base")

@base.get("/")
async def route_index():
    return {"message": "You Got It!"}

@base.get("/config")
def get_config():
    return startup.config

@base.post("/config")
async def update_config(request: Request):
    request_data = await request.json()
    startup.config.update(request_data)
    startup.config.save()
    return startup.config

@base.post("/restart")
async def restart():
    startup.restart()
    return {"message": "Restarted!"}

@base.get("/log")
def get_log():
    from src.utils.logging_config import LOG_FILE
    from collections import deque

    with open(LOG_FILE, 'r') as f:
        last_lines = deque(f, maxlen=1000)

    log = ''.join(last_lines)
    return {"log": log}


