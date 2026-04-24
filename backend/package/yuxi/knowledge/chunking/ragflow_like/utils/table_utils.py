from __future__ import annotations

from bs4 import BeautifulSoup


def html_table_to_markdown(html: str) -> str:
    """
    将HTML表格转换为Markdown格式的具体实现
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return ""

    rows = table.find_all("tr")
    if not rows:
        return ""

    grid = []

    for r_idx, row in enumerate(rows):
        while len(grid) <= r_idx:
            grid.append([])

        cells = row.find_all(["td", "th"])
        c_idx = 0

        for cell in cells:
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1

            text = cell.get_text(strip=True)
            text = text.replace("\n", " ")

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))

            for r in range(rowspan):
                target_r = r_idx + r
                while len(grid) <= target_r:
                    grid.append([])

                for c in range(colspan):
                    target_c = c_idx + c
                    while len(grid[target_r]) <= target_c:
                        grid[target_r].append(None)

                    grid[target_r][target_c] = text

            c_idx += colspan

    if not grid:
        return ""

    markdown_lines = []
    max_cols = max(len(r) for r in grid)
    for r in grid:
        while len(r) < max_cols:
            r.append("")

    header = grid[0]
    header = [h if h is not None else "" for h in header]
    markdown_lines.append("| " + " | ".join(header) + " |")
    markdown_lines.append("|" + "|".join([" --- " for _ in range(max_cols)]) + "|")

    for row in grid[1:]:
        row_clean = [cell if cell is not None else "" for cell in row]
        line = "| " + " | ".join(row_clean) + " |"
        markdown_lines.append(line)

    return "\n".join(markdown_lines)


def html_table_to_key_value(html: str) -> list[str]:
    """
    将HTML表格转换为键值对格式的列表，为了应对过长的表格的切分问题。

    处理逻辑：
    1. **网格重建**：由于 HTML 表格可能包含 `rowspan` 和 `colspan`（合并单元格），
       函数首先构建一个完整的二维网格（grid）。
    2. **单元格展开**：遍历 HTML 行和列，遇到合并单元格时，将其内容填充到网格中受影响的所有坐标点。
       这确保了原本被合并的区域在逻辑网格中每个点都有对应的值。
    3. **键值对转换**：
       - 将网格的第一行视为表头（Key）。
       - 从第二行开始，将每一行与表头对应，生成 "键：值" 形式的字符串。

    例如：
    - 输入：HTML表格，包含姓名、年龄、性别三列。
    - 输出：['姓名：张三；年龄：25；性别：男', '姓名：李四；年龄：30；性别：女']
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    grid = []

    for r_idx, row in enumerate(rows):
        while len(grid) <= r_idx:
            grid.append([])

        cells = row.find_all(["td", "th"])
        c_idx = 0

        for cell in cells:
            while c_idx < len(grid[r_idx]) and grid[r_idx][c_idx] is not None:
                c_idx += 1

            text = cell.get_text(strip=True)
            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))

            for r in range(rowspan):
                target_r = r_idx + r
                while len(grid) <= target_r:
                    grid.append([])

                for c in range(colspan):
                    target_c = c_idx + c
                    while len(grid[target_r]) <= target_c:
                        grid[target_r].append(None)
                    grid[target_r][target_c] = text
            c_idx += colspan

    if not grid:
        return []

    headers = grid[0]
    headers = [h if h is not None else "" for h in headers]

    kv_lines = []
    for row_values in grid[1:]:
        min_len = min(len(headers), len(row_values))
        row_parts = []
        for i in range(min_len):
            key = headers[i]
            val = row_values[i] if row_values[i] is not None else ""
            if key:
                row_parts.append(f"{key}：{val}")
        if row_parts:
            kv_lines.append("；".join(row_parts) + "；")

    return kv_lines
