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
import unicodedata
from xml.etree import ElementTree as ET

# 旧标点字符集 — 在句读处理前需从原文中清除的所有标点
_OLD_PUNCT_CHARS: set[str] = {
    # CJK Symbols and Punctuation (U+3000-U+303F)
    '、',  # 、 IDEOGRAPHIC COMMA
    '。',  # 。 IDEOGRAPHIC FULL STOP
    '〈',  # 〈 LEFT ANGLE BRACKET
    '〉',  # 〉 RIGHT ANGLE BRACKET
    '《',  # 《 LEFT DOUBLE ANGLE BRACKET
    '》',  # 》 RIGHT DOUBLE ANGLE BRACKET
    '「',  # 「 LEFT CORNER BRACKET
    '」',  # 」 RIGHT CORNER BRACKET
    '『',  # 『 LEFT WHITE CORNER BRACKET
    '』',  # 』 RIGHT WHITE CORNER BRACKET
    '【',  # 【 LEFT BLACK LENTICULAR BRACKET
    '】',  # 】 RIGHT BLACK LENTICULAR BRACKET
    '〔',  # 〔 LEFT TORTOISE SHELL BRACKET
    '〕',  # 〕 RIGHT TORTOISE SHELL BRACKET
    '〖',  # 〖 LEFT WHITE LENTICULAR BRACKET
    '〗',  # 〗 RIGHT WHITE LENTICULAR BRACKET
    '〜',  # 〜 WAVE DASH
    '〝',  # 〝 REVERSED DOUBLE PRIME QUOTATION MARK
    '〞',  # 〞 DOUBLE PRIME QUOTATION MARK
    '〰',  # 〰 WAVY DASH
    '〽',  # 〽 PART ALTERNATION MARK
    # Fullwidth Forms (U+FF00-U+FFEF) — punctuation subset
    '！',  # ！ FULLWIDTH EXCLAMATION MARK
    '＂',  # ＂ FULLWIDTH QUOTATION MARK
    '＇',  # ＇ FULLWIDTH APOSTROPHE
    '（',  # （ FULLWIDTH LEFT PARENTHESIS
    '）',  # ） FULLWIDTH RIGHT PARENTHESIS
    '，',  # ， FULLWIDTH COMMA
    '．',  # ． FULLWIDTH FULL STOP
    '：',  # ： FULLWIDTH COLON
    '；',  # ； FULLWIDTH SEMICOLON
    '？',  # ？ FULLWIDTH QUESTION MARK
    '［',  # ［ FULLWIDTH LEFT SQUARE BRACKET
    '］',  # ］ FULLWIDTH RIGHT SQUARE BRACKET
    '｛',  # ｛ FULLWIDTH LEFT CURLY BRACKET
    '｝',  # ｝ FULLWIDTH RIGHT CURLY BRACKET
    '～',  # ～ FULLWIDTH TILDE
    # CJK Compatibility Forms (U+FE30-U+FE4F)
    '︰',  # ︰ PRESENTATION FORM FOR VERTICAL TWO DOT LEADER
    '︱',  # ︱ PRESENTATION FORM FOR VERTICAL EM DASH
    '︳',  # ︳ PRESENTATION FORM FOR VERTICAL LOW LINE
    '︴',  # ︴ PRESENTATION FORM FOR VERTICAL WAVY LOW LINE
    '︵',  # ︵ PRESENTATION FORM FOR VERTICAL LEFT PARENTHESIS
    '︶',  # ︶ PRESENTATION FORM FOR VERTICAL RIGHT PARENTHESIS
    '︷',  # ︷ PRESENTATION FORM FOR VERTICAL LEFT CURLY BRACKET
    '︸',  # ︸ PRESENTATION FORM FOR VERTICAL RIGHT CURLY BRACKET
    '︹',  # ︹ PRESENTATION FORM FOR VERTICAL LEFT TORTOISE SHELL BRACKET
    '︺',  # ︺ PRESENTATION FORM FOR VERTICAL RIGHT TORTOISE SHELL BRACKET
    '︻',  # ︻ PRESENTATION FORM FOR VERTICAL LEFT BLACK LENTICULAR BRACKET
    '︼',  # ︼ PRESENTATION FORM FOR VERTICAL RIGHT BLACK LENTICULAR BRACKET
    '︽',  # ︽ PRESENTATION FORM FOR VERTICAL LEFT DOUBLE ANGLE BRACKET
    '︾',  # ︾ PRESENTATION FORM FOR VERTICAL RIGHT DOUBLE ANGLE BRACKET
    '︿',  # ︿ PRESENTATION FORM FOR VERTICAL LEFT ANGLE BRACKET
    '﹀',  # ﹀ PRESENTATION FORM FOR VERTICAL RIGHT ANGLE BRACKET
    '﹁',  # ﹁ PRESENTATION FORM FOR VERTICAL LEFT CORNER BRACKET
    '﹂',  # ﹂ PRESENTATION FORM FOR VERTICAL RIGHT CORNER BRACKET
    '﹃',  # ﹃ PRESENTATION FORM FOR VERTICAL LEFT WHITE CORNER BRACKET
    '﹄',  # ﹄ PRESENTATION FORM FOR VERTICAL RIGHT WHITE CORNER BRACKET
    '﹏',  # ﹏ WAVY LOW LINE
    # General punctuation
    '‘',  # ' LEFT SINGLE QUOTATION MARK
    '’',  # ' RIGHT SINGLE QUOTATION MARK
    '“',  # " LEFT DOUBLE QUOTATION MARK
    '”',  # " RIGHT DOUBLE QUOTATION MARK
    '…',  # … HORIZONTAL ELLIPSIS
    '‥',  # ‥ TWO DOT LEADER
    # ASCII punctuation (English)
    ',', '.', '!', '?', ':', ';', '"', "'", '(', ')', '[', ']', '{', '}', '<', '>',
    '-', '—', '–', '/', '\\', '|', '@', '#', '$', '%', '^', '&', '*', '+', '=', '`',
    '~',
}


def _is_old_punct(ch: str) -> bool:
    """判断字符是否为旧标点，即句读处理中需要从原文清除的标点符号。"""
    if len(ch) != 1:
        return False
    return ch in _OLD_PUNCT_CHARS


def _is_unicode_whitespace(ch: str) -> bool:
    """判断字符是否为 Unicode 空白/控制字符（IDML 中的布局空白）。

    U+3000（全角空格）保留，因为它在佛经偈颂中用于分字。
    """
    if len(ch) != 1:
        return False
    cp = ord(ch)
    # U+3000 ideographic space is CONTENT (used in verses), not whitespace to strip
    if cp == 0x3000:
        return False
    # ASCII whitespace
    if ch in '\n\r\t ':
        return True
    # Unicode line/paragraph separators
    if cp in (0x2028, 0x2029):
        return True
    # Unicode whitespace category check
    try:
        cat = unicodedata.category(ch)
        # Zs = space separator, Zl = line separator, Zp = paragraph separator
        # Cc = control characters
        if cat in ('Zs', 'Zl', 'Zp', 'Cc'):
            return True
    except ValueError:
        pass
    return False


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
                'is_punct': is_punct or _is_old_punct(ch),
                'is_special': False,
                'style': style_template,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })

    # 去除段落末尾的全角空格（IDML 布局留白，TXT 导出时会忽略）
    while chars and chars[-1]['char'] == '　':
        chars.pop()

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


def extract_from_result(md_path: str) -> list[str]:
    """
    从句读结果 MD 文件提取字符序列。
    - 跳过文件头（# 标题到第一个 --- 之间的元数据）
    - 忽略换行、空格等 ASCII 空白字符
    - 保留可见字符（含「。」和全角空格 U+3000）

    返回: 字符列表，如 ['如', '是', '我', '聞', '。', '一', '時', '。', ...]
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 跳过文件头（# 标题 到 第一个 --- 之间的内容）
    parts = content.split('---', 1)
    body = parts[1] if len(parts) > 1 else content

    # 仅过滤 ASCII 空白字符（空格、制表符、换行、回车）
    # 保留全角空格 U+3000（佛经偈颂中的分字空格）等 Unicode 空白
    chars = [ch for ch in body if ch not in '\n\r\t ']

    return chars


def validate_and_align(stories: list[dict], result_chars: list[str]) -> dict:
    """
    验证 IDML 净文字与句读结果净文字一致，然后执行字符级对齐。

    核心逻辑：
    - IDML 的非标点、非特殊标记字符在句读结果中必有对应
    - 句读结果中新增的「。」插入在对应位置，归属上一字符的段落
    - 对齐后的每个 new_record 都标记了所属的 (story_idx, para_idx)

    返回: grouped_records，结构为 {story_idx: {para_idx: [records]}}
    """
    # 扁平化所有 IDML 字符记录
    # 跳过内容过少的故事（装饰性元素，如页眉标题、译者信息等）
    # 这些装饰故事的内容不在句读结果中，不应参与对齐
    _MIN_CLEAN_CHARS_PER_STORY = 50
    all_idml_records: list[dict] = []
    for story in stories:
        # 检查此 story 是否有足够的正文内容
        story_clean_count = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean_count < _MIN_CLEAN_CHARS_PER_STORY:
            continue
        for para in story['paragraphs']:
            for rec in para['chars']:
                all_idml_records.append(rec)

    # 提取 IDML 净文字（跳过旧标点、特殊标记如 <?ACE 18?>、以及 Unicode 布局空白）
    idml_clean_indices: list[int] = []
    for i, rec in enumerate(all_idml_records):
        ch = rec['char']
        if rec['is_punct'] or rec.get('is_special', False):
            continue
        if _is_unicode_whitespace(ch):
            continue
        idml_clean_indices.append(i)

    idml_clean_chars = [all_idml_records[i]['char'] for i in idml_clean_indices]
    result_clean_chars = [c for c in result_chars if c != '。']

    # 逐字比对验证
    idml_clean_str = ''.join(idml_clean_chars)
    result_clean_str = ''.join(result_clean_chars)

    if idml_clean_str != result_clean_str:
        # 找到第一个差异位置
        min_len = min(len(idml_clean_str), len(result_clean_str))
        for i in range(min_len):
            a = idml_clean_str[i]
            b = result_clean_str[i]
            if a != b:
                ctx = max(0, i - 20)
                raise ValueError(
                    f"字数验证失败！\n"
                    f"IDML 净文字数: {len(idml_clean_str)}\n"
                    f"句读结果净文字数: {len(result_clean_str)}\n"
                    f"第一个差异在位置 {i}:\n"
                    f"  IDML: ...{idml_clean_str[ctx:i+20]}...\n"
                    f"  结果: ...{result_clean_str[ctx:i+20]}...\n"
                    f"  IDML 字符: '{a}' (U+{ord(a):04X})\n"
                    f"  结果字符: '{b}' (U+{ord(b):04X})"
                )
        raise ValueError(
            f"字数验证失败！IDML: {len(idml_clean_str)} 字, "
            f"结果: {len(result_clean_str)} 字"
        )

    print(f"验证通过: {len(idml_clean_str)} 字一致")

    # 对齐: 遍历句读结果，每个字符映射到对应的 IDML 段落和样式
    clean_idx = 0          # 在 idml_clean_indices 中的位置
    last_para = None       # 上一个字符的 (story_idx, para_idx)
    new_records: list[dict] = []
    punct_style = _find_punct_style(all_idml_records)

    for ch in result_chars:
        if ch == '。':
            # 新增句号：归属到上一个字符的段落
            story_idx, para_idx = last_para if last_para else (0, 0)
            new_records.append({
                'char': '。',
                'is_punct': True,
                'is_special': False,
                'style': punct_style,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
        else:
            # 普通文字：映射到对应 IDML 字符的样式和段落
            target_idx = idml_clean_indices[clean_idx]
            orig_rec = all_idml_records[target_idx]

            new_records.append({
                'char': ch,
                'is_punct': False,
                'is_special': False,
                'style': orig_rec['style'],
                'story_idx': orig_rec['story_idx'],
                'para_idx': orig_rec['para_idx'],
            })

            last_para = (orig_rec['story_idx'], orig_rec['para_idx'])
            clean_idx += 1

    # 按 (story_idx, para_idx) 分组
    grouped: dict = {}  # {story_idx: {para_idx: [records]}}
    for rec in new_records:
        si = rec['story_idx']
        pi = rec['para_idx']
        if si not in grouped:
            grouped[si] = {}
        if pi not in grouped[si]:
            grouped[si][pi] = []
        grouped[si][pi].append(rec)

    punct_count = sum(1 for r in new_records if r['is_punct'])
    print(f"对齐完成: {len(new_records)} 个字符（含 {punct_count} 个句号）")

    return grouped


def _find_punct_style(all_records: list[dict]) -> str | None:
    """查找 IDML 中已有的句号样式模板"""
    for rec in all_records:
        if rec['is_punct'] and rec.get('style'):
            return rec['style']
    # 如果找不到，返回 None（后续生成 IDML 时使用默认样式）
    return None


if __name__ == "__main__":
    main()
