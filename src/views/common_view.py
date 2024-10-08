import itertools
import json
from flask import Blueprint, jsonify, request, Response

from src.core import HistoryManager
from src.utils.logging_config import setup_logger
from src.core.startup import startup
from collections import deque

common = Blueprint('common', __name__)
logger = setup_logger("server-common")

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
    history_manager = HistoryManager(request_data['history'])

    new_query, refs = startup.retriever(query, history_manager.messages, meta)

    messages = history_manager.get_history_with_msg(new_query, max_rounds=meta.get('history_round'))
    history_manager.add_user(query)
    logger.debug(f"Web history: {history_manager.messages}")

    def generate_response():
        content = ""
        for delta in startup.model.predict(messages, stream=True):
            if not delta.content:
                continue

            if hasattr(delta, 'is_full') and delta.is_full:
                content = delta.content
            else:
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
    response = startup.model.predict(query)
    logger.debug({"query": query, "response": response.content})

    return jsonify({
        "response": response.content,
    })

@common.route('/config', methods=['get'])
def get_config():
    return jsonify(startup.config)

@common.route('/config', methods=['post'])
def update_config():
    request_data = json.loads(request.data)
    startup.config.update(request_data)
    startup.config.save()
    return jsonify(startup.config)

@common.route('/restart', methods=['POST'])
def restart():
    startup.restart()
    return jsonify({"message": "Restarted!"})


@common.route('/log', methods=['GET'])
def get_log():
    from src.utils.logging_config import LOG_FILE
    from collections import deque

    with open(LOG_FILE, 'r') as f:
        # 使用deque保存最后1000行
        last_lines = deque(f, maxlen=1000)

    log = ''.join(last_lines)

    return jsonify({"log": log})