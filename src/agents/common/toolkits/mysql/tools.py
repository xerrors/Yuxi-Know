from typing import Annotated, Any

from langchain.tools import tool
from pydantic import BaseModel, Field

from src.utils import logger

from .connection import (
    MySQLConnectionManager,
    QueryTimeoutError,
    execute_query_with_timeout,
    limit_result_size,
)
from .exceptions import MySQLConnectionError
from .security import MySQLSecurityChecker

# 全局连接管理器实例
_connection_manager: MySQLConnectionManager | None = None


def get_connection_manager() -> MySQLConnectionManager:
    """获取全局连接管理器"""
    global _connection_manager
    if _connection_manager is None:
        import os

        # 从环境变量中读取 MySQL 配置
        mysql_config = {
            "host": os.getenv("MYSQL_HOST"),
            "user": os.getenv("MYSQL_USER"),
            "password": os.getenv("MYSQL_PASSWORD"),
            "database": os.getenv("MYSQL_DATABASE"),
            "port": int(os.getenv("MYSQL_PORT") or "3306"),
            "charset": "utf8mb4",
            "description": os.getenv("MYSQL_DATABASE_DESCRIPTION") or "默认 MySQL 数据库",
        }
        # 验证配置完整性
        required_keys = ["host", "user", "password", "database"]
        for key in required_keys:
            if not mysql_config[key]:
                raise MySQLConnectionError(f"MySQL configuration missing required key: {key}")

        _connection_manager = MySQLConnectionManager(mysql_config)
    return _connection_manager


class TableListModel(BaseModel):
    """获取表名列表的参数模型"""

    pass


@tool(name_or_callable="查询表名及说明", args_schema=TableListModel)
def mysql_list_tables() -> str:
    """获取数据库中的所有表名

    这个工具用来列出当前数据库中所有的表名，帮助你了解数据库的结构。
    """
    try:
        conn_manager = get_connection_manager()

        with conn_manager.get_cursor() as cursor:
            # 获取表名
            cursor.execute("SHOW TABLES")
            logger.debug("Executed `SHOW TABLES` query")
            tables = cursor.fetchall()

            if not tables:
                return "数据库中没有找到任何表"

            # 提取表名
            table_names = []
            for table in tables:
                table_name = list(table.values())[0]
                table_names.append(table_name)

            # 获取每个表的行数信息
            # table_info = []
            # for table_name in table_names:
            #     try:
            #         cursor.execute(f"SELECT COUNT(*) as count FROM `{table_name}`")
            #         logger.debug(f"Executed `SELECT COUNT(*) FROM {table_name}` query")
            #         count_result = cursor.fetchone()
            #         row_count = count_result["count"]
            #         table_info.append(f"- {table_name} (约 {row_count} 行)")
            #     except Exception:
            #         table_info.append(f"- {table_name} (无法获取行数)")

            all_table_names = "\n".join(table_names)
            result = f"数据库中的表:\n{all_table_names}"
            if db_note := conn_manager.config.get("description"):
                result = f"数据库说明: {db_note}\n\n" + result
            logger.info(f"Retrieved {len(table_names)} tables from database")
            return result

    except Exception as e:
        error_msg = f"获取表名失败: {str(e)}"
        logger.error(error_msg)
        return error_msg


class TableDescribeModel(BaseModel):
    """获取表结构的参数模型"""

    table_name: str = Field(description="要查询的表名", example="users")


@tool(name_or_callable="描述表", args_schema=TableDescribeModel)
def mysql_describe_table(table_name: Annotated[str, "要查询结构的表名"]) -> str:
    """获取指定表的详细结构信息

    这个工具用来查看表的字段信息、数据类型、是否允许NULL、默认值、键类型等。
    帮助你了解表的结构，以便编写正确的SQL查询。
    """
    try:
        # 验证表名安全性
        if not MySQLSecurityChecker.validate_table_name(table_name):
            return "表名包含非法字符，请检查表名"

        conn_manager = get_connection_manager()

        with conn_manager.get_cursor() as cursor:
            # 获取表结构
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()

            if not columns:
                return f"表 {table_name} 不存在或没有字段"

            # 获取字段备注信息
            column_comments: dict[str, str] = {}
            try:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_COMMENT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_NAME = %s AND TABLE_SCHEMA = %s
                    """,
                    (table_name, conn_manager.database_name),
                )
                comment_rows = cursor.fetchall()
                for row in comment_rows:
                    column_name = row.get("COLUMN_NAME")
                    if column_name:
                        column_comments[column_name] = row.get("COLUMN_COMMENT") or ""
            except Exception as e:
                logger.warning(f"Failed to fetch column comments for table {table_name}: {e}")

            # 格式化输出
            result = f"表 `{table_name}` 的结构:\n\n"
            result += "字段名\t\t类型\t\tNULL\t键\t默认值\t\t额外\t备注\n"
            result += "-" * 80 + "\n"

            for col in columns:
                field = col["Field"] or ""
                type_str = col["Type"] or ""
                null_str = col["Null"] or ""
                key_str = col["Key"] or ""
                default_str = col.get("Default") or ""
                extra_str = col.get("Extra") or ""
                comment_str = column_comments.get(field, "")

                # 格式化输出
                result += (
                    f"{field:<16}\t{type_str:<16}\t{null_str:<8}\t{key_str:<4}\t"
                    f"{default_str:<16}\t{extra_str:<16}\t{comment_str}\n"
                )

            # 获取索引信息
            try:
                cursor.execute(f"SHOW INDEX FROM `{table_name}`")
                indexes = cursor.fetchall()

                if indexes:
                    result += "\n索引信息:\n"
                    index_dict = {}
                    for idx in indexes:
                        key_name = idx["Key_name"]
                        if key_name not in index_dict:
                            index_dict[key_name] = []
                        index_dict[key_name].append(idx["Column_name"])

                    for key_name, columns in index_dict.items():
                        result += f"- {key_name}: {', '.join(columns)}\n"
            except Exception as e:
                logger.warning(f"Failed to get index info for table {table_name}: {e}")

            logger.info(f"Retrieved structure for table {table_name}")
            return result

    except Exception as e:
        error_msg = f"获取表 {table_name} 结构失败: {str(e)}"
        logger.error(error_msg)
        return error_msg


class QueryModel(BaseModel):
    """执行SQL查询的参数模型"""

    sql: str = Field(description="要执行的SQL查询语句（只能是SELECT语句）", example="SELECT * FROM users WHERE id = 1")
    timeout: int | None = Field(default=60, description="查询超时时间（秒），默认60秒，最大600秒", ge=1, le=600)


@tool(name_or_callable="执行 SQL 查询", args_schema=QueryModel)
def mysql_query(
    sql: Annotated[str, "要执行的SQL查询语句（只能是SELECT语句）"],
    timeout: Annotated[int | None, "查询超时时间（秒），默认60秒，最大600秒"] = 60,
) -> str:
    """执行只读的SQL查询语句

    这个工具用来执行SQL查询并返回结果。支持复杂的SELECT查询，包括JOIN、GROUP BY等。
    注意：只能执行查询操作，不能修改数据。

    参数:
    - sql: SQL查询语句
    - timeout: 查询超时时间（防止长时间运行的查询）
    """
    try:
        # 验证SQL安全性
        if not MySQLSecurityChecker.validate_sql(sql):
            return "SQL语句包含不安全的操作或可能的注入攻击，请检查SQL语句"

        if not MySQLSecurityChecker.validate_timeout(timeout):
            return "timeout参数必须在1-600之间"

        conn_manager = get_connection_manager()
        connection = conn_manager.get_connection()

        effective_timeout = timeout or 60
        try:
            result = execute_query_with_timeout(connection, sql, timeout=effective_timeout)
        except QueryTimeoutError as timeout_error:
            logger.error(f"MySQL query timed out after {effective_timeout} seconds: {timeout_error}")
            raise
        except Exception:
            conn_manager.invalidate_connection()
            raise

        if not result:
            return "查询执行成功，但没有返回任何结果"

        # 限制结果大小
        limited_result = limit_result_size(result, max_chars=10000)

        # 检查结果是否被截断
        if len(limited_result) < len(result):
            warning = f"\n\n⚠️ 警告: 查询结果过大，只显示了前 {len(limited_result)} 行（共 {len(result)} 行）。\n"
            warning += "建议使用更精确的查询条件或使用LIMIT子句来减少返回的数据量。"
        else:
            warning = ""

        # 格式化输出
        if limited_result:
            # 获取列名
            columns = list(limited_result[0].keys())

            # 计算每列的最大宽度
            col_widths = {}
            for col in columns:
                col_widths[col] = max(len(str(col)), max(len(str(row.get(col, ""))) for row in limited_result))
                col_widths[col] = min(col_widths[col], 50)  # 限制最大宽度

            # 构建表头
            header = "| " + " | ".join(f"{col:<{col_widths[col]}}" for col in columns) + " |"
            separator = "|" + "|".join("-" * (col_widths[col] + 2) for col in columns) + "|"

            # 构建数据行
            rows = []
            for row in limited_result:
                row_str = "| " + " | ".join(f"{str(row.get(col, '')):<{col_widths[col]}}" for col in columns) + " |"
                rows.append(row_str)

            result_str = f"查询结果（共 {len(limited_result)} 行）:\n\n"
            result_str += header + "\n" + separator + "\n"
            result_str += "\n".join(rows[:50])  # 最多显示50行

            if len(rows) > 50:
                result_str += f"\n\n... 还有 {len(rows) - 50} 行未显示 ..."

            result_str += warning

            logger.info(f"Query executed successfully, returned {len(limited_result)} rows")
            return result_str

        return "查询执行成功，但返回数据为空"

    except Exception as e:
        error_msg = f"SQL查询执行失败: {str(e)}\n\n{sql}"

        # 提供更有用的错误信息
        if "timeout" in str(e).lower():
            error_msg += "\n\n💡 建议：查询超时了，请尝试以下方法：\n"
            error_msg += "1. 减少查询的数据量（使用WHERE条件过滤）\n"
            error_msg += "2. 使用LIMIT子句限制返回行数\n"
            error_msg += "3. 增加timeout参数值（最大600秒）"
        elif "table" in str(e).lower() and "doesn't exist" in str(e).lower():
            error_msg += "\n\n💡 建议：表不存在，请使用 mysql_list_tables 查看可用的表名"
        elif "column" in str(e).lower() and "doesn't exist" in str(e).lower():
            error_msg += "\n\n💡 建议：列不存在，请使用 mysql_describe_table 查看表结构"
        elif "not enough arguments for format string" in str(e).lower():
            error_msg += (
                "\n\n💡 建议：SQL 中的百分号 (%) 被当作参数占位符使用。"
                " 如需匹配包含百分号的文本，请将百分号写成双百分号 (%%) 或使用参数化查询。"
            )

        logger.error(error_msg)
        return error_msg


def get_mysql_tools() -> list[Any]:
    """获取MySQL工具列表"""
    return [mysql_list_tables, mysql_describe_table, mysql_query]
