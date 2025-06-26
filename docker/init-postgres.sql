-- LightRAG PostgreSQL 初始化脚本
-- 基于官方文档建议: https://github.com/HKUDS/LightRAG

-- 创建必要的扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

-- 加载 AGE 扩展
LOAD 'age';

-- 设置搜索路径
SET search_path = ag_catalog, "$user", public;

-- 创建 LightRAG 图（如果不存在）
-- 注意：这里使用 'lightrag' 作为图名，可以根据需要修改
SELECT create_graph('lightrag');

-- 为 AGE 创建索引以提高性能
-- 替换下面的 'lightrag' 为您的实际图名

-- Entity 表索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS entity_p_idx ON lightrag."Entity" (id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS entity_idx_node_id ON lightrag."Entity" (ag_catalog.agtype_access_operator(properties, '"node_id"'::agtype));
CREATE INDEX CONCURRENTLY IF NOT EXISTS entity_node_id_gin_idx ON lightrag."Entity" using gin(properties);

-- Vertex 表索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS vertex_p_idx ON lightrag."_ag_label_vertex" (id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS vertex_idx_node_id ON lightrag."_ag_label_vertex" (ag_catalog.agtype_access_operator(properties, '"node_id"'::agtype));

-- DIRECTED 关系表索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS directed_p_idx ON lightrag."DIRECTED" (id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS directed_eid_idx ON lightrag."DIRECTED" (end_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS directed_sid_idx ON lightrag."DIRECTED" (start_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS directed_seid_idx ON lightrag."DIRECTED" (start_id,end_id);

-- Edge 表索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS edge_p_idx ON lightrag."_ag_label_edge" (id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS edge_sid_idx ON lightrag."_ag_label_edge" (start_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS edge_eid_idx ON lightrag."_ag_label_edge" (end_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS edge_seid_idx ON lightrag."_ag_label_edge" (start_id,end_id);

-- 集群表以提高性能
ALTER TABLE lightrag."DIRECTED" CLUSTER ON directed_sid_idx;

-- 创建 LightRAG 需要的基础表（如果使用 PostgreSQL 作为 KV store）
CREATE TABLE IF NOT EXISTS lightrag_kv_store (
    key VARCHAR PRIMARY KEY,
    value JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 创建索引
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lightrag_kv_store_updated_at ON lightrag_kv_store(updated_at);

-- 创建文档状态表
CREATE TABLE IF NOT EXISTS lightrag_doc_status (
    doc_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 授权给 lightrag 用户
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO lightrag;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO lightrag;
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO lightrag;

-- 为 AGE 图授权
GRANT ALL PRIVILEGES ON SCHEMA lightrag TO lightrag;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA lightrag TO lightrag;