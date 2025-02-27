import os
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Body

from src.utils import logger, hashstr
from src.core.startup import startup

data = APIRouter(prefix="/data")


@data.get("/")
def get_databases():
    try:
        database = startup.dbm.get_databases()
    except Exception as e:
        return {"message": f"获取数据库列表失败 {e}", "databases": []}
    return database

@data.post("/")
async def create_database(
    database_name: str = Body(...),
    description: str = Body(...),
    db_type: str = Body(...),
    dimension: Optional[int] = Body(None)
):
    logger.debug(f"Create database {database_name}")
    database_info = startup.dbm.create_database(
        database_name,
        description,
        db_type,
        dimension=dimension
    )
    return database_info

@data.delete("/")
async def delete_database(db_id):
    logger.debug(f"Delete database {db_id}")
    startup.dbm.delete_database(db_id)
    return {"message": "删除成功"}

@data.post("/query-test")
async def query_test(query: str = Body(...), meta: dict = Body(...)):
    logger.debug(f"Query test in {meta}: {query}")
    result = startup.retriever.query_knowledgebase(query, history=None, refs={"meta": meta})
    return result

@data.post("/add-by-file")
async def create_document_by_file(db_id: str = Body(...), files: List[str] = Body(...)):
    logger.debug(f"Add document in {db_id} by file: {files}")
    msg = startup.dbm.add_files(db_id, files)
    return msg

@data.get("/info")
async def get_database_info(db_id: str):
    logger.debug(f"Get database {db_id} info")
    database = startup.dbm.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@data.delete("/document")
async def delete_document(db_id: str = Body(...), file_id: str = Body(...)):
    logger.debug(f"DELETE document {file_id} info in {db_id}")
    startup.dbm.delete_file(db_id, file_id)
    return {"message": "删除成功"}

@data.get("/document")
async def get_document_info(db_id: str, file_id: str):
    logger.debug(f"GET document {file_id} info in {db_id}")

    try:
        info = startup.dbm.get_file_info(db_id, file_id)
    except Exception as e:
        logger.error(f"Failed to get file info, {e}, {db_id=}, {file_id=}")
        info = {"message": "Failed to get file info", "status": "failed"}, 500

    return info

@data.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")

    upload_dir = os.path.join(startup.config.save_dir, "data/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    basename, ext = os.path.splitext(file.filename)
    filename = f"{basename}_{hashstr(basename, 4, with_salt=True)}_{ext}".lower()
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"message": "File successfully uploaded", "file_path": file_path}

@data.get("/graph")
async def get_graph_info():
    graph_info = startup.dbm.get_graph()
    return graph_info

@data.get("/graph/node")
async def get_graph_node(entity_name: str):
    logger.debug(f"Get graph node {entity_name}")
    result = startup.dbm.graph_base.query_node(entity_name=entity_name)
    return {"result": startup.retriever.format_query_results(result), "message": "success"}

@data.get("/graph/nodes")
async def get_graph_nodes(kgdb_name: str, num: int):
    if not startup.config.enable_knowledge_graph:
        raise HTTPException(status_code=400, detail="Knowledge graph is not enabled")

    logger.debug(f"Get graph nodes in {kgdb_name} with {num} nodes")
    result = startup.dbm.graph_base.get_sample_nodes(kgdb_name, num)
    return {"result": startup.retriever.format_general_results(result), "message": "success"}

@data.post("/graph/add-by-jsonl")
async def add_graph_entity(file_path: str = Body(...), kgdb_name: Optional[str] = Body(None)):
    if not startup.config.enable_knowledge_graph:
        raise HTTPException(status_code=400, detail="Knowledge graph is not enabled")

    if not file_path.endswith('.jsonl'):
        raise HTTPException(status_code=400, detail="file_path must be a jsonl file")

    startup.dbm.graph_base.jsonl_file_add_entity(file_path, kgdb_name)
    return {"message": "Entity successfully added"}

