"""业务 PostgreSQL 映射。"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

from yuxi.infrastructure.postgres.base import JSON_VALUE
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import utc_now


class AgentTurn(Base):
    """线程内一轮工作的状态、当前执行和最终结果。"""

    __tablename__ = "agent_turns"

    id = Column(String(64), primary_key=True)
    thread_id = Column(String(64), ForeignKey("sessions.thread_id", ondelete="CASCADE"), nullable=False, index=True)
    uid = Column(String(128), nullable=False, index=True)
    app_id = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="running")
    next_output_index = Column(Integer, nullable=False, default=0, server_default="0")
    current_run_id = Column(String(64), nullable=True)
    result_run_id = Column(String(64), nullable=True)
    langfuse_root_observation_id = Column(String(16), nullable=True)
    waitpoint = Column(JSON_VALUE, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "uq_agent_turns_active",
            "thread_id",
            unique=True,
            postgresql_where=status.in_(("running", "waiting", "cancelling")),
        ).ddl_if(dialect="postgresql"),
        UniqueConstraint("id", "thread_id", name="uq_agent_turns_id_thread"),
        CheckConstraint(
            "status IN ('running', 'waiting', 'cancelling', 'completed', 'failed', 'cancelled')",
            name="ck_agent_turns_status",
        ),
        ForeignKeyConstraint(
            ["id", "current_run_id"],
            ["agent_runs.turn_id", "agent_runs.id"],
            name="fk_agent_turns_current_run",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["id", "result_run_id"],
            ["agent_runs.turn_id", "agent_runs.id"],
            name="fk_agent_turns_result_run",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )
