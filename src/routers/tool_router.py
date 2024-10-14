import os
from fastapi import APIRouter, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from src.utils import setup_logger

tool = APIRouter(prefix="/tool")

logger = setup_logger("server-tools")

class Tool(BaseModel):
    name: str
    title: str
    description: str
    url: str
    method: str

@tool.get("/", response_model=List[Tool])
async def route_index():
    tools = [
        Tool(
            name="text-chunking",
            title="文本分块",
            description="将文本分块以更好地理解。可以输入文本或者上传文件。",
            url="/tools/text-chunking",
            method="POST",
        ),
        Tool(
            name="pdf2txt",
            title="PDF转文本",
            description="将PDF文件转换为文本文件。",
            url="/tools/pdf2txt",
            method="POST",
        )
    ]

    return tools

@tool.post("/text-chunking")
async def text_chunking(text: str = Body(...), params: Dict[str, Any] = Body(...)):
    from src.core.indexing import chunk
    nodes = chunk(text, params=params)
    return {"nodes": [node.to_dict() for node in nodes]}

@tool.post("/pdf2txt")
async def handle_pdf2txt(file: str = Body(...)):
    from src.plugins import pdf2txt
    text = pdf2txt(file, return_text=True)
    return {"text": text}
