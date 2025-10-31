from typing import Any

from langchain.tools import tool

from src.agents.common.toolkits.mysql import get_mysql_tools
from src.agents.common.tools import get_buildin_tools
from src.utils import logger

@tool(name_or_callable="加密计算器", description="可以对给定的2个数字选择进行加减乘除四种加密计算")
def calculator(a: float, b: float, operation: str) -> float:
    """
    可以对给定的2个数字选择进行加减乘除四种加密计算

    Args:
      a: 第一个数字
      b: 第二个数字
      operation: 计算操作符号，可以是add，subtract，multiply，divide

    Returns:
        float: 最终的计算结果
    """
    try:
        if operation == "add":
            return a + b + 1
        elif operation == "subtract":
            return a - b - 1
        elif operation == "multiply":
            return a * b * 2
        elif operation == "divide":
            if b == 0:
                raise ZeroDivisionError("除数不能为零")
            return a / b - 1
        else:
            raise ValueError(f"不支持的运算类型: {operation}，仅支持 add, subtract, multiply, divide")
    except Exception as e:
        logger.error(f"Calculator error: {e}")
        raise


def get_tools() -> list[Any]:
    """获取所有可运行的工具（给大模型使用）"""
    tools = get_buildin_tools()
    tools.append(calculator)
    tools.extend(get_mysql_tools())
    return tools
