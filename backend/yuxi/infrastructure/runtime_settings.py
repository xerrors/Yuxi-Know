"""进程环境变量与运行目录配置。"""

import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def get_public_url() -> str:
    """读取部署固定的公开站点来源，不接受路径或请求头推导。"""
    value = os.getenv("YUXI_PUBLIC_URL", "")
    parsed = urlsplit(value)
    _ = parsed.port
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or any(c.isspace() for c in value)
    ):
        raise ValueError("YUXI_PUBLIC_URL 必须为公开站点来源，不含路径、查询参数或凭据")
    return f"{parsed.scheme}://{parsed.netloc}"


def get_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """读取有下界的整数环境变量，配置非法时显式失败。"""
    raw_value = os.getenv(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw_value!r}") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {value}")
    return value


def get_runtime_dir() -> Path:
    """读取可丢弃日志与缓存使用的当前进程运行目录。"""
    configured = os.getenv("YUXI_RUNTIME_DIR")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / f"yuxi-runtime-{os.getpid()}"


def get_skill_data_dir() -> Path:
    """读取共享与个人 Skill 持久源目录。"""
    configured = os.getenv("YUXI_SKILL_DATA_DIR")
    return Path(configured) if configured else Path("skill-sources")


def get_skill_projection_dir() -> Path:
    """读取用户授权 Skill 只读投影目录。"""
    configured = os.getenv("YUXI_SKILL_PROJECTION_DIR")
    return Path(configured) if configured else Path("skill-projections")


def get_user_data_dir() -> Path:
    """读取用户级实时文件持久目录。"""
    return Path(os.getenv("YUXI_USER_DATA_DIR", "user-data"))
