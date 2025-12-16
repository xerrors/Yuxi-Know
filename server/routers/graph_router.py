import traceback

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.storage.db.models import User
from server.utils.auth_middleware import get_admin_user
from src import graph_base, knowledge_base
from src.knowledge.adapters.factory import GraphAdapterFactory
from src.knowledge.adapters.base import GraphAdapter
from src.utils.logging_config import logger

graph = APIRouter(prefix="/graph", tags=["graph"])


# =============================================================================
# === 统一图谱接口 (Unified Graph API) ===
# =============================================================================


async def _get_graph_adapter(db_id: str) -> GraphAdapter:
    """
    根据数据库ID获取对应的图谱适配器

    Args:
        db_id: 数据库ID

    Returns:
        GraphAdapter: 对应的图谱适配器实例
    """
    # 1. 检查是否是 LightRAG 数据库
    if knowledge_base.is_lightrag_database(db_id):
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"LightRAG database {db_id} not found or inaccessible")
        return GraphAdapterFactory.create_adapter("lightrag", lightrag_instance=rag_instance)

    # 2. 默认为 Upload/Neo4j 数据库 (假设 db_id 为 "neo4j" 或其他 Neo4j 数据库名)
    # 这里我们假设非 LightRAG 的 ID 都是 Neo4j 的数据库名
    # 如果未来有更多类型，需要更完善的 ID 区分机制 (例如前缀)
    if not graph_base.is_running():
        raise HTTPException(status_code=503, detail="Graph database service is not running")

    return GraphAdapterFactory.create_adapter("upload", graph_db_instance=graph_base, config={"kgdb_name": db_id})


@graph.get("/list")
async def get_graphs(current_user: User = Depends(get_admin_user)):
    """
    获取所有可用的知识图谱列表

    Returns:
        包含所有图谱信息的列表 (包括 Neo4j 和 LightRAG)
    """
    try:
        graphs = []

        # 1. 获取默认 Neo4j 图谱信息
        neo4j_info = graph_base.get_graph_info()
        if neo4j_info:
            graphs.append(
                {
                    "id": "neo4j",
                    "name": "默认图谱",
                    "type": "neo4j",
                    "description": "Default graph database for uploaded documents",
                    "status": neo4j_info.get("status", "unknown"),
                    "created_at": neo4j_info.get("last_updated"),
                    "node_count": neo4j_info.get("entity_count", 0),
                    "edge_count": neo4j_info.get("relationship_count", 0),
                }
            )

        # 2. 获取 LightRAG 数据库信息
        lightrag_dbs = knowledge_base.get_lightrag_databases()
        for db in lightrag_dbs:
            graphs.append(
                {
                    "id": db.get("db_id"),
                    "name": db.get("name"),
                    "type": "lightrag",
                    "description": db.get("description"),
                    "status": "active",  # LightRAG DBs are usually active if listed
                    "created_at": db.get("created_at"),
                    "metadata": db,
                }
            )

        return {"success": True, "data": graphs}

    except Exception as e:
        logger.error(f"Failed to list graphs: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to list graphs: {str(e)}")


@graph.get("/subgraph")
async def get_subgraph(
    db_id: str = Query(..., description="知识图谱ID"),
    node_label: str = Query("*", description="节点标签或查询关键词"),
    max_depth: int = Query(2, description="最大深度", ge=1, le=5),
    max_nodes: int = Query(100, description="最大节点数", ge=1, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """
    统一的子图查询接口

    Args:
        db_id: 图谱ID (LightRAG DB ID 或 "neo4j")
        node_label: 查询关键词或标签
        max_depth: 扩展深度
        max_nodes: 返回最大节点数
    """
    try:
        logger.info(f"Querying subgraph - db_id: {db_id}, label: {node_label}")

        adapter = await _get_graph_adapter(db_id)

        # 统一查询参数
        # 对于 UploadGraphAdapter, kgdb_name 通常通过 kwargs 传递
        # 对于 LightRAGGraphAdapter, max_depth/max_nodes 通过 kwargs 传递
        result_data = await adapter.query_nodes(
            keyword=node_label,
            max_depth=max_depth,
            max_nodes=max_nodes,
            kgdb_name=db_id if not knowledge_base.is_lightrag_database(db_id) else "neo4j",
        )

        return {
            "success": True,
            "data": result_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get subgraph: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to get subgraph: {str(e)}")


@graph.get("/labels")
async def get_graph_labels(
    db_id: str = Query(..., description="知识图谱ID"), current_user: User = Depends(get_admin_user)
):
    """
    获取图谱的所有标签
    """
    try:
        adapter = await _get_graph_adapter(db_id)
        labels = await adapter.get_labels()
        return {"success": True, "data": {"labels": labels}}

    except Exception as e:
        logger.error(f"Failed to get labels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get labels: {str(e)}")


@graph.get("/stats")
async def get_graph_stats(
    db_id: str = Query(..., description="知识图谱ID"), current_user: User = Depends(get_admin_user)
):
    """
    获取图谱统计信息
    """
    try:
        if knowledge_base.is_lightrag_database(db_id):
            # 复用原有的 LightRAG 统计逻辑
            # 这里暂时直接调用原有逻辑，理想情况下也应该封装进 Adapter
            rag_instance = await knowledge_base._get_lightrag_instance(db_id)
            if not rag_instance:
                raise HTTPException(status_code=404, detail="Database not found")

            knowledge_graph = await rag_instance.get_knowledge_graph(node_label="*", max_depth=1, max_nodes=10000)
            entity_types = {}
            for node in knowledge_graph.nodes:
                entity_type = node.properties.get("entity_type", "unknown")
                entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

            entity_types_list = [
                {"type": k, "count": v} for k, v in sorted(entity_types.items(), key=lambda x: x[1], reverse=True)
            ]

            return {
                "success": True,
                "data": {
                    "total_nodes": len(knowledge_graph.nodes),
                    "total_edges": len(knowledge_graph.edges),
                    "entity_types": entity_types_list,
                },
            }
        else:
            # Neo4j stats
            info = graph_base.get_graph_info(graph_name=db_id)
            if not info:
                raise HTTPException(status_code=404, detail="Graph info not found")

            return {
                "success": True,
                "data": {
                    "total_nodes": info.get("entity_count", 0),
                    "total_edges": info.get("relationship_count", 0),
                    # Neo4j info currently returns 'labels' list, not counts per label.
                    # Improving this would require updating GraphDatabase.get_graph_info
                    "entity_types": [{"type": label, "count": "N/A"} for label in info.get("labels", [])],
                },
            }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


# =============================================================================
# === 兼容性接口 (Deprecated/Compatibility) ===
# =============================================================================


@graph.get("/lightrag/subgraph")
async def get_lightrag_subgraph(
    db_id: str = Query(..., description="数据库ID"),
    node_label: str = Query(..., description="节点标签或实体名称"),
    max_depth: int = Query(2, description="最大深度", ge=1, le=5),
    max_nodes: int = Query(100, description="最大节点数", ge=1, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """(Deprecated) Use /graph/subgraph instead"""
    return await get_subgraph(
        db_id=db_id, node_label=node_label, max_depth=max_depth, max_nodes=max_nodes, current_user=current_user
    )


@graph.get("/lightrag/databases")
async def get_lightrag_databases(current_user: User = Depends(get_admin_user)):
    """(Deprecated) Use /graph/list instead"""
    try:
        lightrag_databases = knowledge_base.get_lightrag_databases()
        return {"success": True, "data": {"databases": lightrag_databases}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@graph.get("/lightrag/labels")
async def get_lightrag_labels(
    db_id: str = Query(..., description="数据库ID"), current_user: User = Depends(get_admin_user)
):
    """(Deprecated) Use /graph/labels instead"""
    return await get_graph_labels(db_id=db_id, current_user=current_user)


@graph.get("/lightrag/stats")
async def get_lightrag_stats(
    db_id: str = Query(..., description="数据库ID"), current_user: User = Depends(get_admin_user)
):
    """(Deprecated) Use /graph/stats instead"""
    return await get_graph_stats(db_id=db_id, current_user=current_user)


@graph.get("/neo4j/nodes")
async def get_neo4j_nodes(
    kgdb_name: str = Query(..., description="知识图谱数据库名称"),
    num: int = Query(100, description="节点数量", ge=1, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """(Deprecated) Use /graph/subgraph instead"""
    response = await get_subgraph(db_id=kgdb_name, node_label="*", max_nodes=num, current_user=current_user)
    return {"success": True, "result": response["data"], "message": "success"}


@graph.get("/neo4j/node")
async def get_neo4j_node(
    entity_name: str = Query(..., description="实体名称"), current_user: User = Depends(get_admin_user)
):
    """(Deprecated) Use /graph/subgraph instead"""
    # neo4j/node uses query_nodes(keyword=entity_name)
    response = await get_subgraph(db_id="neo4j", node_label=entity_name, current_user=current_user)
    return {"success": True, "result": response["data"], "message": "success"}


@graph.get("/neo4j/info")
async def get_neo4j_info(current_user: User = Depends(get_admin_user)):
    """获取Neo4j图数据库信息"""
    try:
        graph_info = graph_base.get_graph_info()
        if graph_info is None:
            raise HTTPException(status_code=400, detail="图数据库获取出错")
        return {"success": True, "data": graph_info}
    except Exception as e:
        logger.error(f"获取图数据库信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图数据库信息失败: {str(e)}")


@graph.post("/neo4j/index-entities")
async def index_neo4j_entities(data: dict = Body(default={}), current_user: User = Depends(get_admin_user)):
    """为Neo4j图谱节点添加嵌入向量索引"""
    try:
        if not graph_base.is_running():
            raise HTTPException(status_code=400, detail="图数据库未启动")

        kgdb_name = data.get("kgdb_name", "neo4j")
        count = graph_base.add_embedding_to_nodes(kgdb_name=kgdb_name)

        return {
            "success": True,
            "status": "success",
            "message": f"已成功为{count}个节点添加嵌入向量",
            "indexed_count": count,
        }
    except Exception as e:
        logger.error(f"索引节点失败: {e}")
        raise HTTPException(status_code=500, detail=f"索引节点失败: {str(e)}")


@graph.post("/neo4j/add-entities")
async def add_neo4j_entities(
    file_path: str = Body(...), kgdb_name: str | None = Body(None), current_user: User = Depends(get_admin_user)
):
    """通过JSONL文件添加图谱实体到Neo4j"""
    try:
        if not file_path.endswith(".jsonl"):
            return {"success": False, "message": "文件格式错误，请上传jsonl文件", "status": "failed"}

        await graph_base.jsonl_file_add_entity(file_path, kgdb_name)
        return {"success": True, "message": "实体添加成功", "status": "success"}
    except Exception as e:
        logger.error(f"添加实体失败: {e}, {traceback.format_exc()}")
        return {"success": False, "message": f"添加实体失败: {e}", "status": "failed"}
