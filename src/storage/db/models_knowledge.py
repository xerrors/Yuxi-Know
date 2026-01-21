from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

from src.storage.db.models import Base
from src.utils.datetime_utils import utc_now

JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (UniqueConstraint("db_id", name="uq_knowledge_bases_db_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    db_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    kb_type = Column(String(32), nullable=False, index=True)
    embed_info = Column(JSON_VALUE)
    llm_info = Column(JSON_VALUE)
    query_params = Column(JSON_VALUE)
    additional_params = Column(JSON_VALUE)
    share_config = Column(JSON_VALUE)
    mindmap = Column(JSON_VALUE)
    sample_questions = Column(JSON_VALUE)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"
    __table_args__ = (UniqueConstraint("file_id", name="uq_knowledge_files_file_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(64), unique=True, nullable=False, index=True)
    db_id = Column(String(64), ForeignKey("knowledge_bases.db_id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(64), ForeignKey("knowledge_files.file_id", ondelete="SET NULL"), index=True)
    filename = Column(String(512), nullable=False)
    original_filename = Column(String(512))
    file_type = Column(String(64))
    path = Column(String(1024))
    minio_url = Column(String(1024))
    markdown_file = Column(String(1024))
    status = Column(String(32), default="uploaded", index=True)
    content_hash = Column(String(128), index=True)
    file_size = Column(BigInteger)
    content_type = Column(String(64))
    processing_params = Column(JSON_VALUE)
    is_folder = Column(Boolean, default=False)
    error_message = Column(Text)
    created_by = Column(String(64))
    updated_by = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class EvaluationBenchmark(Base):
    __tablename__ = "evaluation_benchmarks"
    __table_args__ = (UniqueConstraint("benchmark_id", name="uq_evaluation_benchmarks_benchmark_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    benchmark_id = Column(String(64), unique=True, nullable=False, index=True)
    db_id = Column(String(64), ForeignKey("knowledge_bases.db_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    question_count = Column(Integer, default=0)
    has_gold_chunks = Column(Boolean, default=False)
    has_gold_answers = Column(Boolean, default=False)
    data_file_path = Column(String(1024))
    created_by = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (UniqueConstraint("task_id", name="uq_evaluation_results_task_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    db_id = Column(String(64), ForeignKey("knowledge_bases.db_id", ondelete="CASCADE"), nullable=False, index=True)
    benchmark_id = Column(
        String(64),
        ForeignKey("evaluation_benchmarks.benchmark_id", ondelete="SET NULL"),
        index=True,
    )
    status = Column(String(32), default="running", index=True)
    retrieval_config = Column(JSON_VALUE)
    metrics = Column(JSON_VALUE)
    overall_score = Column(Float)
    total_questions = Column(Integer, default=0)
    completed_questions = Column(Integer, default=0)
    started_at = Column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(String(64))


class EvaluationResultDetail(Base):
    __tablename__ = "evaluation_result_details"
    __table_args__ = (UniqueConstraint("task_id", "query_index", name="uq_evaluation_result_details_task_query"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        String(64),
        ForeignKey("evaluation_results.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_index = Column(Integer, nullable=False)
    query_text = Column(Text, nullable=False)
    gold_chunk_ids = Column(JSON_VALUE)
    gold_answer = Column(Text)
    generated_answer = Column(Text)
    retrieved_chunks = Column(JSON_VALUE)
    metrics = Column(JSON_VALUE)
