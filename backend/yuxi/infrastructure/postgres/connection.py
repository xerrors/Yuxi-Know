"""PostgreSQL 原生消费者的连接串适配。"""


def postgres_conninfo(db_url: str) -> str:
    """只移除 SQLAlchemy 驱动前缀，保留凭据和查询值。"""
    raw = db_url.strip()
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://"):
        if raw.startswith(prefix):
            return "postgresql://" + raw[len(prefix) :]
    return raw
