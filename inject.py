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


def extract_from_idml(idml_path: str) -> list[dict]:
    """
    从 IDML 中提取所有文字及其样式信息。

    返回: stories — 列表，每个元素是一个 story 的信息字典:
          {
            'name': story_name,       # str
            'path': story_path,       # str
            'xml_header': str,        # Story XML 头部（第一个 PSR 前的内容）
            'xml_footer': str,        # Story XML 尾部（最后一个 PSR 后的内容）
            'paragraphs': [           # 列表
              {
                'chars': [char_record, ...],
                'raw_xml': str,       # 原始 ParagraphStyleRange XML
              },
              ...
            ],
          }
          char_record = {
            'char': str,
            'is_punct': bool,
            'style': str | None,    # CharacterStyleRange XML 模板（Content 替换为 {content}）
            'story_idx': int,
            'para_idx': int,
            'is_special': bool,
          }
    """
    stories: list[dict] = []

    with zipfile.ZipFile(idml_path, 'r') as zf:
        # 读取 designmap.xml 获取 Story 顺序
        designmap = zf.read('designmap.xml').decode('utf-8')
        story_order = _parse_story_order(designmap)

        # 读取每个 Story XML
        for story_idx, story_name in enumerate(story_order):
            story_path = f'Stories/Story_{story_name}.xml'
            if story_path not in zf.namelist():
                continue

            story_xml = zf.read(story_path).decode('utf-8')
            paragraphs = _parse_story_xml(story_xml, story_idx)
            stories.append({
                'name': story_name,
                'path': story_path,
                'xml_header': _get_story_header(story_xml),
                'xml_footer': _get_story_footer(story_xml),
                'paragraphs': paragraphs,
            })

    return stories


def _parse_story_order(designmap_xml: str) -> list[str]:
    """从 designmap.xml 提取 StoryList 属性中的 Story 顺序"""
    match = re.search(r'StoryList="([^"]*)"', designmap_xml)
    if match:
        return match.group(1).split()
    return []


def _parse_story_xml(story_xml: str, story_idx: int) -> list[dict]:
    """
    解析一个 Story XML，返回该 story 中的所有段落。
    """
    paragraphs: list[dict] = []

    pattern = r'(<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>)'
    for para_idx, match in enumerate(re.finditer(pattern, story_xml, re.DOTALL)):
        psr_xml = match.group(1)
        chars = _parse_paragraph_style_range(psr_xml, story_idx, para_idx)
        paragraphs.append({'chars': chars, 'raw_xml': psr_xml})

    return paragraphs


def _parse_paragraph_style_range(
    psr_xml: str, story_idx: int, para_idx: int
) -> list[dict]:
    """
    从 ParagraphStyleRange XML 中提取所有字符记录。
    每个记录标记其所属的 story 和 paragraph，用于后续按段落重建。
    """
    chars: list[dict] = []

    csr_pattern = r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)'

    for match in re.finditer(csr_pattern, psr_xml, re.DOTALL):
        attrs_str = match.group(1)
        inner = match.group(2) if match.group(2) else ''

        is_punct = 'CharacterStyle/句号' in attrs_str or 'CharacterStyle/句号' in inner

        content_match = re.search(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        if content_match:
            content_text = content_match.group(1)
        else:
            continue

        # 特殊加工指令（如 <?ACE 18?>）
        if re.match(r'<\?ACE\s', content_text):
            chars.append({
                'char': content_text,
                'is_punct': False,
                'is_special': True,
                'style': None,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
            continue

        # 生成样式模板 — 在完整的 CSR XML 中搜索 Content 元素位置
        full_csr_xml = match.group(0)
        full_content_match = re.search(
            r'<Content>(.*?)</Content>', full_csr_xml, re.DOTALL
        )
        if full_content_match:
            style_template = (
                full_csr_xml[:full_content_match.start()]
                + '{content}'
                + full_csr_xml[full_content_match.end():]
            )
        else:
            style_template = full_csr_xml

        for ch in content_text:
            chars.append({
                'char': ch,
                'is_punct': is_punct,
                'is_special': False,
                'style': style_template,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })

    return chars


def _get_story_header(story_xml: str) -> str:
    """提取 Story XML 从开头到第一个 ParagraphStyleRange 之前的内容"""
    match = re.search(r'<ParagraphStyleRange', story_xml)
    if match:
        return story_xml[:match.start()]
    return story_xml


def _get_story_footer(story_xml: str) -> str:
    """提取 Story XML 最后一个 ParagraphStyleRange 之后的内容"""
    # 找到最后一个 </ParagraphStyleRange> 的位置
    last_end = 0
    for m in re.finditer(r'</ParagraphStyleRange>', story_xml):
        last_end = m.end()
    if last_end > 0:
        return story_xml[last_end:]
    return ''


if __name__ == "__main__":
    main()
