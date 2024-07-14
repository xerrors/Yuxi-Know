import os
import json
from flask import Blueprint, jsonify, request, Response

from core import HistoryManager
from utils.logging_config import setup_logger
from core.startup import config, model, retriever, dbm

db = Blueprint('database', __name__, url_prefix="/database")

logger = setup_logger("server-database")

@db.route('/', methods=['GET'])
def get_databases():
    database = dbm.get_databases()
    return jsonify(database)

@db.route('/', methods=['POST'])
def create_database():
    database_name = request.args.get('database_name')
    logger.debug(f"Create database {database_name}")
    database = dbm.create_database(database_name)
    return jsonify(database)


@db.route('/add_by_text', methods=['POST'])
def create_document_by_text():
    form_data = request.form
    name = form_data['name']
    text = form_data['text']
    logger.debug(f"Add document in {name} by text: {text}")
    database = dbm.add_text(text, name)
    return jsonify(database)

@db.route('/add_by_file', methods=['POST'])
def create_document_by_file():
    """file Type: multipart/form-data"""
    name = request.form['database_name']
    file = request.files['file']
    logger.debug(f"Adding document {name} by file: {file.filename}")
    if file:
        file_path = os.path.join("data/uploads", file.filename)
        file.save(file_path)
        logger.info(f"Save file {file_path}")
    else:
        logger.error("No file found")
        return jsonify({"message": "No file found"}), 400

    database = dbm.add_file(file_path, name)
    return jsonify(database)


@db.route('/info', methods=['GET'])
def get_database_info():
    name = request.args.get('database_name')
    logger.debug(f"Get database {name} info")
    database = dbm.get_database_info(name)
    return jsonify(database)

@db.route('/info', methods=['DELETE'])
def delete_database():
    return jsonify({"message": "unimplemented"}), 501

@db.route('/document', methods=['GET'])
def get_document_info():
    name = request.args.get('database_name')
    id = request.args.get('id')
    logger.debug(f"Get document {id} in {name}")
    document = dbm.get_document_info(name, id)
    return jsonify(document)

