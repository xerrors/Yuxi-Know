import traceback

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from src.storage.db.models import User
from server.utils.auth_middleware import get_admin_user
from src import graph_base, knowledge_base
from src.utils.logging_config import logger

graph = APIRouter(prefix="/graph", tags=["graph"])


# =============================================================================
# === 子图查询分组 ===
# =============================================================================


@graph.get("/lightrag/subgraph")
async def get_lightrag_subgraph(
    db_id: str = Query(..., description="数据库ID"),
    node_label: str = Query(..., description="节点标签或实体名称"),
    max_depth: int = Query(2, description="最大深度", ge=1, le=5),
    max_nodes: int = Query(100, description="最大节点数", ge=1, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """
    使用 LightRAG 原生方法获取知识图谱子图

    Args:
        db_id: LightRAG 数据库实例ID
        node_label: 节点标签，用于查找起始节点，使用 "*" 获取全图
        max_depth: 子图的最大深度
        max_nodes: 返回的最大节点数量

    Returns:
        包含节点和边的知识图谱数据
    """
    try:
        logger.info(
            f"获取子图数据 - db_id: {db_id}, node_label: {node_label}, max_depth: {max_depth}, max_nodes: {max_nodes}"
        )

        # 检查是否是 LightRAG 数据库
        if not knowledge_base.is_lightrag_database(db_id):
            raise HTTPException(
                status_code=400, detail=f"数据库 {db_id} 不是 LightRAG 类型，图谱功能仅支持 LightRAG 知识库"
            )

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"LightRAG 数据库 {db_id} 不存在或无法访问")

        # 使用 LightRAG 的原生 get_knowledge_graph 方法
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label=node_label, max_depth=max_depth, max_nodes=max_nodes
        )

        # 将 LightRAG 的 KnowledgeGraph 格式转换为前端需要的格式
        nodes = []
        for node in knowledge_graph.nodes:
            nodes.append(
                {
                    "id": node.id,
                    "labels": node.labels,
                    "entity_type": node.properties.get("entity_type", "unknown"),
                    "properties": node.properties,
                }
            )

        edges = []
        for edge in knowledge_graph.edges:
            edges.append(
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type,
                    "properties": edge.properties,
                }
            )

        result = {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "is_truncated": knowledge_graph.is_truncated,
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        }

        logger.info(f"成功获取子图 - 节点数: {len(nodes)}, 边数: {len(edges)}")
        return result

    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        logger.error(f"获取子图数据失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取子图数据失败: {str(e)}")


@graph.get("/lightrag/databases")
async def get_lightrag_databases(current_user: User = Depends(get_admin_user)):
    """
    获取所有可用的 LightRAG 数据库

    Returns:
        可用的 LightRAG 数据库列表
    """
    try:
        lightrag_databases = knowledge_base.get_lightrag_databases()
        return {"success": True, "data": {"databases": lightrag_databases}}

    except Exception as e:
        logger.error(f"获取 LightRAG 数据库列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 LightRAG 数据库列表失败: {str(e)}")


# =============================================================================
# === 节点管理分组 ===
# =============================================================================


@graph.get("/lightrag/labels")
async def get_lightrag_labels(
    db_id: str = Query(..., description="数据库ID"), current_user: User = Depends(get_admin_user)
):
    """
    获取知识图谱中的所有标签

    Args:
        db_id: LightRAG 数据库实例ID

    Returns:
        图谱中所有可用的标签列表
    """
    try:
        logger.info(f"获取图谱标签 - db_id: {db_id}")

        # 检查是否是 LightRAG 数据库
        if not knowledge_base.is_lightrag_database(db_id):
            raise HTTPException(
                status_code=400, detail=f"数据库 {db_id} 不是 LightRAG 类型，图谱功能仅支持 LightRAG 知识库"
            )

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"LightRAG 数据库 {db_id} 不存在或无法访问")

        # 使用 LightRAG 的原生方法获取所有标签
        labels = await rag_instance.get_graph_labels()

        return {"success": True, "data": {"labels": labels}}

    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        logger.error(f"获取图谱标签失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取图谱标签失败: {str(e)}")


@graph.get("/neo4j/nodes")
async def get_neo4j_nodes(
    kgdb_name: str = Query(..., description="知识图谱数据库名称"),
    num: int = Query(100, description="节点数量", ge=1, le=1000),
    current_user: User = Depends(get_admin_user),
):
    """
    获取图谱节点样本数据
    """
    try:
        logger.debug(f"Get graph nodes in {kgdb_name} with {num} nodes")

        if not graph_base.is_running():
            raise HTTPException(status_code=400, detail="图数据库未启动")

        result = graph_base.get_sample_nodes(kgdb_name, num)

        return {"success": True, "result": result, "message": "success"}

    except Exception as e:
        logger.error(f"获取图节点数据失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取图节点数据失败: {str(e)}")


@graph.get("/neo4j/node")
async def get_neo4j_node(
    entity_name: str = Query(..., description="实体名称"), current_user: User = Depends(get_admin_user)
):
    """
    根据实体名称查询图节点
    """
    try:
        if not graph_base.is_running():
            raise HTTPException(status_code=400, detail="图数据库未启动")

        result = graph_base.query_node(keyword=entity_name)

        return {"success": True, "result": result, "message": "success"}

    except Exception as e:
        logger.error(f"查询图节点失败: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"查询图节点失败: {str(e)}")


# =============================================================================
# === 边管理分组 ===
# =============================================================================

# 可以在这里添加边相关的管理功能

# =============================================================================
# === 图谱分析分组 ===
# =============================================================================


@graph.get("/lightrag/test-data")
async def create_test_graph_data(
    db_id: str = Query(..., description="数据库ID"), current_user: User = Depends(get_admin_user)
):
    """
    创建测试图谱数据（临时API，用于演示图谱功能）
    """
    try:
        logger.info(f"创建测试图谱数据 - db_id: {db_id}")

        # 检查是否是 LightRAG 数据库
        if not knowledge_base.is_lightrag_database(db_id):
            raise HTTPException(
                status_code=400, detail=f"数据库 {db_id} 不是 LightRAG 类型，图谱功能仅支持 LightRAG 知识库"
            )

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"LightRAG 数据库 {db_id} 不存在或无法访问")

        # 创建测试图谱数据
        test_nodes = [
            {
                'id': '宋晓宁',
                'labels': ['人物'],
                'entity_type': 'person',
                'properties': {
                    'entity_id': '宋晓宁',
                    'entity_type': 'person',
                    'description': '人工智能学院项目负责人',
                    'file_path': 'test'
                }
            },
            {
                'id': '江南大学',
                'labels': ['机构'],
                'entity_type': 'organization',
                'properties': {
                    'entity_id': '江南大学',
                    'entity_type': 'organization',
                    'description': '江南大学',
                    'file_path': 'test'
                }
            },
            {
                'id': '食品安全知识图谱',
                'labels': ['项目'],
                'entity_type': 'project',
                'properties': {
                    'entity_id': '食品安全知识图谱',
                    'entity_type': 'project',
                    'description': '食品安全知识图谱和监管控制平台的构建与应用示范',
                    'file_path': 'test'
                }
            },
            {
                'id': '无锡君桥汽车租赁有限公司',
                'labels': ['公司'],
                'entity_type': 'company',
                'properties': {
                    'entity_id': '无锡君桥汽车租赁有限公司',
                    'entity_type': 'company',
                    'description': '汽车租赁服务公司',
                    'file_path': 'test'
                }
            },
            {
                'id': '租车费',
                'labels': ['费用'],
                'entity_type': 'expense',
                'properties': {
                    'entity_id': '租车费',
                    'entity_type': 'expense',
                    'description': '租车费用300元',
                    'file_path': 'test'
                }
            }
        ]

        test_edges = [
            {
                'id': '宋晓宁-江南大学-工作于',
                'source': '宋晓宁',
                'target': '江南大学',
                'type': 'WORKS_AT',
                'properties': {
                    'description': '宋晓宁工作于江南大学',
                    'keywords': '工作关系'
                }
            },
            {
                'id': '宋晓宁-食品安全知识图谱-负责',
                'source': '宋晓宁',
                'target': '食品安全知识图谱',
                'type': 'RESPONSIBLE_FOR',
                'properties': {
                    'description': '宋晓宁负责食品安全知识图谱项目',
                    'keywords': '负责关系'
                }
            },
            {
                'id': '宋晓宁-租车费-产生',
                'source': '宋晓宁',
                'target': '租车费',
                'type': 'INCURRED',
                'properties': {
                    'description': '宋晓宁产生租车费用',
                    'keywords': '费用关系'
                }
            },
            {
                'id': '租车费-无锡君桥汽车租赁有限公司-支付给',
                'source': '租车费',
                'target': '无锡君桥汽车租赁有限公司',
                'type': 'PAID_TO',
                'properties': {
                    'description': '租车费支付给无锡君桥汽车租赁有限公司',
                    'keywords': '支付关系'
                }
            }
        ]

        result = {
            "success": True,
            "data": {
                "nodes": test_nodes,
                "edges": test_edges,
                "is_truncated": False,
                "total_nodes": len(test_nodes),
                "total_edges": len(test_edges),
            },
        }

        logger.info(f"成功创建测试图谱 - 节点数: {len(test_nodes)}, 边数: {len(test_edges)}")
        return result

    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        logger.error(f"创建测试图谱数据失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"创建测试图谱数据失败: {str(e)}")


@graph.get("/lightrag/stats")
async def get_lightrag_stats(
    db_id: str = Query(..., description="数据库ID"), current_user: User = Depends(get_admin_user)
):
    """
    获取知识图谱统计信息
    """
    try:
        logger.info(f"获取图谱统计信息 - db_id: {db_id}")

        # 检查是否是 LightRAG 数据库
        if not knowledge_base.is_lightrag_database(db_id):
            raise HTTPException(
                status_code=400, detail=f"数据库 {db_id} 不是 LightRAG 类型，图谱功能仅支持 LightRAG 知识库"
            )

        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"LightRAG 数据库 {db_id} 不存在或无法访问")

        # 通过获取全图来统计节点和边的数量
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label="*",
            max_depth=1,
            max_nodes=10000,  # 设置较大值以获取完整统计
        )

        # 统计实体类型分布
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
                "is_truncated": knowledge_graph.is_truncated,
            },
        }

    except HTTPException:
        # 重新抛出 HTTP 异常
        raise
    except Exception as e:
        logger.error(f"获取图谱统计信息失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取图谱统计信息失败: {str(e)}")


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

        # 获取参数或使用默认值
        kgdb_name = data.get("kgdb_name", "neo4j")

        # 调用GraphDatabase的add_embedding_to_nodes方法
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
