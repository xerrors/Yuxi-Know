import json
from flask import Blueprint, jsonify, request, Response

from core import HistoryManager
from utils.logging_config import setup_logger
from core.startup import config, model
from core.retriever import Retriever


common = Blueprint('common', __name__)
logger = setup_logger("server-common")
retriever = Retriever(config)

@common.route('/', methods=["GET"])
def route_index():
    return jsonify({"message": "You Got It!"})

@common.errorhandler(404)
def page_not_found(e):
    return jsonify({"message": "DEBUG: " + str(e)}), 404


@common.errorhandler(403)
def page_not_found(e):
    return jsonify({"message": str(e)}), 403
@common.route('/', methods=['GET'])
def chat_get():
    return "Chat Get!"

@common.route('/chat', methods=['POST'])
def chat():
    request_data = json.loads(request.data)
    query = request_data['query']
    meta = request_data.get('meta')
    logger.debug(f"Web query: {query}")
    history_manager = HistoryManager(request_data['history'])

    new_query, refs = retriever(query, history_manager.messages, meta)

    messages = history_manager.get_history_with_msg(new_query)
    history_manager.add_user(query)
    logger.debug(f"Web history: {history_manager}")

    def generate_response():
        content = ""
        for delta in model.predict(messages, stream=True):
            if delta.content:
                content += delta.content
                response_chunk = json.dumps({
                    "history": history_manager.update_ai(content),
                    "response": content,
                    "refs": refs  # TODO: 优化 refs，不需要每次都返回
                }, ensure_ascii=False).encode('utf8') + b'\n'
                yield response_chunk

    return Response(generate_response(), content_type='application/json', status=200)

@common.route('/call', methods=['POST'])
def call():
    request_data = json.loads(request.data)
    query = request_data['query']
    response = model.predict(query)
    logger.debug(f"Call query: {query} Response: {response.content}")

    return jsonify({
        "response": response.content,
    })

@common.route('/config', methods=['get'])
def get_config():
    return jsonify(config)