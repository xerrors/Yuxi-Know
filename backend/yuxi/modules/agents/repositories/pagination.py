"""Agent 游标页的排序与有序边界，作用域和游标读取仍由仓储拥有。"""

from sqlalchemy import tuple_


def order_page(statement, *, columns: tuple, anchor: tuple | None = None, order: str = "desc"):
    """以同一列序构造游标边界和稳定排序。"""
    if anchor is not None:
        position, boundary = tuple_(*columns), tuple_(*anchor)
        statement = statement.where(position > boundary if order == "asc" else position < boundary)
    sorting = [column.asc() if order == "asc" else column.desc() for column in columns]
    return statement.order_by(*sorting)
