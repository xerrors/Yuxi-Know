#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PaddleX 文档分析使用示例
演示如何使用 analyze_document 函数分析文档
"""

from paddlex_layout_parser import analyze_document
import json


def analyze_custom_file(file_path: str):
    """分析自定义文件的示例函数"""

    print(f"\n🔍 分析自定义文件: {file_path}")

    result = analyze_document(file_path=file_path)

    if result["success"]:
        return result
    else:
        print(f"❌ 分析失败: {result['error']}")
        return None


if __name__ == "__main__":
    # main()

    # 如果您想分析其他文件，可以取消注释下面的代码
    custom_file = "test/struct_pdf/P020241226617572090546.pdf"
    custom_file = "test/data/PixPin_2025-06-19_23-42-17.png"
    print(analyze_custom_file(custom_file))