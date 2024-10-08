import os
import json
import threading
from flask import Blueprint, jsonify, request, Response

from src.utils import setup_logger, hashstr
from src.core.startup import startup

tools = Blueprint('tools', __name__, url_prefix="/tools")

logger = setup_logger("server-tools")


@tools.route("/", methods=["GET"])
def route_index():
    tools = [
        {
            "name": "text_chunking",
            "title": "文本分块",
            "description": "将文本分块以更好地理解。可以输入文本或者上传文件。",
            "url": "/tools/text_chunking",
            "method": "POST",
        },
        {
            "name": "pdf2txt",
            "title": "PDF转文本",
            "description": "将PDF文件转换为文本文件。",
            "url": "/tools/pdf2txt",
            "method": "POST",
        }
    ]

    return jsonify(tools)


@tools.route("/text_chunking", methods=["POST"])
def text_chunking():
    from src.core.indexing import chunk
    text = request.json.get("text")
    nodes = chunk(text, params=request.json)
    return jsonify({"nodes": [node.to_dict() for node in nodes]})

@tools.route("/pdf2txt", methods=["POST"])
def handle_pdf2txt():
    from src.plugins import pdf2txt
    file = request.json.get("file")
    text = pdf2txt(file, return_text=True)
    return jsonify({"text": text})
