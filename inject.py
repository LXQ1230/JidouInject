#!/usr/bin/env python3
"""
IDML 句读结果回注工具
将 _WD句读结果.md 中的文字和「。」注入回 IDML，排版样式原封不动。

用法:
    python inject.py --idml 275导出.idml --result 275从ID中导出文字_WD句读结果.md
    或拖拽两个文件到 inject.bat 上
"""

import sys
import os
import re
import argparse
import shutil
import tempfile
import zipfile
from xml.etree import ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description="IDML 句读结果回注工具")
    parser.add_argument("--idml", required=True, help="原始 IDML 文件路径")
    parser.add_argument("--result", required=True, help="句读结果 MD 文件路径")
    parser.add_argument("--output", help="输出 IDML 路径（默认自动生成）")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(args.idml)[0]
        args.output = f"{base}_WD注入.idml"

    print(f"输入 IDML: {args.idml}")
    print(f"句读结果: {args.result}")
    print(f"输出文件: {args.output}")

    process(args.idml, args.result, args.output)


def process(idml_path, result_path, output_path):
    """主处理流程"""
    # Step 1: 从 IDML 提取字符记录
    stories = extract_from_idml(idml_path)
    # Step 2: 从句读结果提取字符
    result_chars = extract_from_result(result_path)
    # Step 3: 验证并对齐
    new_stories = validate_and_align(stories, result_chars)
    # Step 4: 生成新 IDML
    generate_idml(idml_path, new_stories, output_path)
    print(f"完成！输出: {output_path}")


if __name__ == "__main__":
    main()
