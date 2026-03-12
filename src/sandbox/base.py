from abc import ABC, abstractmethod


class Sandbox(ABC):
    """沙盒执行环境抽象基类，与 deer-flow 保持一致"""

    _id: str

    def __init__(self, id: str):
        self._id = id

    @property
    def id(self) -> str:
        return self._id

    @abstractmethod
    def execute_command(self, command: str) -> str:
        """在沙盒内执行 bash 命令

        Args:
            command: 待执行的指令

        Returns:
            命令的标准输出或错误输出拼合字符串
        """

    @abstractmethod
    def read_file(self, path: str) -> str:
        """读取指定文件内容

        Args:
            path: 沙盒内的绝对路径

        Returns:
            文件内容
        """

    @abstractmethod
    def list_dir(self, path: str) -> list[str]:
        """列出目录内容（最多 2 层深度的树状结构）

        Args:
            path: 沙盒内的绝对路径

        Returns:
            包含文件/目录名称的字符串列表
        """

    @abstractmethod
    def write_file(self, path: str, content: str, append: bool = False) -> None:
        """将内容写入沙盒内指定文件

        Args:
            path: 沙盒内的绝对路径
            content: 待写入的文本内容
            append: 是否追加写入，如果为 False 则是覆盖写入
        """
