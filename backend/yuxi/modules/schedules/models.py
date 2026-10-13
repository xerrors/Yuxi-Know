"""业务 PostgreSQL 映射。"""

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)

from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import format_utc_datetime, utc_now


class ScheduledAgentJob(Base):
    """用户自建 Agent 定时任务。"""

    __tablename__ = "scheduled_agent_jobs"
    __table_args__ = (
        UniqueConstraint(
            "uid",
            "creation_request_id",
            name="uq_scheduled_agent_jobs_uid_creation_request",
        ),
        ForeignKeyConstraint(
            ["project_id", "uid"],
            ["projects.id", "projects.uid"],
            name="fk_scheduled_agent_jobs_project_uid",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "tool_approval_mode IN ('default', 'always_trust')",
            name="ck_scheduled_agent_jobs_tool_approval_mode",
        ),
    )

    id = Column(String(64), primary_key=True)
    uid = Column(String(128), ForeignKey("users.uid", ondelete="CASCADE"), nullable=False, index=True)
    creation_request_id = Column(String(64), nullable=False)
    creation_intent_hash = Column(String(64), nullable=False)
    project_id = Column(String(64), nullable=False, index=True)
    agent_slug = Column(String(64), nullable=False)
    name = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    tool_approval_mode = Column(String(32), nullable=False, default="default")
    model_spec = Column(String(512), nullable=True)
    cron_expression = Column(String(100), nullable=False)
    timezone = Column(String(64), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    next_run_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "uid": self.uid,
            "project_id": self.project_id,
            "agent_slug": self.agent_slug,
            "name": self.name,
            "prompt": self.prompt,
            "tool_approval_mode": self.tool_approval_mode,
            "model_spec": self.model_spec,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "enabled": bool(self.enabled),
            "deleted_at": format_utc_datetime(self.deleted_at),
            "next_run_at": format_utc_datetime(self.next_run_at),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class ScheduledAgentRun(Base):
    """一次定时或手动触发意图，保存配置快照并关联统一 Input。"""

    __tablename__ = "scheduled_agent_runs"
    __table_args__ = (
        UniqueConstraint("job_id", "occurrence_key", name="uq_scheduled_agent_runs_job_occurrence"),
        UniqueConstraint("input_id", name="uq_scheduled_agent_runs_input"),
        UniqueConstraint("thread_id", name="uq_scheduled_agent_runs_thread"),
        Index("ix_scheduled_agent_runs_job_created", "job_id", "created_at"),
        Index("ix_scheduled_agent_runs_dispatching", "status", "created_at"),
    )

    id = Column(String(64), primary_key=True)
    job_id = Column(
        String(64),
        ForeignKey("scheduled_agent_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_id = Column(String(64), nullable=False)
    thread_id = Column(String(64), nullable=False)
    trigger = Column(String(16), nullable=False, default="scheduled")
    occurrence_key = Column(String(128), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    project_id = Column(String(64), nullable=False)
    agent_slug = Column(String(64), nullable=False)
    session_title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    tool_approval_mode = Column(String(32), nullable=False)
    model_spec = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="dispatching")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "input_id": self.input_id,
            "thread_id": self.thread_id,
            "trigger": self.trigger,
            "scheduled_for": format_utc_datetime(self.scheduled_for),
            "status": self.status,
            "run_id": None,
            "error_message": self.error_message,
            "created_at": format_utc_datetime(self.created_at),
            "completed_at": None,
        }
