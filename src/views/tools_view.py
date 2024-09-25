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
            "title": "Text Chunking",
            "description": "Chunking text into smaller pieces for better understanding.",
            "url": "/tools/text_chunking",
            "method": "POST",
            "params": [
                {
                    "name": "text",
                    "type": "string",
                    "description": "Text to be chunked."
                },
                {
                    "name": "chunk_size",
                    "type": "int",
                }
            ]
        }
    ]

    return jsonify(tools)


@tools.route("/text_chunking", methods=["POST"])
def text_chunking():
    from src.core.indexing import chunk_text
    text = request.json.get("text")
    nodes = chunk_text(text, params=request.json)
    return jsonify({"nodes": [node.to_dict() for node in nodes]})
