"""用户评价与 Agent 改进线索的持久约束。"""

import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, text

from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import format_utc_datetime, utc_now


class AgentFeedbackRecord(Base):
    """保存明确 Run 上的当前用户评价或工具标记。"""

    __tablename__ = "agent_feedback_records"

    id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(64), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(16), nullable=False)
    rating = Column(String(16), nullable=True)
    reason = Column(Text, nullable=True)
    tool_call_id = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    __table_args__ = (
        CheckConstraint(
            "(source = 'user' AND rating IS NOT NULL AND rating IN ('like','dislike') "
            "AND tool_call_id IS NULL AND (reason IS NULL OR length(reason) <= 2000)) OR "
            "(source = 'agent' AND rating IS NULL AND reason IS NOT NULL "
            "AND length(trim(reason)) BETWEEN 1 AND 4000 "
            "AND tool_call_id IS NOT NULL AND length(trim(tool_call_id)) > 0)",
            name="ck_agent_feedback_source_shape",
        ),
        Index(
            "uq_agent_feedback_user_run",
            "run_id",
            unique=True,
            postgresql_where=text("source = 'user'"),
            sqlite_where=text("source = 'user'"),
        ),
        Index(
            "uq_agent_feedback_tool_call",
            "run_id",
            "tool_call_id",
            unique=True,
            postgresql_where=text("source = 'agent'"),
            sqlite_where=text("source = 'agent'"),
        ),
        Index("ix_agent_feedback_page", "created_at", "id"),
    )

    def to_dict(self) -> dict:
        """投影反馈正文，不复制执行身份或资源清单。"""
        return {
            "id": self.id,
            "run_id": self.run_id,
            "source": self.source,
            "rating": self.rating,
            "reason": self.reason,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
