""".xls 入口按文件头嗅探分派的回归测试：BIFF、xlsx 改名、SpreadsheetML、HTML 与不可识别内容。"""

from __future__ import annotations

from pathlib import Path

import pytest

from yuxi.knowledge.parser.unified import _convert_legacy_excel_to_markdown

pytestmark = [pytest.mark.unit]

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data"

SPREADSHEETML = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="装备">
  <Table>
   <Row><Cell><Data ss:Type="String">雷达</Data></Cell><Cell ss:Index="3"><Data ss:Type="Number">53</Data></Cell></Row>
   <Row>
    <Cell><Data ss:Type="String">声呐</Data></Cell>
    <Cell ss:MergeAcross="1"><Data ss:Type="String">合并</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
 <Worksheet ss:Name="空表"><Table/></Worksheet>
</Workbook>
"""


def _xlrd_fails(path: Path) -> None:
    """负控：证明旧实现（xlrd 直读）对该内容必然抛错，嗅探分派是必要的。"""
    import pandas as pd

    with pytest.raises(Exception):
        pd.read_excel(path, engine="xlrd", sheet_name=None, header=None, dtype=object, keep_default_na=False)


def test_biff_xls_still_parses():
    out = _convert_legacy_excel_to_markdown(SAMPLE_DIR / "测试旧表格.xls")
    assert "项目" in out and "数值" in out


def test_renamed_xlsx_falls_back_to_openpyxl(tmp_path):
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet["A1"] = "伪装表格"
    sheet["B2"] = "中文内容"
    path = tmp_path / "伪装.xls"
    workbook.save(path)

    _xlrd_fails(path)
    out = _convert_legacy_excel_to_markdown(path)
    assert "伪装表格" in out and "中文内容" in out


def test_spreadsheetml_parses_with_index_and_merge(tmp_path):
    path = tmp_path / "xml表格.xls"
    path.write_text(SPREADSHEETML, encoding="utf-8")

    _xlrd_fails(path)
    out = _convert_legacy_excel_to_markdown(path)
    assert "装备" in out
    assert "雷达" in out and "53" in out
    assert "声呐" in out and "合并" in out


def test_spreadsheetml_without_content_fails_readable(tmp_path):
    empty_workbook = SPREADSHEETML.split("<Row>")[0] + "</Table></Worksheet></Workbook>"
    path = tmp_path / "空表.xls"
    path.write_text(empty_workbook, encoding="utf-8")

    with pytest.raises(ValueError, match="未解析出任何表格内容"):
        _convert_legacy_excel_to_markdown(path)


def test_html_table_masquerading_as_xls(tmp_path):
    path = tmp_path / "网页另存.xls"
    path.write_text(
        "<html><body><table><tr><th>名称</th><th>数量</th></tr><tr><td>报表</td><td>12</td></tr></table></body></html>",
        encoding="utf-8",
    )

    _xlrd_fails(path)
    out = _convert_legacy_excel_to_markdown(path)
    assert "名称" in out and "报表" in out


def test_unrecognizable_content_fails_readable(tmp_path):
    path = tmp_path / "损坏.xls"
    path.write_bytes(b"this is not a workbook at all")

    with pytest.raises(ValueError, match="另存为 .xlsx"):
        _convert_legacy_excel_to_markdown(path)
