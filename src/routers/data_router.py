import os
import asyncio
import traceback
from typing import List, Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends, Body

from src.utils import logger, hashstr
from src import executor, dbm, retriever, config

data = APIRouter(prefix="/data")


@data.get("/")
async def get_databases():
    try:
        database = dbm.get_databases()
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
    database_info = dbm.create_database(
        database_name,
        description,
        db_type,
        dimension=dimension
    )
    return database_info

@data.delete("/")
async def delete_database(db_id):
    logger.debug(f"Delete database {db_id}")
    dbm.delete_database(db_id)
    return {"message": "删除成功"}

@data.post("/query-test")
async def query_test(query: str = Body(...), meta: dict = Body(...)):
    logger.debug(f"Query test in {meta}: {query}")
    result = retriever.query_knowledgebase(query, history=None, refs={"meta": meta})
    return result

@data.post("/add-by-file")
async def create_document_by_file(db_id: str = Body(...), files: List[str] = Body(...)):
    logger.debug(f"Add document in {db_id} by file: {files}")
    try:
        # 使用线程池执行耗时操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            executor,  # 使用与chat_router相同的线程池
            lambda: dbm.add_files(db_id, files)
        )
        return {"message": "文件添加完成", "status": "success"}
    except Exception as e:
        logger.error(f"添加文件失败: {e}")
        return {"message": f"添加文件失败: {e}", "status": "failed"}

@data.get("/info")
async def get_database_info(db_id: str):
    logger.debug(f"Get database {db_id} info")
    database = dbm.get_database_info(db_id)
    if database is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return database

@data.delete("/document")
async def delete_document(db_id: str = Body(...), file_id: str = Body(...)):
    logger.debug(f"DELETE document {file_id} info in {db_id}")
    dbm.delete_file(db_id, file_id)
    return {"message": "删除成功"}

@data.get("/document")
async def get_document_info(db_id: str, file_id: str):
    logger.debug(f"GET document {file_id} info in {db_id}")

    try:
        info = dbm.get_file_info(db_id, file_id)
    except Exception as e:
        logger.error(f"Failed to get file info, {e}, {db_id=}, {file_id=}, {traceback.format_exc()}")
        info = {"message": "Failed to get file info", "status": "failed"}, 500

    return info

@data.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No selected file")

    upload_dir = os.path.join(config.save_dir, "data/uploads")
    os.makedirs(upload_dir, exist_ok=True)
    basename, ext = os.path.splitext(file.filename)
    filename = f"{basename}_{hashstr(basename, 4, with_salt=True)}{ext}".lower()
    file_path = os.path.join(upload_dir, filename)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {"message": "File successfully uploaded", "file_path": file_path}

@data.get("/graph")
async def get_graph_info():
    graph_info = dbm.get_graph()

    # 获取未索引节点数量
    unindexed_count = 0
    if dbm.is_graph_running():
        # 调用GraphDatabase的query_nodes_without_embedding方法
        unindexed_nodes = dbm.graph_base.query_nodes_without_embedding()
        unindexed_count = len(unindexed_nodes) if unindexed_nodes else 0

    # 将未索引节点数量添加到返回结果中
    graph_info["graph"]["unindexed_node_count"] = unindexed_count

    return graph_info

@data.post("/graph/index-nodes")
async def index_nodes(data: dict = Body(default={})):
    if not dbm.is_graph_running():
        raise HTTPException(status_code=400, detail="图数据库未启动")

    # 获取参数或使用默认值
    kgdb_name = data.get('kgdb_name', 'neo4j')

    # 调用GraphDatabase的add_embedding_to_nodes方法
    count = dbm.graph_base.add_embedding_to_nodes(kgdb_name=kgdb_name)

    return {"status": "success", "message": f"已成功为{count}个节点添加嵌入向量", "indexed_count": count}

@data.get("/graph/node")
async def get_graph_node(entity_name: str):
    result = dbm.graph_base.query_node(entity_name=entity_name)
    return {"result": retriever.format_query_results(result), "message": "success"}

@data.get("/graph/nodes")
async def get_graph_nodes(kgdb_name: str, num: int):
    if not config.enable_knowledge_graph:
        raise HTTPException(status_code=400, detail="Knowledge graph is not enabled")

    logger.debug(f"Get graph nodes in {kgdb_name} with {num} nodes")
    result = dbm.graph_base.get_sample_nodes(kgdb_name, num)
    return {"result": retriever.format_general_results(result), "message": "success"}

@data.post("/graph/add-by-jsonl")
async def add_graph_entity(file_path: str = Body(...), kgdb_name: Optional[str] = Body(None)):
    if not config.enable_knowledge_graph:
        raise HTTPException(status_code=400, detail="Knowledge graph is not enabled")

    if not file_path.endswith('.jsonl'):
        raise HTTPException(status_code=400, detail="file_path must be a jsonl file")

    dbm.graph_base.jsonl_file_add_entity(file_path, kgdb_name)
    return {"message": "Entity successfully added"}

