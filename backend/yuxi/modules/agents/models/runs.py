"""业务 PostgreSQL 映射。"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    UniqueConstraint,
)

from yuxi.infrastructure.postgres.base import JSON_VALUE
from yuxi.infrastructure.postgres.base import BusinessBase as Base
from yuxi.shared.datetime import duration_ms, format_utc_datetime, utc_now

AGENT_RUN_TERMINAL_STATUSES = ("completed", "failed", "cancelled", "interrupted", "yielded")


AGENT_RUN_SHAPE_CONSTRAINT_NAME = "ck_agent_runs_nonterminal_shape"


AGENT_RUN_SHAPE_CONSTRAINT_SQL = """
    runtime_scope_id <> '' AND thread_id <> ''
 AND (run_type = 'chat' OR (run_type = 'resume' AND resume_from_run_id IS NOT NULL))
"""


def build_agent_run_timing(
    *,
    created_at: datetime | None,
    started_at: datetime | None,
    prepared_at: datetime | None,
    first_output_at: datetime | None,
    finished_at: datetime | None,
    first_model_request_at: datetime | None = None,
) -> dict[str, Any]:
    """从 AgentRun 权威时间点生成统一的阶段时延投影。"""
    return {
        "created_at": format_utc_datetime(created_at),
        "started_at": format_utc_datetime(started_at),
        "prepared_at": format_utc_datetime(prepared_at),
        "first_model_request_at": format_utc_datetime(first_model_request_at),
        "first_output_at": format_utc_datetime(first_output_at),
        "finished_at": format_utc_datetime(finished_at),
        "dispatch_latency_ms": duration_ms(created_at, started_at),
        "preparation_latency_ms": duration_ms(started_at, prepared_at),
        "first_model_request_latency_ms": duration_ms(created_at, first_model_request_at),
        "model_first_output_latency_ms": duration_ms(prepared_at, first_output_at),
        "first_output_latency_ms": duration_ms(created_at, first_output_at),
        "total_latency_ms": duration_ms(created_at, finished_at),
    }


class AgentRun(Base):
    """保存 Turn 内一段执行及其独立结果。"""

    __tablename__ = "agent_runs"

    id = Column(String(64), primary_key=True, comment="Run ID (UUID)")
    execution_seq = Column(
        BigInteger,
        Sequence("agent_runs_execution_seq"),
        nullable=False,
        comment="跨 Run 订阅的持久执行顺序",
    )
    thread_id = Column(String(64), index=True, nullable=False, comment="Session thread ID snapshot")
    runtime_scope_id = Column(String(64), index=True, nullable=False, comment="Owning Thread runtime scope")
    runtime_cleanup_pending = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
        comment="Terminal Run still owns its runtime cleanup",
    )
    agent_slug = Column(String(64), index=True, nullable=False, comment="Agent slug")
    uid = Column(String(128), index=True, nullable=False, comment="UID")
    status = Column(
        String(32),
        index=True,
        nullable=False,
        default="pending",
        comment="Run status: pending/running/completed/failed/cancel_requested/cancelled/interrupted/yielded",
    )
    turn_id = Column(String(64), ForeignKey("agent_turns.id", name="fk_agent_runs_turn"), nullable=False, index=True)
    app_id = Column(String(64), nullable=True, index=True, comment="API Key 来源快照")
    api_key_id = Column(Integer, nullable=True, index=True, comment="发起调用的 API Key ID 快照")
    source = Column(String(32), nullable=False, default="chat", comment="Run source snapshot")
    channel = Column(String(32), nullable=False, default="web", comment="Run channel snapshot")
    external_id = Column(String(128), nullable=True, index=True, comment="Source-specific external ID snapshot")
    origin_metadata = Column(JSON, nullable=False, default=dict, comment="Immutable origin metadata snapshot")
    session_record_id = Column(Integer, ForeignKey("sessions.id"), nullable=True, index=True, comment="Session ID")
    created_by_run_id = Column(String(64), ForeignKey("agent_runs.id"), nullable=True, index=True, comment="Run that created this run")
    resume_from_run_id = Column(String(64), ForeignKey("agent_runs.id"), nullable=True)
    run_type = Column(
        String(32),
        nullable=False,
        default="chat",
        comment="Run type: chat/resume",
    )
    input_message_id = Column(Integer, nullable=True, comment="Input message ID")
    output_message_id = Column(Integer, nullable=True, comment="Output message ID")
    input_payload = Column(JSON, nullable=False, default=dict, comment="Original input payload")
    token_usage = Column(JSON_VALUE, nullable=False, default=dict, comment="Run token usage grouped by model")
    langfuse_trace_id = Column(String(64), nullable=True, comment="Langfuse trace ID")
    langfuse_observation_id = Column(String(16), nullable=True, comment="本 Run 的 Langfuse observation ID")
    error_type = Column(String(64), nullable=True, comment="Error type")
    error_message = Column(Text, nullable=True, comment="Error message")
    worker_id = Column(String(128), nullable=True, comment="稳定 worker identity 与 attempt UUID 组成的 owner token")
    heartbeat_at = Column(DateTime(timezone=True), nullable=True, comment="当前 owner 最近一次成功续租时间")
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, comment="当前执行 ownership 的到期时间")
    manifest = Column(
        JSON_VALUE,
        nullable=True,
        comment="首次执行前固化的运行清单（脱敏）；NULL 表示历史 Run 未知，不从当前配置反推",
    )
    manifest_fingerprint = Column(String(64), nullable=True, comment="运行清单规范化 JSON 的 SHA-256 指纹")
    manifest_recorded_at = Column(DateTime(timezone=True), nullable=True, comment="运行清单固化时间")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="Start time")
    prepared_at = Column(DateTime(timezone=True), nullable=True, comment="当前 Run 首次完成模型调用前准备的时间")
    first_model_request_at = Column(DateTime(timezone=True), nullable=True, comment="当前 Run 首次进入模型供应商请求前的时间")
    first_output_at = Column(DateTime(timezone=True), nullable=True, comment="当前 Run 首次产生非空模型语义输出的时间")
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="Finish time")
    created_at = Column(DateTime(timezone=True), default=utc_now, comment="Creation time")
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="Update time")

    __table_args__ = (
        ForeignKeyConstraint(
            ["session_record_id", "thread_id", "runtime_scope_id"],
            ["sessions.id", "sessions.thread_id", "sessions.tree_root_thread_id"],
            name="fk_agent_runs_session_runtime_scope",
        ),
        UniqueConstraint("turn_id", "id", name="uq_agent_runs_turn_id_id"),
        Index("ix_agent_runs_turn_execution", "turn_id", "execution_seq", "id"),
        CheckConstraint(
            "status IN ('pending','running','cancel_requested','completed','failed','cancelled','interrupted','yielded')",
            name="ck_agent_runs_status",
        ),
        UniqueConstraint("id", "turn_id", "session_record_id", name="uq_agent_runs_id_turn_session"),
        ForeignKeyConstraint(
            ["session_record_id", "thread_id"],
            ["sessions.id", "sessions.thread_id"],
            name="fk_agent_runs_session_thread",
        ),
        CheckConstraint(
            "(input_message_id IS NULL AND output_message_id IS NULL) OR session_record_id IS NOT NULL",
            name="ck_agent_runs_message_thread_required",
        ),
        ForeignKeyConstraint(
            ["input_message_id", "id", "turn_id", "session_record_id"],
            ["messages.id", "messages.run_id", "messages.turn_id", "messages.session_record_id"],
            name="fk_agent_runs_input_message_scope",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["output_message_id", "id", "turn_id", "session_record_id"],
            ["messages.id", "messages.run_id", "messages.turn_id", "messages.session_record_id"],
            name="fk_agent_runs_output_message_scope",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["turn_id", "thread_id"],
            ["agent_turns.id", "agent_turns.thread_id"],
            name="fk_agent_runs_owning_turn_thread",
        ),
        ForeignKeyConstraint(
            ["turn_id", "resume_from_run_id"],
            ["agent_runs.turn_id", "agent_runs.id"],
            name="fk_agent_runs_resume_same_turn",
            use_alter=True,
        ),
        CheckConstraint(
            AGENT_RUN_SHAPE_CONSTRAINT_SQL,
            name=AGENT_RUN_SHAPE_CONSTRAINT_NAME,
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "execution_seq": self.execution_seq,
            "thread_id": self.thread_id,
            "runtime_scope_id": self.runtime_scope_id,
            "runtime_cleanup_pending": bool(self.runtime_cleanup_pending),
            "agent_slug": self.agent_slug,
            "uid": self.uid,
            "status": self.status,
            "turn_id": self.turn_id,
            "app_id": self.app_id,
            "api_key_id": self.api_key_id,
            "source": self.source,
            "channel": self.channel,
            "external_id": self.external_id,
            "origin_metadata": self.origin_metadata or {},
            "session_record_id": self.session_record_id,
            "created_by_run_id": self.created_by_run_id,
            "resume_from_run_id": self.resume_from_run_id,
            "run_type": self.run_type,
            "input_message_id": self.input_message_id,
            "output_message_id": self.output_message_id,
            "input_payload": self.input_payload or {},
            "token_usage": self.token_usage or {},
            "langfuse_trace_id": self.langfuse_trace_id,
            "langfuse_observation_id": self.langfuse_observation_id,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "manifest": self.manifest,
            "manifest_fingerprint": self.manifest_fingerprint,
            "started_at": format_utc_datetime(self.started_at),
            "prepared_at": format_utc_datetime(self.prepared_at),
            "first_model_request_at": format_utc_datetime(self.first_model_request_at),
            "first_output_at": format_utc_datetime(self.first_output_at),
            "finished_at": format_utc_datetime(self.finished_at),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
            "timing": build_agent_run_timing(
                created_at=self.created_at,
                started_at=self.started_at,
                prepared_at=self.prepared_at,
                first_output_at=self.first_output_at,
                finished_at=self.finished_at,
                first_model_request_at=self.first_model_request_at,
            ),
        }


class AgentRunAttempt(Base):
    """AgentRunAttempt table - 单次执行占有的不可变事实记录。

    每当 worker 取得 Run 执行所有权时创建一条记录，(run_id, attempt_no) 唯一约束
    保证同一 Run 内序号唯一。终止事实（outcome/error/finished_at）写入后不得改写；
    AgentRun 保存面向业务查询的聚合状态，本表是执行历史与失败事实的 Owner。
    """

    __tablename__ = "agent_run_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Primary key")
    run_id = Column(
        String(64),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owning run ID（组合索引以 run_id 开头，无需独立索引）",
    )
    attempt_no = Column(Integer, nullable=False, comment="Run 内递增的执行序号")
    worker_id = Column(String(128), nullable=False, comment="取得执行所有权的 owner token")
    started_at = Column(DateTime(timezone=True), nullable=False, comment="取得执行所有权时间")
    heartbeat_at = Column(DateTime(timezone=True), nullable=True, comment="本 attempt 最近一次续租时间")
    lease_expires_at = Column(DateTime(timezone=True), nullable=True, comment="本 attempt 最近一次租约到期时间")
    finished_at = Column(DateTime(timezone=True), nullable=True, comment="执行占有结束时间；NULL 表示仍开放")
    outcome = Column(
        String(32),
        nullable=True,
        comment="终止事实: completed/failed/cancelled/interrupted/retry_released/lease_expired",
    )
    error_type = Column(String(64), nullable=True, comment="失败时的结构化错误分类")
    error_message = Column(Text, nullable=True, comment="失败时的错误摘要")
    created_at = Column(DateTime(timezone=True), default=utc_now, comment="Creation time")
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, comment="Update time")

    __table_args__ = (
        UniqueConstraint("run_id", "attempt_no", name="uq_agent_run_attempts_run_attempt_no"),
        Index("ix_agent_run_attempts_open", "run_id", "finished_at"),
        Index(
            "uq_agent_run_attempts_one_open",
            "run_id",
            unique=True,
            postgresql_where=finished_at.is_(None),
            sqlite_where=finished_at.is_(None),
        ),
    )
