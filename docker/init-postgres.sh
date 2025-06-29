#!/bin/bash

# PostgreSQL 初始化脚本
# 适用于 shangor/postgres-for-rag 镜像

set -e

echo "Starting PostgreSQL initialization..."

# 启动 PostgreSQL 服务
service postgresql start
sleep 10

echo "PostgreSQL service started, waiting for it to be ready..."

# 等待 PostgreSQL 完全启动
while ! su - postgres -c "pg_isready" > /dev/null 2>&1; do
    echo "Waiting for PostgreSQL to be ready..."
    sleep 2
done

echo "PostgreSQL is ready, creating user and database..."

# 创建用户（如果不存在）
if ! su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER:-lightrag}'\"" | grep -q 1; then
    echo "Creating user ${POSTGRES_USER:-lightrag}..."
    su - postgres -c "createuser -s ${POSTGRES_USER:-lightrag}"
else
    echo "User ${POSTGRES_USER:-lightrag} already exists"
fi

# 创建数据库（如果不存在）
if ! su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DATABASE:-lightrag}'\"" | grep -q 1; then
    echo "Creating database ${POSTGRES_DATABASE:-lightrag}..."
    su - postgres -c "createdb -O ${POSTGRES_USER:-lightrag} ${POSTGRES_DATABASE:-lightrag}"
else
    echo "Database ${POSTGRES_DATABASE:-lightrag} already exists"
fi

# 设置密码
echo "Setting password for user ${POSTGRES_USER:-lightrag}..."
su - postgres -c "psql -c \"ALTER USER ${POSTGRES_USER:-lightrag} PASSWORD '${POSTGRES_PASSWORD:-lightrag}';\""

# 配置 pg_hba.conf 以允许密码认证
echo "Configuring PostgreSQL authentication..."
PG_HBA_CONF="/etc/postgresql/16/main/pg_hba.conf"
# 备份原始配置
cp $PG_HBA_CONF $PG_HBA_CONF.backup

# 创建新的 pg_hba.conf 文件，确保 lightrag 用户的规则在前面
cat > $PG_HBA_CONF << EOF
# PostgreSQL Client Authentication Configuration File
# ===================================================

# TYPE  DATABASE        USER            ADDRESS                 METHOD

# LightRAG user authentication (must be first to take precedence)
local   ${POSTGRES_DATABASE:-lightrag}   ${POSTGRES_USER:-lightrag}                      md5
host    ${POSTGRES_DATABASE:-lightrag}   ${POSTGRES_USER:-lightrag}   127.0.0.1/32      md5
host    ${POSTGRES_DATABASE:-lightrag}   ${POSTGRES_USER:-lightrag}   ::1/128           md5
host    ${POSTGRES_DATABASE:-lightrag}   ${POSTGRES_USER:-lightrag}   0.0.0.0/0         md5

# Default configurations
local   all             postgres                                peer
local   all             all                                     peer
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256
local   replication     all                                     peer
host    replication     all             127.0.0.1/32            scram-sha-256
host    replication     all             ::1/128                 scram-sha-256
EOF

# 重启 PostgreSQL 以应用 pg_hba.conf 更改
echo "Restarting PostgreSQL to apply authentication changes..."
service postgresql restart
sleep 5

echo "Installing extensions..."

# 安装 vector 扩展
echo "Installing vector extension..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"CREATE EXTENSION IF NOT EXISTS vector;\""

# 安装 age 扩展
echo "Installing age extension..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"CREATE EXTENSION IF NOT EXISTS age;\""

echo "Configuring AGE extension..."

# 加载 AGE 扩展
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"LOAD 'age';\""

# 设置搜索路径
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"SET search_path = ag_catalog, public;\""

# 创建图（如果不存在）
echo "Creating LightRAG graph..."
if su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -tAc \"SELECT 1 FROM ag_catalog.ag_graph WHERE name='lightrag'\"" | grep -q 1; then
    echo "Graph 'lightrag' already exists"
else
    su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"SELECT ag_catalog.create_graph('lightrag');\""
    echo "Graph 'lightrag' created successfully"
fi

echo "Creating LightRAG application tables..."

# 创建 LightRAG 需要的基础表
echo "Creating lightrag_kv_store table..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
CREATE TABLE IF NOT EXISTS lightrag_kv_store (
    key VARCHAR PRIMARY KEY,
    value JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
\""

echo "Creating lightrag_doc_status table..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
CREATE TABLE IF NOT EXISTS lightrag_doc_status (
    doc_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
\""

echo "Creating indexes for performance optimization..."

# 为应用表创建索引
echo "Creating KV store indexes..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lightrag_kv_store_updated_at ON lightrag_kv_store(updated_at);
\""

echo "Creating doc status indexes..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lightrag_doc_status_status ON lightrag_doc_status(status);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_lightrag_doc_status_updated_at ON lightrag_doc_status(updated_at);
\""

# 等待图表创建完成后创建 AGE 相关索引
echo "Waiting for graph tables to be fully initialized..."
sleep 5

echo "Creating AGE performance indexes..."

# 检查并创建 Entity 表索引
echo "Creating Entity table indexes..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
DO \$\$
BEGIN
    -- Entity 表索引
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'lightrag' AND table_name = 'Entity') THEN
        PERFORM 1;
        -- 主键索引通常自动创建，这里创建其他有用的索引
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = 'Entity' AND indexname = 'entity_node_id_gin_idx') THEN
            CREATE INDEX CONCURRENTLY entity_node_id_gin_idx ON lightrag.\\\"Entity\\\" USING gin(properties);
        END IF;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Entity table not ready yet, skipping indexes';
END
\$\$;
\""

# 检查并创建 DIRECTED 关系表索引
echo "Creating DIRECTED relationship indexes..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
DO \$\$
BEGIN
    -- DIRECTED 关系表索引
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'lightrag' AND table_name = 'DIRECTED') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = 'DIRECTED' AND indexname = 'directed_eid_idx') THEN
            CREATE INDEX CONCURRENTLY directed_eid_idx ON lightrag.\\\"DIRECTED\\\" (end_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = 'DIRECTED' AND indexname = 'directed_sid_idx') THEN
            CREATE INDEX CONCURRENTLY directed_sid_idx ON lightrag.\\\"DIRECTED\\\" (start_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = 'DIRECTED' AND indexname = 'directed_seid_idx') THEN
            CREATE INDEX CONCURRENTLY directed_seid_idx ON lightrag.\\\"DIRECTED\\\" (start_id, end_id);
        END IF;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'DIRECTED table not ready yet, skipping indexes';
END
\$\$;
\""

# 检查并创建 Edge 表索引
echo "Creating Edge table indexes..."
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
DO \$\$
BEGIN
    -- Edge 表索引
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'lightrag' AND table_name = '_ag_label_edge') THEN
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = '_ag_label_edge' AND indexname = 'edge_sid_idx') THEN
            CREATE INDEX CONCURRENTLY edge_sid_idx ON lightrag.\\\"_ag_label_edge\\\" (start_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = '_ag_label_edge' AND indexname = 'edge_eid_idx') THEN
            CREATE INDEX CONCURRENTLY edge_eid_idx ON lightrag.\\\"_ag_label_edge\\\" (end_id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'lightrag' AND tablename = '_ag_label_edge' AND indexname = 'edge_seid_idx') THEN
            CREATE INDEX CONCURRENTLY edge_seid_idx ON lightrag.\\\"_ag_label_edge\\\" (start_id, end_id);
        END IF;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Edge table not ready yet, skipping indexes';
END
\$\$;
\""

echo "Setting up permissions..."

# 授权给 lightrag 用户
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ${POSTGRES_USER:-lightrag};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ${POSTGRES_USER:-lightrag};
GRANT ALL PRIVILEGES ON ALL FUNCTIONS IN SCHEMA public TO ${POSTGRES_USER:-lightrag};
GRANT USAGE ON SCHEMA public TO ${POSTGRES_USER:-lightrag};
\""

# 为 AGE 图授权
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
GRANT ALL PRIVILEGES ON SCHEMA lightrag TO ${POSTGRES_USER:-lightrag};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA lightrag TO ${POSTGRES_USER:-lightrag};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA lightrag TO ${POSTGRES_USER:-lightrag};
GRANT USAGE ON SCHEMA lightrag TO ${POSTGRES_USER:-lightrag};
\""

echo "Applying PostgreSQL performance configuration..."

# 应用性能配置
su - postgres -c "psql -c \"ALTER SYSTEM SET shared_preload_libraries = 'age';\""
su - postgres -c "psql -c \"ALTER SYSTEM SET max_connections = 200;\""
su - postgres -c "psql -c \"ALTER SYSTEM SET shared_buffers = '256MB';\""
su - postgres -c "psql -c \"ALTER SYSTEM SET effective_cache_size = '1GB';\""
su - postgres -c "psql -c \"ALTER SYSTEM SET maintenance_work_mem = '64MB';\""
su - postgres -c "psql -c \"ALTER SYSTEM SET random_page_cost = 1.1;\""
su - postgres -c "psql -c \"ALTER SYSTEM SET effective_io_concurrency = 200;\""
su - postgres -c "psql -c \"ALTER SYSTEM SET work_mem = '4MB';\""

# 启用查询计划缓存
su - postgres -c "psql -c \"ALTER SYSTEM SET plan_cache_mode = 'auto';\""

# 重新加载配置
su - postgres -c "psql -c \"SELECT pg_reload_conf();\""

echo "Restarting PostgreSQL to apply configuration changes..."
service postgresql restart
sleep 5

echo "Verifying setup..."

# 验证扩展
echo "Installed extensions:"
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"\\dx\""

# 验证图
echo "Available graphs:"
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"SELECT name FROM ag_catalog.ag_graph;\""

# 验证表
echo "Created tables:"
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname IN ('public', 'lightrag')
ORDER BY schemaname, tablename;
\""

# 验证索引
echo "Created indexes:"
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname IN ('public', 'lightrag')
ORDER BY schemaname, tablename, indexname;
\""

# 测试连接
echo "Testing database connection..."
export PGPASSWORD="${POSTGRES_PASSWORD:-lightrag}"
if PGPASSWORD="${POSTGRES_PASSWORD:-lightrag}" psql -h localhost -p 5432 -U ${POSTGRES_USER:-lightrag} -d ${POSTGRES_DATABASE:-lightrag} -c "SELECT version();" > /dev/null 2>&1; then
    echo "✅ Database connection test successful!"
else
    echo "❌ Database connection test failed!"
    echo "Checking pg_hba.conf..."
    cat $PG_HBA_CONF | head -20
    echo "Checking PostgreSQL logs..."
    tail -20 /var/log/postgresql/postgresql-16-main.log
fi

echo "✅ PostgreSQL setup completed successfully!"
echo "Database: ${POSTGRES_DATABASE:-lightrag}"
echo "User: ${POSTGRES_USER:-lightrag}"
echo "Extensions: vector, age"
echo "Graph: lightrag"
echo "Tables: lightrag_kv_store, lightrag_doc_status + AGE graph tables"
echo "Connection: postgresql://${POSTGRES_USER:-lightrag}:***@localhost:5432/${POSTGRES_DATABASE:-lightrag}"

# 显示数据库统计信息
echo "Database statistics:"
su - postgres -c "psql -d ${POSTGRES_DATABASE:-lightrag} -c \"
SELECT
    schemaname,
    COUNT(*) as table_count
FROM pg_tables
WHERE schemaname IN ('public', 'lightrag')
GROUP BY schemaname;
\""

# 保持容器运行并显示日志
echo "PostgreSQL is ready for connections on port 5432"
tail -f /var/log/postgresql/postgresql-16-main.log