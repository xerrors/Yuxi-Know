import os


def postgres_dsn() -> str:
    """返回 asyncpg 使用的 PostgreSQL DSN。"""
    return os.getenv("POSTGRES_URL", "postgresql+asyncpg://postgres:postgres@postgres:5432/yuxi").replace("+asyncpg", "")
