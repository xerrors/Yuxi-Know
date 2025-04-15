import os
from fastapi import APIRouter, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from src.agents import agent_manager

tool = APIRouter(prefix="/tool")


class Tool(BaseModel):
    name: str
    title: str
    description: str
    url: str
    method: Optional[str] = "POST"
    params: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

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
        ),
        Tool(
            name="agent",
            title="智能体（Dev）",
            description="智能体演练平台，现在还处于开发预览状态，欢迎提 Issue，但先不要用于正式场景。",
            url="/tools/agent",
        )
    ]

    for agent in agent_manager.agents.values():
        tools.append(
            Tool(
                name=agent.name,
                title=agent.name,
                description=agent.description,
                url=f"/agent/{agent.name}",
                method="POST",
                metadata=agent.config_schema.to_dict(),
            )
        )

    return tools

@tool.post("/text-chunking")
async def text_chunking(text: str = Body(...), params: Dict[str, Any] = Body(...)):
    from src.core.indexing import chunk
    nodes = chunk(text, params=params)
    return {"nodes": [node.to_dict() for node in nodes]}

@tool.post("/pdf2txt")
async def handle_pdf2txt(file: str = Body(...)):
    from src.plugins import ocr
    text = ocr.process_pdf(file)
    return {"text": text}

