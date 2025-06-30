import json
import os
import asyncio
import traceback
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException, Depends
from server.utils.auth_middleware import get_admin_user
from server.models.user_model import User

from src import knowledge_base
from src.utils.logging_config import logger

graph = APIRouter()


@graph.get("/graph/subgraph")
async def get_subgraph(
    db_id: str = Query(..., description="数据库ID"),
    node_label: str = Query(..., description="节点标签或实体名称"),
    max_depth: int = Query(2, description="最大深度", ge=1, le=5),
    max_nodes: int = Query(100, description="最大节点数", ge=1, le=1000),
    current_user: User = Depends(get_admin_user)
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
        logger.info(f"获取子图数据 - db_id: {db_id}, node_label: {node_label}, max_depth: {max_depth}, max_nodes: {max_nodes}")
        
        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"数据库 {db_id} 不存在")
        
        # 使用 LightRAG 的原生 get_knowledge_graph 方法
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label=node_label,
            max_depth=max_depth,
            max_nodes=max_nodes
        )
        
        # 将 LightRAG 的 KnowledgeGraph 格式转换为前端需要的格式
        nodes = []
        for node in knowledge_graph.nodes:
            nodes.append({
                "id": node.id,
                "labels": node.labels,
                "entity_type": node.properties.get("entity_type", "unknown"),
                "properties": node.properties
            })
        
        edges = []
        for edge in knowledge_graph.edges:
            edges.append({
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
                "properties": edge.properties
            })
        
        result = {
            "success": True,
            "data": {
                "nodes": nodes,
                "edges": edges,
                "is_truncated": knowledge_graph.is_truncated,
                "total_nodes": len(nodes),
                "total_edges": len(edges)
            }
        }
        
        logger.info(f"成功获取子图 - 节点数: {len(nodes)}, 边数: {len(edges)}")
        return result
        
    except Exception as e:
        logger.error(f"获取子图数据失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取子图数据失败: {str(e)}")


@graph.get("/graph/labels")
async def get_graph_labels(
    db_id: str = Query(..., description="数据库ID"),
    current_user: User = Depends(get_admin_user)
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
        
        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"数据库 {db_id} 不存在")
        
        # 使用 LightRAG 的原生方法获取所有标签
        labels = await rag_instance.get_graph_labels()
        
        return {
            "success": True,
            "data": {
                "labels": labels
            }
        }
        
    except Exception as e:
        logger.error(f"获取图谱标签失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取图谱标签失败: {str(e)}")


@graph.get("/graph/databases")
async def get_available_databases(
    current_user: User = Depends(get_admin_user)
):
    """
    获取所有可用的 LightRAG 数据库
    
    Returns:
        可用的数据库列表
    """
    try:
        databases = knowledge_base.get_databases()
        return {
            "success": True,
            "data": databases
        }
        
    except Exception as e:
        logger.error(f"获取数据库列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取数据库列表失败: {str(e)}")


# 保留原有的直接数据库查询方法作为备用（如果需要的话）
@graph.get("/graph/nodes")
async def get_graph_nodes_legacy(
    db_id: str = Query(..., description="数据库ID"),
    limit: int = Query(500, description="最大节点数量", ge=1, le=2000),
    offset: int = Query(0, description="偏移量", ge=0),
    entity_type: Optional[str] = Query(None, description="实体类型筛选"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: User = Depends(get_admin_user)
):
    """
    直接查询数据库获取节点数据（备用方法）
    建议使用 /graph/subgraph 接口
    """
    try:
        # 这里可以添加直接数据库查询的逻辑
        # 但建议用户使用 get_subgraph 接口
        return {
            "success": False,
            "message": "建议使用 /graph/subgraph 接口获取图谱数据",
            "data": {
                "nodes": [],
                "total": 0
            }
        }
        
    except Exception as e:
        logger.error(f"获取图节点数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图节点数据失败: {str(e)}")


@graph.get("/graph/edges")
async def get_graph_edges_legacy(
    db_id: str = Query(..., description="数据库ID"),
    limit: int = Query(500, description="最大边数量", ge=1, le=2000),
    offset: int = Query(0, description="偏移量", ge=0),
    min_weight: Optional[float] = Query(None, description="最小权重筛选"),
    current_user: User = Depends(get_admin_user)
):
    """
    直接查询数据库获取边数据（备用方法）
    建议使用 /graph/subgraph 接口
    """
    try:
        # 这里可以添加直接数据库查询的逻辑
        # 但建议用户使用 get_subgraph 接口
        return {
            "success": False,
            "message": "建议使用 /graph/subgraph 接口获取图谱数据",
            "data": {
                "edges": [],
                "total": 0
            }
        }
        
    except Exception as e:
        logger.error(f"获取图边数据失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图边数据失败: {str(e)}")


@graph.get("/graph/stats")
async def get_graph_stats(
    db_id: str = Query(..., description="数据库ID"),
    current_user: User = Depends(get_admin_user)
):
    """
    获取知识图谱统计信息
    """
    try:
        logger.info(f"获取图谱统计信息 - db_id: {db_id}")
        
        # 获取 LightRAG 实例
        rag_instance = await knowledge_base._get_lightrag_instance(db_id)
        if not rag_instance:
            raise HTTPException(status_code=404, detail=f"数据库 {db_id} 不存在")
        
        # 通过获取全图来统计节点和边的数量
        knowledge_graph = await rag_instance.get_knowledge_graph(
            node_label="*",
            max_depth=1,
            max_nodes=10000  # 设置较大值以获取完整统计
        )
        
        # 统计实体类型分布
        entity_types = {}
        for node in knowledge_graph.nodes:
            entity_type = node.properties.get("entity_type", "unknown")
            entity_types[entity_type] = entity_types.get(entity_type, 0) + 1
        
        entity_types_list = [
            {"type": k, "count": v} 
            for k, v in sorted(entity_types.items(), key=lambda x: x[1], reverse=True)
        ]
        
        return {
            "success": True,
            "data": {
                "total_nodes": len(knowledge_graph.nodes),
                "total_edges": len(knowledge_graph.edges),
                "entity_types": entity_types_list,
                "is_truncated": knowledge_graph.is_truncated
            }
        }
        
    except Exception as e:
        logger.error(f"获取图谱统计信息失败: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"获取图谱统计信息失败: {str(e)}")