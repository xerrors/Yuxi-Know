import time

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class KnowledgeDatabase(Base):
    """知识库模型"""

    __tablename__ = "knowledge_databases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    db_id = Column(String, nullable=False, unique=True, index=True)  # 数据库ID
    name = Column(String, nullable=False)  # 数据库名称
    description = Column(Text, nullable=True)  # 描述
    embed_model = Column(String, nullable=True)  # 嵌入模型名称
    dimension = Column(Integer, nullable=True)  # 向量维度
    meta_info = Column(JSON, nullable=True)  # 元数据
    created_at = Column(DateTime, default=func.now())  # 创建时间

    # 关系
    files = relationship("KnowledgeFile", back_populates="database", cascade="all, delete-orphan")

    def to_dict(self, with_nodes=True):
        """转换为字典格式，确保meta_info映射为metadata"""
        result = {
            "id": self.id,
            "db_id": self.db_id,
            "name": self.name,
            "description": self.description,
            "embed_model": self.embed_model,
            "dimension": self.dimension,
            "metadata": self.meta_info or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        # 添加文件信息
        if self.files:
            result["files"] = {file.file_id: file.to_dict(with_nodes=with_nodes) for file in self.files}
        else:
            result["files"] = {}
        return result


class KnowledgeFile(Base):
    """知识库文件模型"""

    __tablename__ = "knowledge_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, nullable=False, index=True)  # 文件ID
    database_id = Column(String, ForeignKey("knowledge_databases.db_id"), nullable=False)  # 所属数据库ID
    filename = Column(String, nullable=False)  # 文件名
    path = Column(String, nullable=False)  # 文件路径
    file_type = Column(String, nullable=False)  # 文件类型
    status = Column(String, nullable=False)  # 处理状态
    created_at = Column(DateTime, default=func.now())  # 创建时间

    # 关系
    database = relationship("KnowledgeDatabase", back_populates="files")
    nodes = relationship("KnowledgeNode", back_populates="file", cascade="all, delete-orphan")

    @property
    def computed_node_count(self):
        """动态计算节点数量"""
        return len(self.nodes) if self.nodes is not None else 0

    def to_dict(self, with_nodes=True):
        """转换为字典格式"""
        result = {
            "file_id": self.file_id,
            "filename": self.filename,
            "path": self.path,
            "type": self.file_type,
            "status": self.status,
            "node_count": self.computed_node_count,
            "created_at": self.created_at.timestamp() if self.created_at else time.time(),
        }
        if with_nodes:
            result["nodes"] = [node.to_dict() for node in self.nodes] if self.nodes else []
        return result


class KnowledgeNode(Base):
    """知识块模型"""

    __tablename__ = "knowledge_nodes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey("knowledge_files.file_id"), nullable=False)  # 所属文件ID
    text = Column(Text, nullable=False)  # 文本内容
    hash = Column(String, nullable=True)  # 文本哈希值
    start_char_idx = Column(Integer, nullable=True)  # 开始字符索引
    end_char_idx = Column(Integer, nullable=True)  # 结束字符索引
    meta_info = Column(JSON, nullable=True)  # 元数据

    # 关系
    file = relationship("KnowledgeFile", back_populates="nodes")

    def to_dict(self):
        """转换为字典格式，确保meta_info映射为metadata"""
        return {
            "id": self.id,
            "file_id": self.file_id,
            "text": self.text,
            "hash": self.hash,
            "start_char_idx": self.start_char_idx,
            "end_char_idx": self.end_char_idx,
            "metadata": self.meta_info or {},  # 确保映射正确
        }


class Thread(Base):
    """对话线程表"""

    __tablename__ = "thread"

    id = Column(String(64), primary_key=True, index=True, comment="线程ID")
    user_id = Column(String(64), index=True, nullable=False, comment="用户ID")
    agent_id = Column(String(64), index=True, nullable=False, comment="智能体ID")
    title = Column(String(255), nullable=True, comment="标题")
    create_at = Column(DateTime, default=func.now(), comment="创建时间")
    update_at = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")

    description = Column(String(255), nullable=True, comment="描述")
    status = Column(Integer, default=1, comment="状态")


class User(Base):
    """用户模型"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)  # 显示名称，2-20字符
    user_id = Column(String, nullable=False, unique=True, index=True)  # 登录ID，根据用户名生成
    phone_number = Column(String, nullable=True, unique=True, index=True)  # 手机号，可选登录方式
    avatar = Column(String, nullable=True)  # 头像URL
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # 角色: superadmin, admin, user
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, nullable=True)

    # 登录失败限制相关字段
    login_failed_count = Column(Integer, nullable=False, default=0)  # 登录失败次数
    last_failed_login = Column(DateTime, nullable=True)  # 最后一次登录失败时间
    login_locked_until = Column(DateTime, nullable=True)  # 锁定到什么时候

    # 关联操作日志
    operation_logs = relationship("OperationLog", back_populates="user")

    def to_dict(self, include_password=False):
        result = {
            "id": self.id,
            "username": self.username,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "avatar": self.avatar,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "login_failed_count": self.login_failed_count,
            "last_failed_login": self.last_failed_login.isoformat() if self.last_failed_login else None,
            "login_locked_until": self.login_locked_until.isoformat() if self.login_locked_until else None,
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

    def is_login_locked(self):
        """检查用户是否处于登录锁定状态"""
        if self.login_locked_until is None:
            return False
        from datetime import datetime

        return datetime.now() < self.login_locked_until

    def get_remaining_lock_time(self):
        """获取剩余锁定时间（秒）"""
        if not self.is_login_locked():
            return 0
        from datetime import datetime

        return int((self.login_locked_until - datetime.now()).total_seconds())

    def calculate_lock_duration(self):
        """根据失败次数计算锁定时长（秒）"""
        if self.login_failed_count < 10:
            return 0

        # 从第10次失败开始，等待时间从1秒开始，每次翻倍
        wait_seconds = 2 ** (self.login_failed_count - 10)

        # 最大锁定时间：365天
        max_seconds = 365 * 24 * 60 * 60
        return min(wait_seconds, max_seconds)

    def increment_failed_login(self):
        """增加登录失败次数并设置锁定时间"""
        from datetime import datetime, timedelta

        self.login_failed_count += 1
        self.last_failed_login = datetime.now()

        lock_duration = self.calculate_lock_duration()
        if lock_duration > 0:
            self.login_locked_until = datetime.now() + timedelta(seconds=lock_duration)

    def reset_failed_login(self):
        """重置登录失败相关字段"""
        self.login_failed_count = 0
        self.last_failed_login = None
        self.login_locked_until = None


class OperationLog(Base):
    """操作日志模型"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    operation = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())

    # 关联用户
    user = relationship("User", back_populates="operation_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "operation": self.operation,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
