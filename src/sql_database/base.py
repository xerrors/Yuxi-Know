import os, json
import time
import shutil
import tempfile
from abc import ABC, abstractmethod
from typing import Any
from src.utils import logger, hashstr
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat

class DnowledgeBaseException(Exception):
    """数据库库统一异常基类"""

    pass


class DBNotFoundError(DnowledgeBaseException):
    """数据库库不存在错误"""

    pass


class DBOperationError(DnowledgeBaseException):
    """数据库库操作错误"""

    pass


class ConnectorBase(ABC):
    """知识库抽象基类，定义统一接口"""

    # 类级别的处理队列，跟踪所有正在处理的文件
    _processing_files = set()
    _processing_lock = None

    def __init__(self, work_dir: str):
        """
        初始化知识库

        Args:
            work_dir: 工作目录
        """
        import threading

        self.work_dir = work_dir
        self.databases_meta: dict[str, dict] = {}
        self.tables_meta: dict[str, dict] = {}
        self.selected_tables_meta: dict[str, dict] = {}
        # self.topk: int = 5
        # self.similarity_threshold: float = 0.2

        # 初始化类级别的锁
        if ConnectorBase._processing_lock is None:
            ConnectorBase._processing_lock = threading.Lock()

        os.makedirs(work_dir, exist_ok=True)

        # 自动加载元数据
        self._load_metadata()
        self._normalize_metadata_state()

    def _load_metadata(self):
        """加载元数据"""
        meta_file = os.path.join(self.work_dir, f"metadata_{self.db_type}.json")

        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.databases_meta = data.get("databases", {})
                    self.tables_meta = data.get("tables", {})
                    self.selected_tables_meta = data.get("selected_tables", {})
                logger.info(f"Loaded {self.db_type} metadata for {len(self.databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load {self.db_type} metadata: {e}")
                # 尝试从备份恢复
                backup_file = f"{meta_file}.backup"
                if os.path.exists(backup_file):
                    try:
                        with open(backup_file, encoding="utf-8") as f:
                            data = json.load(f)
                            self.databases_meta = data.get("databases", {})
                            self.tables_meta = data.get("tables", {})
                            self.selected_tables_meta = data.get("selected_tables", {})
                        logger.info(f"Loaded {self.db_type} metadata from backup")
                        # 恢复备份文件
                        shutil.copy2(backup_file, meta_file)
                        return
                    except Exception as backup_e:
                        logger.error(f"Failed to load backup: {backup_e}")

                # 如果加载失败，初始化为空状态
                logger.warning(f"Initializing empty {self.db_type} metadata")
                self.databases_meta = {}
                self.tables_meta = {}
                self.selected_tables_meta = {}
    @staticmethod
    def _normalize_timestamp(value: Any) -> str | None:
        """Convert persisted timestamps to a normalized UTC ISO string."""
        try:
            dt_value = coerce_any_to_utc_datetime(value)
        except (TypeError, ValueError) as exc:  # noqa: BLE001
            logger.warning(f"Invalid timestamp encountered: {value!r} ({exc})")
            return None

        if not dt_value:
            return None
        return utc_isoformat(dt_value)

    def _normalize_metadata_state(self) -> None:
        """Ensure in-memory metadata uses normalized timestamp formats."""
        for meta in self.databases_meta.values():
            if "created_at" in meta:
                normalized = self._normalize_timestamp(meta.get("created_at"))
                if normalized:
                    meta["created_at"] = normalized

        for table_info in self.tables_meta.values():
            if "created_at" in table_info:
                normalized = self._normalize_timestamp(table_info.get("created_at"))
                if normalized:
                    table_info["created_at"] = normalized

        for table_info in self.selected_tables_meta.values():
            if "created_at" in table_info:
                normalized = self._normalize_timestamp(table_info.get("created_at"))
                if normalized:
                    table_info["created_at"] = normalized

    @property
    @abstractmethod
    def db_type(self) -> str:
        """知识库类型标识"""
        pass

    # @abstractmethod
    # async def _create_db_instance(self, db_id: str, config: dict) -> Any:
    #     """
    #     创建底层知识库实例

    #     Args:
    #         db_id: 数据库ID
    #         config: 配置信息

    #     Returns:
    #         底层知识库实例
    #     """
    #     pass

    @abstractmethod
    async def _create_connection(self) -> Any:
        """
        初始化底层知识库实例

        Args:
            instance: 底层知识库实例
        """
        pass

    @abstractmethod
    def get_cursor(self):
        pass





    def create_database(
        self,
        database_name: str,
        description: str,
        connection_info: dict | None = None,
        **kwargs,
    ) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数

        Returns:
            数据库信息字典
        """

        # 从 kwargs 中获取 is_private 配置
        is_private = kwargs.get("is_private", False)
        prefix = "db_private_" if is_private else "db_"
        db_id = f"{prefix}{hashstr(database_name, with_salt=True)}"

        # 创建数据库记录
        # 确保 Pydantic 模型被转换为字典，以便 JSON 序列化
        connection_info['port'] = int(connection_info['port'])
        self.databases_meta[db_id] = {
            "name": database_name,
            "description": description,
            "db_type": self.db_type,
            "connection_info": connection_info.model_dump() if hasattr(connection_info, "model_dump") else connection_info,
            "metadata": kwargs,
            "created_at": utc_isoformat(),
        }
        self._save_metadata()

        # 创建工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        os.makedirs(working_dir, exist_ok=True)

        # 返回数据库信息
        db_dict = self.databases_meta[db_id].copy()
        db_dict["db_id"] = db_id
        db_dict["tables"] = {}

        return db_dict

    def delete_database(self, db_id: str) -> dict:
        """
        删除数据库

        Args:
            db_id: 数据库ID

        Returns:
            操作结果
        """
        if db_id in self.databases_meta:
            # 删除相关文件记录
            tables_to_delete = [fid for fid, finfo in self.tables_meta.items() if finfo.get("database_id") == db_id]
            for table_id in tables_to_delete:
                del self.tables_meta[table_id]
            tables_to_delete = [fid for fid, finfo in self.selected_tables_meta.items() if finfo.get("database_id") == db_id]
            for table_id in tables_to_delete:
                del self.selected_tables_meta[table_id]

            # 删除数据库记录
            del self.databases_meta[db_id]
            self._save_metadata()

        # 删除工作目录
        working_dir = os.path.join(self.work_dir, db_id)
        if os.path.exists(working_dir):
            import shutil

            try:
                shutil.rmtree(working_dir)
            except Exception as e:
                logger.error(f"Error deleting working directory {working_dir}: {e}")

        return {"message": "删除成功"}

    def get_database_info(self, db_id: str) -> dict | None:
        """
        获取数据库详细信息

        Args:
            db_id: 数据库ID

        Returns:
            数据库信息或None
        """
        if db_id not in self.databases_meta:
            return None

        meta = self.databases_meta[db_id].copy()
        meta["db_id"] = db_id

        # 检查并修复异常的processing状态
        # self._check_and_fix_processing_status(db_id)

        # 获取文件信息
        db_tables = {}
        for table_id, table_info in self.tables_meta.items():
            if table_info.get("database_id") == db_id:
                created_at = self._normalize_timestamp(table_info.get("created_at"))
                db_tables[table_id] = {
                    "database_id": db_id,
                    "table_id": table_id,
                    "table_name": table_info.get("table_name", ""),
                    "created_at": created_at,
                }
        # 获取已选择的表信息
        selected_db_tables = {}
        for table_id, table_info in self.selected_tables_meta.items():
            if table_info.get("database_id") == db_id:
                created_at = self._normalize_timestamp(table_info.get("created_at"))
                selected_db_tables[table_id] = {
                    "database_id": db_id,
                    "table_id": table_id,
                    "table_name": table_info.get("table_name", ""),
                    "created_at": created_at,
                }

        # 按创建时间倒序排序文件列表
        sorted_tables = dict(
            sorted(
                db_tables.items(),
                key=lambda item: item[1].get("created_at") or "",
                reverse=True,
            )
        )

        # 按创建时间倒序排序文件列表
        sorted_selected_tables = dict(
            sorted(
                selected_db_tables.items(),
                key=lambda item: item[1].get("created_at") or "",
                reverse=True,
            )
        )

        meta["selected_tables"] = sorted_selected_tables
        meta["tables"] = sorted_tables
        meta["row_count"] = len(sorted_selected_tables)
        meta["status"] = "已连接"
        return meta

    def get_databases(self) -> dict:
        """
        获取所有数据库信息

        Returns:
            数据库列表
        """
        databases = []
        for db_id, meta in self.databases_meta.items():
            # 检查并修复异常的processing状态
            # self._check_and_fix_processing_status(db_id)

            db_dict = meta.copy()
            db_dict["db_id"] = db_id

            db_tables = {}
            # 获取文件信息
            for table_id, table_info in self.tables_meta.items():
                if table_info.get("database_id") == db_id:
                    created_at = self._normalize_timestamp(table_info.get("created_at"))
                    db_tables[table_id] = {
                        "database_id": db_id,
                        "table_id": table_id,
                        "table_name": table_info.get("table_name", ""),
                        "created_at": created_at,
                        "table_comment": table_info.get("table_comment", ""),
                    }
            # 获取已选择的表信息
            selected_db_tables = {}
            for table_id, table_info in self.selected_tables_meta.items():
                if table_info.get("database_id") == db_id:
                    created_at = self._normalize_timestamp(table_info.get("created_at"))
                    selected_db_tables[table_id] = {
                        "database_id": db_id,
                        "table_id": table_id,
                        "table_name": table_info.get("table_name", ""),
                        "created_at": created_at,
                        "table_comment": table_info.get("table_comment", ""),
                    }

            # 按创建时间倒序排序文件列表
            sorted_tables = dict(
                sorted(
                    db_tables.items(),
                    key=lambda item: item[1].get("created_at") or "",
                    reverse=True,
                )
            )

            # 按创建时间倒序排序文件列表
            sorted_selected_tables = dict(
                sorted(
                    selected_db_tables.items(),
                    key=lambda item: item[1].get("created_at") or "",
                    reverse=True,
                )
            )

            db_dict["tables"] = sorted_tables
            db_dict["selected_tables"] = sorted_selected_tables
            db_dict["row_count"] = len(sorted_selected_tables)
            db_dict["status"] = "已连接"
            databases.append(db_dict)

        return {"databases": databases}

    def _serialize_metadata(self, obj):
        """递归序列化元数据中的 Pydantic 模型"""
        if hasattr(obj, "dict"):
            return obj.dict()
        elif isinstance(obj, dict):
            return {k: self._serialize_metadata(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_metadata(item) for item in obj]
        else:
            return obj

    def _save_metadata(self):
        """保存元数据"""
        self._normalize_metadata_state()
        meta_file = os.path.join(self.work_dir, f"metadata_{self.db_type}.json")
        backup_file = f"{meta_file}.backup"

        try:
            # 创建简单备份
            if os.path.exists(meta_file):
                shutil.copy2(meta_file, backup_file)

            # 准备数据并序列化 Pydantic 模型
            data = {
                "databases": self._serialize_metadata(self.databases_meta),
                "tables": self._serialize_metadata(self.tables_meta),
                "selected_tables": self._serialize_metadata(self.selected_tables_meta),
                "db_type": self.db_type,
                "updated_at": utc_isoformat(),
            }

            # 原子性写入（使用临时文件）
            with tempfile.NamedTemporaryFile(
                mode="w", dir=os.path.dirname(meta_file), prefix=".tmp_", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                temp_path = tmp_file.name

            os.replace(temp_path, meta_file)
            logger.debug(f"Saved {self.db_type} metadata")

        except Exception as e:
            logger.error(f"Failed to save {self.db_type} metadata: {e}")
            # 尝试恢复备份
            if os.path.exists(backup_file):
                try:
                    shutil.copy2(backup_file, meta_file)
                    logger.info("Restored metadata from backup")
                except Exception as restore_e:
                    logger.error(f"Failed to restore backup: {restore_e}")
            raise e
    def prepare_table_metadata(self, db_id: str) -> dict:
        """
        准备文件或URL的元数据
        """
        db_name = self.databases_meta[db_id]['name']
        table_id = f"table_{hashstr(str(db_name) + str(time.time()), 6)}"

        return {
            "database_id": db_id,
            "created_at": utc_isoformat(),
            "table_id": table_id,
        }

    def prepare_table_name_metadata(self, db_id: str, table_name) -> dict:
        """
        准备文件或URL的元数据
        """
        table_id = f"table_{hashstr(str(table_name) + str(time.time()), 6)}"

        return {
            "database_id": db_id,
            "created_at": utc_isoformat(),
            "table_id": table_id,
        }