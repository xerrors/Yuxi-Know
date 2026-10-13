"""附件归属、准备状态与存储位置。"""

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text

from yuxi.infrastructure.postgres.base import BusinessBase
from yuxi.shared.datetime import utc_now


class AgentAttachment(BusinessBase):
    """文件内容留在存储边界，附件事实只保存在本表。"""

    __tablename__ = "agent_attachments"

    id = Column(String(32), primary_key=True)
    uid = Column(String(128), nullable=False)
    app_id = Column(String(64), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(255), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False, default="draft")
    input_id = Column(String(64), ForeignKey("agent_inputs.id", ondelete="CASCADE"), nullable=True, index=True)
    message_id = Column(Integer, nullable=True, index=True)
    object_name = Column(Text, nullable=True)
    parsed_source = Column(Text, nullable=True)
    parse_method = Column(String(32), nullable=True)
    path = Column(Text, nullable=True)
    original_path = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["message_id", "input_id"],
            ["messages.id", "messages.source_input_id"],
            name="fk_agent_attachments_message_origin",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_agent_attachments_size"),
        CheckConstraint(
            "(status = 'draft' AND input_id IS NULL AND message_id IS NULL AND object_name IS NOT NULL) "
            "OR (status = 'preparing' AND input_id IS NOT NULL "
            "AND message_id IS NULL AND object_name IS NOT NULL) "
            "OR (status = 'ready' AND input_id IS NOT NULL "
            "AND path IS NOT NULL AND original_path IS NOT NULL)",
            name="ck_agent_attachments_preparation",
        ),
        Index("ix_agent_attachments_expired_drafts", "uid", "app_id", "status", "expires_at"),
    )
