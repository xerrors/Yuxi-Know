import os
import json
import threading
from functools import wraps
from flask import Blueprint, jsonify, request, Response

from src.utils import setup_logger, hashstr
from src.core.startup import startup

db = Blueprint('database', __name__, url_prefix="/database")

logger = setup_logger("server-database")

progress = {} # 只针对单个用户的进度

def handle_exceptions(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            logger.debug(f"Entering {f.__name__}")
            result = f(*args, **kwargs)
            logger.debug(f"Exiting {f.__name__}")
            return result
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            return jsonify({"message": str(e), "error": "处理请求时发生错误"}), 500
    return decorated_function

@db.route('/', methods=['GET'])
def get_databases():
    try:
        database = startup.dbm.get_databases()
    except Exception as e:
        return jsonify({"message": "获取数据库列表失败", "databases": []})

    return jsonify(database)

@db.route('/', methods=['POST'])
def create_database():
    data = json.loads(request.data)
    database_name = data.get('database_name')
    description = data.get('description')
    db_type = data.get('db_type')
    dimension = data.get('dimension')
    logger.debug(f"Create database {database_name}")
    database = startup.dbm.create_database(database_name, description, db_type, dimension=dimension)
    return jsonify(database)

@db.route('/', methods=['DELETE'])
def delete_database():
    data = json.loads(request.data)
    db_id = data.get('db_id')
    logger.debug(f"Delete database {db_id}")
    startup.dbm.delete_database(db_id)
    return jsonify({"message": "删除成功"})

@db.route('/query-test', methods=['POST'])
def query_test():
    data = json.loads(request.data)
    query = data.get('query')
    meta = data.get('meta')
    logger.debug(f"Query test in {meta}: {query}")

    result = startup.retriever.query_knowledgebase(query, history=None, refs={"meta": meta})
    return jsonify(result)

@db.route('/add_by_file', methods=['POST'])
def create_document_by_file():
    data = json.loads(request.data)
    db_id = data.get('db_id')
    files = data.get('files')
    logger.debug(f"Add document in {db_id} by file: {files}")
    msg = startup.dbm.add_files(db_id, files)
    return jsonify(msg)


@db.route('/info', methods=['GET'])
def get_database_info():
    db_id = request.args.get('db_id')
    if not db_id:
        return jsonify({"message": "db_id is required"}), 400

    logger.debug(f"Get database {db_id} info")
    database = startup.dbm.get_database_info(db_id)

    if database is None:
        return jsonify({"message": "database not found"}), 404

    return jsonify(database)


@db.route('/document', methods=['DELETE'])
def delete_document():
    data = json.loads(request.data)
    db_id = data.get('db_id')
    file_id = data.get('file_id')
    logger.debug(f"DELETE document {file_id} info in {db_id}")
    startup.dbm.delete_file(db_id, file_id)
    return jsonify({"message": "删除成功"})

@db.route('/document', methods=['GET'])
def get_document_info():
    db_id = request.args.get('db_id')
    file_id = request.args.get('file_id')
    logger.debug(f"GET document {file_id} info in {db_id}")
    info = startup.dbm.get_file_info(db_id, file_id)
    return jsonify(info)

@db.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'message': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    # elif file.filename.split('.')[-1] not in ['pdf', 'txt', 'md']:
    #     return jsonify({'message': 'Unsupported file type'}), 400
    if file:
        upload_dir = os.path.join(startup.config.save_dir, "data/uploads")
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{hashstr(file.filename, 4, with_salt=True)}_{file.filename}"
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        return jsonify({'message': 'File successfully uploaded', 'file_path': file_path}), 200

@db.route('/graph', methods=['GET'])
def get_graph_info():
    graph_info = startup.dbm.get_graph()
    return jsonify(graph_info)

@db.route('/graph/node', methods=['GET'])
@handle_exceptions
def get_graph_node():
    assert request.args.get("entity_name"), "entity_name is required"
    logger.debug(f"Get graph node {request.args.get('entity_name')} with {request.args}")
    result = startup.dbm.graph_base.query_node(**request.args)
    return jsonify({'result': startup.retriever.format_query_results(result), 'message': 'success'}), 200

@db.route('/graph/nodes', methods=['GET'])
@handle_exceptions
def get_graph_nodes():
    kgdb_name = request.args.get('kgdb_name')
    num = request.args.get('num')
    assert kgdb_name, "kgdb_name is required"
    assert startup.config.enable_knowledge_graph, "Knowledge graph is not enabled"

    logger.debug(f"Get graph nodes in {kgdb_name} with {num} nodes")
    result = startup.dbm.graph_base.get_sample_nodes(kgdb_name, num)
    return jsonify({'result': startup.retriever.format_general_results(result), 'message': 'success'}), 200

@db.route('/graph/add', methods=['POST'])
@handle_exceptions
def add_graph_entity():
    data = json.loads(request.data)
    kgdb_name = data.get('kgdb_name')
    file_path = data.get('file_path')
    assert file_path.endswith('.jsonl'), "file_path must be a jsonl file"
    assert startup.config.enable_knowledge_graph, "Knowledge graph is not enabled"

    startup.dbm.graph_base.jsonl_file_add_entity(file_path, kgdb_name)

    return jsonify({'message': 'Entity successfully added'}), 200

