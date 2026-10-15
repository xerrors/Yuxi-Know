"""会话协作的持久通知与消息。"""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from yuxi.infrastructure.postgres.base import JSON_VALUE
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import utc_now


class CooperationEvent(Base):
    """保存树内消息及精确绑定 Turn 的状态通知。"""

    __tablename__ = "session_cooperation_events"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tree_root_thread_id = Column(String(64), ForeignKey("sessions.thread_id"), nullable=False, index=True)
    sender_thread_id = Column(String(64), ForeignKey("sessions.thread_id"), nullable=False, index=True)
    recipient_thread_id = Column(String(64), ForeignKey("sessions.thread_id"), nullable=False, index=True)
    source_run_id = Column(String(64), ForeignKey("agent_runs.id"), nullable=True)
    turn_id = Column(String(64), ForeignKey("agent_turns.id"), nullable=True)
    kind = Column(String(32), nullable=False)
    content = Column(Text, nullable=False, default="")
    payload = Column(JSON_VALUE, nullable=False, default=dict)
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    __table_args__ = (UniqueConstraint("recipient_thread_id", "idempotency_key", name="uq_cooperation_recipient_key"),)


class CooperationRuntime(Base):
    """拥有协作树停止状态，独立于用户 VM 生命周期。"""

    __tablename__ = "session_cooperation_runtimes"
    tree_root_thread_id = Column(String(64), ForeignKey("sessions.thread_id"), primary_key=True)
    stopped = Column(Boolean, nullable=False, default=False)
