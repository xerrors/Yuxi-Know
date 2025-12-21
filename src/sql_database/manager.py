import os, asyncio, json
import tempfile
import pymysql
import shutil
from pymysql import MySQLError
from pymysql.cursors import DictCursor
from src.sql_database.base import DBNotFoundError, DBOperationError
from src.sql_database.implementations.mysql import MySQLConnector
from src.sql_database.factory import DBConnectorBaseFactory
from src.utils.datetime_utils import coerce_any_to_utc_datetime, utc_isoformat

from src.utils import logger


class SqlDataBaseManager:
    """数据库管理器

    统一管理多种类型的数据库实例，提供统一的外部接口
    """
    def __init__(self, work_dir: str):
        """
        初始化知识库管理器

        Args:
            work_dir: 工作目录
        """
        self.work_dir = work_dir
        os.makedirs(work_dir, exist_ok=True)

        # 知识库实例缓存 {kb_type: kb_instance}
        self.db_instances: dict[str, MySQLConnector] = {}

        # 全局数据库元信息 {db_id: metadata_with_kb_type}
        self.global_databases_meta: dict[str, dict] = {}

        self.db_name_to_id: dict[str, str] = {}

        # 元数据锁
        self._metadata_lock = asyncio.Lock()

        # 加载全局元数据
        self._load_global_metadata()
        self._normalize_global_metadata()

        # 初始化已存在的知识库实例
        self._initialize_existing_dbs()

        logger.info("KnowledgeBaseManager initialized")

    def _update_db_name2id(self):
        for database_id, database_meta in self.global_databases_meta.items():
            database_name = database_meta.get("name")
            self.db_name_to_id[database_name] = database_id

    def _load_global_metadata(self):
        """加载全局元数据"""
        meta_file = os.path.join(self.work_dir, "global_metadata.json")

        if os.path.exists(meta_file):
            try:
                with open(meta_file, encoding="utf-8") as f:
                    data:dict = json.load(f)
                    self.global_databases_meta = data.get("databases", {})
                logger.info(f"Loaded global metadata for {len(self.global_databases_meta)} databases")
            except Exception as e:
                logger.error(f"Failed to load global metadata: {e}")
                # 尝试从备份恢复
                backup_file = f"{meta_file}.backup"
                if os.path.exists(backup_file):
                    try:
                        with open(backup_file, encoding="utf-8") as f:
                            data = json.load(f)
                            self.global_databases_meta = data.get("databases", {})
                        logger.info("Loaded global metadata from backup")
                        # 恢复备份文件
                        shutil.copy2(backup_file, meta_file)
                        return
                    except Exception as backup_e:
                        logger.error(f"Failed to load backup: {backup_e}")

                # 如果加载失败，初始化为空状态
                logger.warning("Initializing empty global metadata")
                self.global_databases_meta = {}


    
    def _normalize_global_metadata(self) -> None:
        """Normalize stored timestamps within the global metadata cache."""
        for meta in self.global_databases_meta.values():
            if "created_at" in meta:
                try:
                    dt_value = coerce_any_to_utc_datetime(meta.get("created_at"))
                    if dt_value:
                        meta["created_at"] = utc_isoformat(dt_value)
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"Failed to normalize database metadata timestamp {meta.get('created_at')!r}: {exc}")


    def _initialize_existing_dbs(self):
        """初始化已存在的数据库库实例"""
        db_types_in_use = set()
        for db_meta in self.global_databases_meta.values():
            db_type = db_meta.get("db_type", "mysql")  # 默认为mysql
            db_types_in_use.add(db_type)

        # 为每种使用中的知识库类型创建实例
        for db_type in db_types_in_use:
            try:
                self._get_or_create_db_instance(db_type)
            except Exception as e:
                logger.error(f"Failed to initialize {db_type} knowledge base: {e}")

    def _get_or_create_db_instance(self, db_type: str) -> MySQLConnector:
        """
        获取或创建知识库实例

        Args:
            kb_type: 知识库类型

        Returns:
            知识库实例
        """
        self._update_db_name2id()
        if db_type in self.db_instances:
            return self.db_instances[db_type]

        # 创建新的知识库实例
        db_work_dir = os.path.join(self.work_dir, f"{db_type}_data")
        db_instance = DBConnectorBaseFactory.create(db_type, db_work_dir)

        self.db_instances[db_type] = db_instance
        logger.info(f"Created {db_type} knowledge base instance")
        return db_instance
    
    def _get_db_for_database(self, db_id: str) -> MySQLConnector:
        """
        根据数据库ID获取对应的知识库实例

        Args:
            db_id: 数据库ID

        Returns:
            知识库实例

        Raises:
            KBNotFoundError: 数据库不存在或知识库类型不支持
        """
        if db_id not in self.global_databases_meta:
            raise DBNotFoundError(f"Database {db_id} not found")

        db_type = self.global_databases_meta[db_id].get("db_type", "mysql")

        if not DBConnectorBaseFactory.is_type_supported(db_type):
            raise DBNotFoundError(f"Unsupported knowledge base type: {db_type}")

        return self._get_or_create_db_instance(db_type)

    def _save_global_metadata(self):
        """保存全局元数据"""
        self._normalize_global_metadata()
        meta_file = os.path.join(self.work_dir, "global_metadata.json")
        backup_file = f"{meta_file}.backup"

        try:
            # 创建简单备份
            if os.path.exists(meta_file):
                shutil.copy2(meta_file, backup_file)
            logger.debug(f"global datasets meta: {self.global_databases_meta}")
            # 准备数据
            data = {"databases": self.global_databases_meta, "updated_at": utc_isoformat(), "version": "2.0"}

            # 原子性写入（使用临时文件）
            with tempfile.NamedTemporaryFile(
                mode="w", dir=os.path.dirname(meta_file), prefix=".tmp_", suffix=".json", delete=False, encoding="utf-8"
            ) as tmp_file:
                json.dump(data, tmp_file, ensure_ascii=False, indent=2)
                temp_path = tmp_file.name

            os.replace(temp_path, meta_file)
            logger.debug("Saved global metadata")

        except Exception as e:
            logger.error(f"Failed to save global metadata: {e}")
            # 尝试恢复备份
            if os.path.exists(backup_file):
                try:
                    shutil.copy2(backup_file, meta_file)
                    logger.info("Restored global metadata from backup")
                except Exception as restore_e:
                    logger.error(f"Failed to restore backup: {restore_e}")
            raise e
       
        self._update_db_name2id()

    # =============================================================================
    # 统一的外部接口 - 与原始 LightRagBasedKB 兼容
    # =============================================================================

    def test_connection(self, config: dict) -> bool:
        try:
            connection = pymysql.connect(
                host=config["host"],
                user=config["user"],
                password=config["password"],
                database=config["database"],
                port=config["port"],
                charset=config.get("charset", "utf8mb4"),
                cursorclass=DictCursor,
                connect_timeout=10,
                read_timeout=60,  # 增加读取超时
                write_timeout=30,
                autocommit=True,  # 自动提交
            )
            return connection

        except MySQLError as e:
            logger.error(f"Failed to connect to MySQL: {e}")
            raise ConnectionError(f"MySQL connection failed: {e}")

    def get_database_instance(self, db_id: str) -> MySQLConnector:
        """Public accessor to fetch the underlying knowledge base instance by database id.

        This provides a simple compatibility layer for callers that expect a
        `get_kb` method on the manager.
        """
        return self._get_db_for_database(db_id)

    def get_databases(self) -> dict:
        """获取所有数据库信息"""
        all_databases = []

        # 收集所有知识库的数据库信息
        for kb_type, kb_instance in self.db_instances.items():
            kb_databases = kb_instance.get_databases()["databases"]
            all_databases.extend(kb_databases)

        return {"databases": all_databases}

    async def create_database(
        self, database_name: str, description: str, db_type: str, **kwargs
    ) -> dict:
        """
        创建数据库

        Args:
            database_name: 数据库名称
            description: 数据库描述
            kb_type: 知识库类型，默认为lightrag
            embed_info: 嵌入模型信息
            **kwargs: 其他配置参数，包括chunk_size和chunk_overlap

        Returns:
            数据库信息字典
        """
        if not DBConnectorBaseFactory.is_type_supported(db_type):
            available_types = list(DBConnectorBaseFactory.get_available_types().keys())
            raise ValueError(f"Unsupported knowledge base type: {db_type}. Available types: {available_types}")

        db_instance = self._get_or_create_db_instance(db_type)

        db_info = db_instance.create_database(database_name, description, **kwargs)

        db_id = db_info["db_id"]

        async with self._metadata_lock:
            self.global_databases_meta[db_id] = {
                "name": database_name,
                "description": description,
                "db_type": db_type,
                "created_at": utc_isoformat(),
                # "connection_params": kwargs.copy(),
            }
            self._save_global_metadata()

        logger.info(f"Created {db_type} database: {database_name} ({db_id}) with {kwargs}")
        # db_info = {
        #         "name": database_name,
        #         "description": description,
        #         "db_type": db_type,
        #         "created_at": utc_isoformat(),
        #         # "connection_params": kwargs.copy(),
        #     }
        return db_info

    async def delete_database(self, db_id: str) -> dict:
        """删除数据库"""
        try:
            kb_instance = self._get_db_for_database(db_id)
            result = kb_instance.delete_database(db_id)

            async with self._metadata_lock:
                if db_id in self.global_databases_meta:
                    del self.global_databases_meta[db_id]
                    self._save_global_metadata()

            return result
        except DBNotFoundError as e:
            logger.warning(f"Database {db_id} not found during deletion: {e}")
            return {"message": "删除成功"}

    def get_connection(self, db_id: str):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.get_connection(db_id)

    def invalidate_connection(self, db_id: str):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.invalidate_connection()

    def get_database_info(self, db_id: str) -> dict | None:
        """获取数据库详细信息"""
        try:
            kb_instance = self._get_db_for_database(db_id)
            db_info = kb_instance.get_database_info(db_id)

            # 添加全局元数据中的additional_params信息
            if db_info and db_id in self.global_databases_meta:
                global_meta = self.global_databases_meta[db_id]
                additional_params = global_meta.get("additional_params", {})
                if additional_params:
                    db_info["additional_params"] = additional_params

            return db_info
        except DBNotFoundError:
            return None


    async def initialize_tables(self, db_id: str) -> dict | None:
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.initalize_table(db_id)


    async def select_tables(self, db_id: str, table_ids: list[dict]) -> list[dict]:
        """设置表信息"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.select_tables(db_id, table_ids)
    
    async def unselect_table(self, db_id: str, table_id: str) -> dict:
        """取消设置表"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.unselect_table(table_id)

    async def get_table_basic_info(self, db_id: str, file_id: str) -> dict:
        """获取文件基本信息（仅元数据）"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_table_basic_info(db_id, file_id)

    async def get_tables(self, db_id: str) -> dict:
        """获取数据库表信息"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_tables()

    async def get_selected_tables(self, db_id: str) -> dict:
        """获取已选择的数据库表信息"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_selected_tables()

    async def get_table_info(self, db_id: str, table_id: str) -> dict:
        """获取文件完整信息（基本信息+内容信息）- 保持向后兼容"""
        db_instance = self._get_db_for_database(db_id)
        return await db_instance.get_table_info(db_id, table_id)

    def table_existed_in_db(self, db_id: str | None, table_name: str | None) -> bool:
        """检查指定数据库中是否存在相同内容哈希的文件"""
        if not db_id or not table_name:
            return False

        try:
            db_instance = self._get_db_for_database(db_id)
        except DBNotFoundError:
            return False

        for file_info in db_instance.tables_meta.values():
            if file_info.get("database_id") != db_id:
                continue
            if file_info.get("table_name") == table_name:
                return True

        return False


    def get_cursors(self) -> dict[str, dict]:
        """获取所有检索器"""
        all_cursors= {}

        # 收集所有知识库的检索器
        for db_instance in self.db_instances.values():
            cursors = db_instance.get_cursors()
            all_cursors.update(cursors)

        return all_cursors

    def get_cursor(self, db_id):
        db_instance = self._get_db_for_database(db_id)
        return db_instance.get_cursor(db_id)