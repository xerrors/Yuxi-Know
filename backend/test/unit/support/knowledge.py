from types import SimpleNamespace

from yuxi.modules.knowledge.base import KnowledgeBase


class FakeKnowledgeBase(KnowledgeBase):
    """提供不依赖外部服务的知识库实现。"""

    @property
    def kb_type(self) -> str:
        """返回该替身的固定类型标识。"""
        return "fake"

    async def _create_kb_instance(self, kb_id: str, embedding_model_spec: str | None):
        """该替身不创建外部客户端。"""
        return None

    async def _initialize_kb_instance(self, instance) -> None:
        """该替身不初始化外部客户端。"""
        pass

    async def index_file(self, kb_id: str, file_id: str, operator_id: str | None = None) -> dict:
        """该替身不执行索引。"""
        return {}

    async def aquery(self, query_text: str, kb_id: str, **kwargs) -> list[dict]:
        """该替身返回空查询结果。"""
        return []

    def get_query_params_config(self, kb_id: str, **kwargs) -> dict:
        """提供管理器构造查询配置所需的最小值。"""
        return {"options": []}

    async def delete_file(self, kb_id: str, file_id: str) -> None:
        """该替身不执行文件删除。"""
        pass

    async def get_file_basic_info(self, kb_id: str, file_id: str) -> dict:
        """该替身不读取文件元数据。"""
        return {}

    async def get_file_content(self, kb_id: str, file_id: str) -> dict:
        """该替身不读取文件内容。"""
        return {}

    async def get_file_info(self, kb_id: str, file_id: str) -> dict:
        """该替身不读取文件元数据。"""
        return {}


def make_knowledge_file_record(**overrides) -> SimpleNamespace:
    """创建带知识文件公共字段的记录替身。"""
    values = {
        "file_id": "file-1",
        "kb_id": "db",
        "parent_id": None,
        "filename": "demo.md",
        "file_type": "md",
        "path": "minio://knowledgebases/db/upload/demo.md",
        "minio_url": None,
        "markdown_file": None,
        "status": "uploaded",
        "content_hash": "hash",
        "file_size": 123,
        "chunk_count": 0,
        "token_count": 0,
        "content_type": "file",
        "processing_params": {"ocr_engine": "disable"},
        "is_folder": False,
        "error_message": None,
        "created_by": "user",
        "updated_by": None,
        "created_at": None,
        "updated_at": None,
        "original_filename": None,
        "generation": 1,
        "active_generation": 1,
        "building_generation": None,
        "deleted_at": None,
        "projection_status": "pending",
        "projection_error": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)
