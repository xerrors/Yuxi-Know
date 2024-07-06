import os
import json
from flask import Flask, jsonify, Response, request
from flask_cors import CORS
from dotenv import load_dotenv
from core.history import HistoryManager
from config import Config
from models import select_model
from utils.logging_config import setup_logger


load_dotenv()
logger = setup_logger("server")

apps = Flask(__name__)# 这段代码是为了解决跨域问题，Flask默认不支持跨域
CORS(apps, resources=r'/*')# CORS的用法是


config = Config("config/base.yaml")
model = select_model(config)


@apps.route('/', methods=["GET"])
def route_index():
    return jsonify({"message": "You Got It!"})


@apps.errorhandler(404)
def page_not_found(e):
    return jsonify({"message": "DEBUG: " + str(e)}), 404


@apps.errorhandler(403)
def page_not_found(e):
    return jsonify({"message": str(e)}), 403
@apps.route('/', methods=['GET'])
def chat_get():
    return "Chat Get!"


@apps.route('/chat', methods=['POST'])
def chat():
    request_data = json.loads(request.data)
    query = request_data['query']
    logger.debug(f"Web query: {query}")

    history_manager = HistoryManager(request_data['history'])
    messages = history_manager.add_user(query)
    logger.debug(f"Web history: {history_manager}")

    def generate_response():
        content = ""
        for delta in model.predict(messages, stream=True):
            content += delta.content
            response_chunk = json.dumps({
                "history": history_manager.update_ai(content),
                "response": content
            }, ensure_ascii=False).encode('utf8') + b'\n'
            yield response_chunk

    return Response(generate_response(), content_type='application/json', status=200)


if __name__ == '__main__':
    print("Starting model...")
    apps.secret_key = os.urandom(24)
    apps.run(host='0.0.0.0', port=8000, debug=False, threaded=True)