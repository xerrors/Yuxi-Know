"""用户环境及待清理命令的持久事实。"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import utc_now


class UserSandbox(Base):
    """一个用户拥有一个环境，代次只在显式重建时改变。"""

    __tablename__ = "user_sandboxes"
    uid = Column(String(128), primary_key=True)
    generation = Column(Integer, nullable=False, default=1)
    sandbox_id = Column(String(128), nullable=True)
    traffic_token = Column(Text, nullable=False, default="")
    envd_token = Column(Text, nullable=False)
    state = Column(String(32), nullable=False, default="creating")
    operation_id = Column(String(64), nullable=False)
    last_active_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)


class SandboxCommand(Base):
    """命令终止被确认前保留句柄，不依赖 worker 内存。"""

    __tablename__ = "sandbox_commands"
    id = Column(String(64), primary_key=True)
    uid = Column(String(128), ForeignKey("user_sandboxes.uid"), nullable=False, index=True)
    generation = Column(Integer, nullable=False)
    run_id = Column(String(64), nullable=True, index=True)
    owner = Column(String(128), nullable=True)
    kind = Column(String(16), nullable=False)
    pgid = Column(Integer, nullable=True)
    phase = Column(String(16), nullable=False, default="starting")
    deadline = Column(DateTime(timezone=True), nullable=False)
