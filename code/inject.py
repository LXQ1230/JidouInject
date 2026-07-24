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
import zipfile
import unicodedata

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
    # 〔 〕 不属于旧标点——在佛经中常用于校勘标注（如〔云〕表校订补充）
    # 〖 〗 不属于旧标点——与 〔 〕 同为校勘标注标记
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


def _is_ws_for_compare(ch: str) -> bool:
    """判断字符是否为比对时应忽略的空白。

    与 _is_unicode_whitespace() 不同，此函数将 U+3000（全角空格）也视为空白。
    比对和字符对齐时使用，确保句读结果中的空格差异不影响文字匹配。
    IDML 原文中的空格原样保留在输出中。
    """
    if _is_unicode_whitespace(ch):
        return True
    if ord(ch) == 0x3000:
        return True
    return False


def resolve_conflicts(conflicts: dict[str, str]) -> dict[str, str]:
    """冲突检测与处理。

    Args:
        conflicts: {路径: 描述} 映射，如 {'output/275导出_WD注入.idml': '输出文件'}

    Returns:
        {路径: 操作} 映射，操作: 'overwrite' | 'rename_v2' | 'skip'
    """
    if not conflicts:
        return {}

    print("\n[!] 检测到以下文件已存在：\n")
    items = list(conflicts.items())
    for i, (path, desc) in enumerate(items, 1):
        print(f"  [{i}] {path}")
        print(f"      {desc}")

    print("\n请选择处理方式：")
    print("  A  全部覆盖")
    print("  S  全部跳过")
    print("  R  全部自动重命名（加 _v2, _v3 后缀）")
    print("  C  逐个确认")

    while True:
        choice = input("\n> ").strip().upper()
        result: dict[str, str] = {}

        if choice == 'A':
            return {path: 'overwrite' for path in conflicts}
        elif choice == 'S':
            return {path: 'skip' for path in conflicts}
        elif choice == 'R':
            return {path: 'rename_v2' for path in conflicts}
        elif choice == 'C':
            for path, desc in items:
                while True:
                    sub = input(f"  {path}\n  [O]覆盖 [S]跳过 [R]重命名 [Q]取消全部 > ").strip().upper()
                    if sub == 'O':
                        result[path] = 'overwrite'
                        break
                    elif sub == 'S':
                        result[path] = 'skip'
                        break
                    elif sub == 'R':
                        result[path] = 'rename_v2'
                        break
                    elif sub == 'Q':
                        print("  已取消")
                        sys.exit(0)
            return result
        else:
            print("  无效选项，请重新输入")


def _resolve_output_path(path: str, action: str) -> str | None:
    """根据冲突处理结果返回最终输出路径。

    Returns:
        最终路径，或 None 表示跳过
    """
    if action == 'skip':
        return None
    if action == 'rename_v2':
        base, ext = os.path.splitext(path)
        v = 2
        while os.path.exists(f"{base}_v{v}{ext}"):
            v += 1
        return f"{base}_v{v}{ext}"
    return path  # overwrite


def main():
    parser = argparse.ArgumentParser(description="IDML 句读结果回注工具")
    parser.add_argument("--idml", required=True, help="原始 IDML 文件路径")
    parser.add_argument("--result", required=True, help="句读结果 MD 文件路径")
    parser.add_argument("--output", help="输出 IDML 路径（默认自动生成）")
    args = parser.parse_args()

    # 输入文件存在性检查
    if not os.path.isfile(args.idml):
        print(f"错误: IDML 文件不存在: {args.idml}")
        sys.exit(1)
    if not os.path.isfile(args.result):
        print(f"错误: 句读结果文件不存在: {args.result}")
        sys.exit(1)

    # IDML 文件基本校验（是否为有效 ZIP）
    try:
        with zipfile.ZipFile(args.idml, 'r') as zf:
            if 'designmap.xml' not in zf.namelist():
                print(f"错误: 文件不是有效的 IDML（缺少 designmap.xml）: {args.idml}")
                sys.exit(1)
    except zipfile.BadZipFile:
        print(f"错误: 文件不是有效的 ZIP/IDML 文件: {args.idml}")
        sys.exit(1)

    if args.output is None:
        base = os.path.splitext(args.idml)[0]
        args.output = f"{base}_WD注入.idml"

    print(f"输入 IDML: {args.idml}")
    print(f"句读结果: {args.result}")
    print(f"输出文件: {args.output}")

    # 冲突检测
    if os.path.exists(args.output):
        conflicts = {args.output: "输出文件已存在"}
        decisions = resolve_conflicts(conflicts)
        resolved = _resolve_output_path(args.output, decisions[args.output])
        if resolved is None:
            print("已跳过")
            sys.exit(0)
        args.output = resolved

    try:
        process(args.idml, args.result, args.output)
    except ValueError as e:
        print(f"\n处理失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


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
            'story_idx': int,
            'para_idx': int,
            'csr_idx': int,        # 属于段落中第几个 CSR
            'content_slot': int,   # 属于 CSR 中第几个 <Content>
            'is_special': bool,
          }
    """
    stories: list[dict] = []
    raw_story_xmls: dict[str, str] = {}  # 保留原始 XML 用于自检

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
            raw_story_xmls[story_name] = story_xml
            paragraphs = _parse_story_xml(story_xml, story_idx)
            stories.append({
                'name': story_name,
                'path': story_path,
                'xml_header': _get_story_header(story_xml),
                'xml_footer': _get_story_footer(story_xml),
                'paragraphs': paragraphs,
            })

    # 自检：直接用正则从原始 XML 提取全部 Content 文本，
    # 与解析器提取结果比对，确保没有任何字符被漏掉
    _verify_extraction(stories, raw_story_xmls)

    return stories


def _parse_story_order(designmap_xml: str) -> list[str]:
    """从 designmap.xml 提取 StoryList 属性中的 Story 顺序"""
    match = re.search(r'StoryList="([^"]*)"', designmap_xml)
    if match:
        return match.group(1).split()
    return []


def _verify_extraction(stories: list[dict], raw_story_xmls: dict[str, str]) -> None:
    """自检：确保解析器没有遗漏任何 Content 文本。

    独立于主解析逻辑，直接用正则从原始 Story XML 中提取所有
    <Content>...</Content> 文本，与解析器产出的净文字逐 Story 比对。
    任何不一致都会抛出 ValueError，阻止静默的数据丢失。
    """
    for story in stories:
        story_name = story['name']
        raw_xml = raw_story_xmls.get(story_name)
        if raw_xml is None:
            continue

        # 直接从原始 XML 提取全部 Content 文本（不依赖解析器）
        raw_contents = re.findall(r'<Content>(.*?)</Content>', raw_xml, re.DOTALL)
        # 去除加工指令（如 <?ACE 18?>），与解析器行为一致
        raw_text = re.sub(r'<\?.*?\?>', '', ''.join(raw_contents))
        # 模拟解析器的段落末尾全角空格去除：
        # 解析器在每个 ParagraphStyleRange 末尾去除尾随的 U+3000，
        # 这里按 ParagraphStyleRange 边界分割后各自 rstrip
        raw_filtered: list[str] = []
        for psr_match in re.finditer(
            r'<ParagraphStyleRange[^>]*>(.*?)</ParagraphStyleRange>',
            raw_xml, re.DOTALL
        ):
            psr_contents = re.findall(
                r'<Content>(.*?)</Content>', psr_match.group(1), re.DOTALL
            )
            psr_text = re.sub(r'<\?.*?\?>', '', ''.join(psr_contents))
            # 去除段落末尾的全角空格（与解析器行为一致）
            psr_text = psr_text.rstrip('　')
            for ch in psr_text:
                if _is_old_punct(ch):
                    continue
                if _is_unicode_whitespace(ch):
                    continue
                raw_filtered.append(ch)

        # 从解析器结果收集全部字符（与上述 raw_filtered 使用相同过滤规则）
        parsed_filtered: list[str] = []
        for para in story['paragraphs']:
            for rec in para['chars']:
                ch = rec['char']
                if rec.get('is_special', False):
                    continue
                if _is_old_punct(ch):
                    continue
                if _is_unicode_whitespace(ch):
                    continue
                parsed_filtered.append(ch)

        raw_str = ''.join(raw_filtered)
        parsed_str = ''.join(parsed_filtered)

        if raw_str != parsed_str:
            # 定位第一个差异
            min_len = min(len(raw_str), len(parsed_str))
            for i in range(min_len):
                if raw_str[i] != parsed_str[i]:
                    ctx_start = max(0, i - 30)
                    ctx_end = min(min_len, i + 30)
                    raise ValueError(
                        f"IDML 解析自检失败！Story '{story_name}' 提取结果与原始 XML 不一致。\n"
                        f"原始 XML Content 净字数: {len(raw_str)}\n"
                        f"解析器提取净字数:     {len(parsed_str)}\n"
                        f"第一个差异在位置 {i}:\n"
                        f"  原始 XML: ...{raw_str[ctx_start:ctx_end]}...\n"
                        f"  解析器:   ...{parsed_str[ctx_start:ctx_end]}...\n"
                        f"  原始字符: U+{ord(raw_str[i]):04X} ('{raw_str[i]}')\n"
                        f"  解析字符: U+{ord(parsed_str[i]):04X} ('{parsed_str[i]}')\n"
                        f"这通常意味着解析器遗漏了某种 XML 结构。"
                    )
            raise ValueError(
                f"IDML 解析自检失败！Story '{story_name}' 净字数不一致: "
                f"原始 XML {len(raw_str)} vs 解析器 {len(parsed_str)}"
            )


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
    """从 ParagraphStyleRange XML 中提取所有字符记录。

    每个记录标记其所属的 story、paragraph、CSR 索引和 Content 槽位。
    """
    chars: list[dict] = []

    csr_pattern = r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)'
    csr_idx = 0

    for match in re.finditer(csr_pattern, psr_xml, re.DOTALL):
        inner = match.group(2) if match.group(2) else ''

        # 找到此 CSR 内所有的 <Content> 元素
        content_matches = list(
            re.finditer(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        )

        if not content_matches:
            # 无 Content → 可能是纯 Br CSR。csr_idx 仍需递增以保证
            # 后续 CSR 的索引正确，但不产生任何字符记录
            csr_idx += 1
            continue

        # 每个 <Content> → 一组字符，打上槽位标签
        for slot_idx, cm in enumerate(content_matches):
            content_text = cm.group(1)

            # 特殊加工指令（如 <?ACE 18?>）
            if re.match(r'<\?ACE\s', content_text):
                chars.append({
                    'char': content_text,
                    'is_punct': False,
                    'is_special': True,
                    'story_idx': story_idx,
                    'para_idx': para_idx,
                    'csr_idx': csr_idx,
                    'content_slot': slot_idx,
                })
                continue

            for ch in content_text:
                chars.append({
                    'char': ch,
                    'is_punct': _is_old_punct(ch),
                    'is_special': False,
                    'story_idx': story_idx,
                    'para_idx': para_idx,
                    'csr_idx': csr_idx,
                    'content_slot': slot_idx,
                })

        csr_idx += 1

    # 去除段落末尾的全角空格
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


def extract_from_result(md_path: str) -> dict:
    """
    从句读结果 MD 文件提取字符序列和段落边界。

    - 跳过文件头（# 标题到第一个 --- 之间的元数据）
    - 忽略空格、制表符等 ASCII 空白字符
    - 保留可见字符（含「。」和全角空格 U+3000）
    - 检测空行作为段落边界标记

    返回: {
        'chars': 字符列表，如 ['如', '是', '我', '聞', '。', '一', '時', '。', ...],
        'para_breaks': set of int — chars 中的位置索引，表示段落边界
                        （边界在位置 i 表示 chars[i] 是新段落的第一个字符）
    }
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 跳过文件头（# 标题 到 第一个 --- 之间的内容）
    parts = content.split('---', 1)
    body = parts[1] if len(parts) > 1 else content

    # 逐行处理，检测空行作为段落边界
    lines = body.replace('\r', '').split('\n')
    chars: list[str] = []
    para_breaks: set[int] = set()

    for line in lines:
        # 过滤空格和制表符（但保留全角空格 U+3000）
        line_chars = [ch for ch in line if ch not in '\t ']
        if line_chars:
            chars.extend(line_chars)
        else:
            # 空行 → 段落边界标记（跳过文件开头的空行）
            if chars:
                para_breaks.add(len(chars))

    return {'chars': chars, 'para_breaks': para_breaks}


def validate_and_align(stories: list[dict], result_data: dict) -> dict:
    """
    验证 IDML 净文字与句读结果净文字一致，然后执行字符级对齐。

    核心逻辑：
    - IDML 的非标点、非特殊标记字符在句读结果中必有对应
    - 句读结果中新增的「。」插入在对应位置，归属上一字符的段落
    - 对齐后的每个 new_record 都标记了所属的 (story_idx, para_idx)
    - 句读结果中的空行（段落边界）会触发 IDML 段落分割：
      边界位置的字符及其后续内容分配到新的虚拟段落

    返回: grouped_records，结构为 {story_idx: {para_idx: [records]}}
    """
    result_chars: list[str] = result_data['chars']
    para_breaks: set[int] = result_data['para_breaks']

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

    # 提取 IDML 净文字（跳过旧标点、特殊标记如 <?ACE 18?>）
    # 注意：全角空格 U+3000 保留在 idml_clean_indices 中，因为 IDML 的所有空白
    # 都是排版的一部分，应原样保留在输出中
    idml_clean_indices: list[int] = []
    for i, rec in enumerate(all_idml_records):
        ch = rec['char']
        if rec['is_punct'] or rec.get('is_special', False):
            continue
        if _is_unicode_whitespace(ch):
            continue
        idml_clean_indices.append(i)

    # 比对用的净文字：双方都排除比对空白（含 U+3000）
    idml_compare_chars = [
        all_idml_records[i]['char'] for i in idml_clean_indices
        if not _is_ws_for_compare(all_idml_records[i]['char'])
    ]
    result_compare_chars = [c for c in result_chars if c != '。' and not _is_ws_for_compare(c)]

    # 逐字比对验证（排除空白字符）
    idml_compare_str = ''.join(idml_compare_chars)
    result_compare_str = ''.join(result_compare_chars)

    if idml_compare_str != result_compare_str:
        # 找到第一个差异位置
        min_len = min(len(idml_compare_str), len(result_compare_str))
        for i in range(min_len):
            a = idml_compare_str[i]
            b = result_compare_str[i]
            if a != b:
                ctx_start = max(0, i - 50)
                ctx_end = min(min_len, i + 50)
                raise ValueError(
                    f"字数验证失败！\n"
                    f"IDML 净文字数（不含空白）: {len(idml_compare_str)}\n"
                    f"句读结果净文字数（不含空白）: {len(result_compare_str)}\n"
                    f"第一个差异在位置 {i} (上下文 {ctx_start}-{ctx_end}):\n"
                    f"  IDML: ...{idml_compare_str[ctx_start:ctx_end]}...\n"
                    f"  结果: ...{result_compare_str[ctx_start:ctx_end]}...\n"
                    f"  IDML @{i}: U+{ord(a):04X} ('{a}')\n"
                    f"  结果 @{i}: U+{ord(b):04X} ('{b}')\n"
                    f"提示: 句读结果与 IDML 原文不一致，"
                    f"请确认结果文件是从该 IDML 导出的文本生成的。"
                )
        raise ValueError(
            f"字数验证失败！IDML: {len(idml_compare_str)} 字, "
            f"结果: {len(result_compare_str)} 字（内容相同但长度不同）"
        )

    print(f"验证通过: {len(idml_compare_str)} 字一致")

    # 对齐: 遍历句读结果
    # 段落分割策略：
    # - 每个原始段落有一个"当前有效 para_idx"，初始为原始 para_idx
    # - 当遇到空行边界时，该原始段落的"当前有效 para_idx"切换到新的唯一索引
    # - 这样分割产生的新字符不会与其他原始段落冲突
    #
    # 计算每个 story 的最大原始 para_idx 和初始有效索引
    orig_para_max: dict[int, int] = {}
    for rec in all_idml_records:
        si = rec['story_idx']
        pi = rec['para_idx']
        if si not in orig_para_max:
            orig_para_max[si] = pi
        else:
            orig_para_max[si] = max(orig_para_max[si], pi)

    # current_effective[(si, pi)] = 此原始段落当前的 effective para_idx
    current_effective: dict[tuple, int] = {}
    # next_new_idx[si] = 下一个可分配的唯一 para_idx
    next_new_idx: dict[int, int] = {}
    # split_sources[(si, effective_pi)] = original_pi（仅非原始索引的段落）
    new_split_sources: dict[tuple, int] = {}

    for si, max_pi in orig_para_max.items():
        next_new_idx[si] = max_pi + 1
        for pi in range(max_pi + 1):
            current_effective[(si, pi)] = pi

    idml_idx = 0
    last_slot = None       # (story_idx, para_idx, csr_idx, content_slot)
    new_records: list[dict] = []

    for i, ch in enumerate(result_chars):
        # 检测段落边界：切换当前原始段落的 effective para_idx
        if i in para_breaks and i > 0:
            if last_slot:
                si, pi = last_slot[0], last_slot[1]
                new_idx = next_new_idx.get(si, pi + 1)
                current_effective[(si, pi)] = new_idx
                new_split_sources[(si, new_idx)] = pi
                next_new_idx[si] = new_idx + 1

        if ch == '。':
            si, pi, ci, sl = last_slot if last_slot else (0, 0, 0, 0)
            effective_pi = current_effective.get((si, pi), pi)
            new_records.append({
                'char': '。',
                'is_punct': True,
                'is_special': False,
                'story_idx': si,
                'para_idx': effective_pi,
                'csr_idx': -1,
                'content_slot': -1,
                'after_csr': ci,
            })
        elif _is_ws_for_compare(ch):
            pass
        else:
            while idml_idx < len(idml_clean_indices):
                target_idx = idml_clean_indices[idml_idx]
                orig_rec = all_idml_records[target_idx]
                idml_idx += 1
                effective_pi = current_effective.get(
                    (orig_rec['story_idx'], orig_rec['para_idx']),
                    orig_rec['para_idx'],
                )
                if _is_ws_for_compare(orig_rec['char']):
                    last_slot = (orig_rec['story_idx'], orig_rec['para_idx'],
                                 orig_rec['csr_idx'], orig_rec['content_slot'])
                    new_records.append({
                        'char': orig_rec['char'],
                        'is_punct': False,
                        'is_special': False,
                        'story_idx': orig_rec['story_idx'],
                        'para_idx': effective_pi,
                        'csr_idx': orig_rec['csr_idx'],
                        'content_slot': orig_rec['content_slot'],
                    })
                else:
                    last_slot = (orig_rec['story_idx'], orig_rec['para_idx'],
                                 orig_rec['csr_idx'], orig_rec['content_slot'])
                    new_records.append({
                        'char': orig_rec['char'],
                        'is_punct': False,
                        'is_special': False,
                        'story_idx': orig_rec['story_idx'],
                        'para_idx': effective_pi,
                        'csr_idx': orig_rec['csr_idx'],
                        'content_slot': orig_rec['content_slot'],
                    })
                    break

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

    return {'grouped': grouped, 'split_sources': new_split_sources}


def _xml_escape(text: str) -> str:
    """转义 XML 特殊字符。

    将 & < > " ' 转义为对应的 XML 实体。
    注意：已在实体中的 & 号（如 &amp;）不会被二次转义，
    因为我们先替换 & 为 &amp;，后续替换不会匹配新生成的 &。
    """
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text


def _rebuild_paragraph_xml(
    original_psr_xml: str, new_char_records: list[dict],
    global_punct_template: str | None = None,
    is_split_copy: bool = False,
) -> str:
    """用槽位追踪 + CSR 拆分的方式重建 ParagraphStyleRange XML。

    当句读结果要求在同一个 CSR 内的两个字之间插入句号时，
    自动将原 CSR 拆分为多段，句号独立插入其间。

    Args:
        is_split_copy: 该段落是否为分割产生的新段落（模板副本）。
                       副本中的 Group 元素（有唯一 Self ID）必须清除
                       以避免与原始段落中的同一 ID 冲突。
    """
    if not new_char_records:
        return original_psr_xml

    # 1. 收集所有有效记录（文字 + 句号），排除空白标记
    all_records = [r for r in new_char_records
                   if not r.get('is_special', False)]

    # 2. 扫描原始 PSR XML
    csr_pattern = r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)'
    csr_list: list[dict] = []  # [{csr_idx, match_obj, is_punct, contents}]
    punct_template: str | None = None
    csr_idx = 0
    for m in re.finditer(csr_pattern, original_psr_xml, re.DOTALL):
        inner = m.group(2) or ''
        contents = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        csr_list.append({
            'idx': csr_idx,
            'match': m,
            'is_punct': (
                'CharacterStyle/句号' in m.group(1)
                or ''.join(contents) == '。'
            ),
            'contents': contents,
        })
        if csr_list[-1]['is_punct'] and csr_list[-1]['contents']:
            tmpl_xml = m.group(0)
            if '<Br' in tmpl_xml:
                tmpl_xml = re.sub(r'<Br\s*/>', '', tmpl_xml)  # 去 Br
            if punct_template is None:
                punct_template = tmpl_xml
            elif '。</Content>' in tmpl_xml and '。</Content>' not in punct_template:
                punct_template = tmpl_xml
        csr_idx += 1

    if punct_template is None or '。</Content>' not in punct_template:
        punct_template = global_punct_template

    # 3. 将记录按 csr_idx 分组（含句号：after_csr 指向它跟随的文字 CSR）
    # csr_texts: {csr_idx: [(is_punct, text), ...]} — 保持原始顺序
    csr_segments: dict[int, list[tuple[bool, str]]] = {}
    for rec in all_records:
        if rec.get('is_punct', False):
            ci = rec.get('after_csr', -1)
        else:
            ci = rec['csr_idx']
        if ci < 0:
            continue
        is_p = rec.get('is_punct', False)
        csr_segments.setdefault(ci, []).append((is_p, rec['char']))

    # 3.5 确定文字内容 CSR 的范围（用于区分 leading/trailing 清除区域）
    text_content_csrs = {
        ci for ci, segs in csr_segments.items()
        if any(not is_p for is_p, _ in segs) and not csr_list[ci]['is_punct']
    }
    min_text_idx = min(text_content_csrs) if text_content_csrs else 0
    max_text_idx = max(text_content_csrs) if text_content_csrs else len(csr_list) - 1

    # 3.6 预扫描：找到紧邻内容的第一尾饰 CSR（A2 规则）
    # 只在 max_text_idx 之后到第一个"曾有文字内容"的 CSR 之间搜索
    first_trailing_decoration: int | None = None
    for ci in range(max_text_idx + 1, len(csr_list)):
        cdata = csr_list[ci]
        if cdata['is_punct']:
            continue
        orig_had_text = any(
            c.strip() for c in cdata.get('contents', [])
        )
        if orig_had_text:
            break  # 遇到曾有文字的 CSR，不是装饰区
        has_br = '<Br' in cdata['match'].group(0)
        if has_br:
            first_trailing_decoration = ci
            break  # 找到第一个空+Br CSR，标记为紧邻尾饰

    # 4. 生成 CSR 级别的替换内容
    # csr_replacements: {csr_idx: replacement_xml_string}
    #
    # 无记录 CSR 的 Br 保留规则（优先级 A1→A2→A3→A3.5→A4）：
    #   A1. punct + trailing + 纯空白内容 + 有 Br → 保留（分隔符）
    #   A2. text + close-trailing + 原为空 + 有 Br → 保留（尾饰）
    #   A3. text + 分割副本 → 剥离 Br + Group
    #   A3.5. 中间 + 纯空白 + 有 Br → 保留（文字 CSR 之间的换行，如偈颂分行）
    #   A4. 其他 → 剥离 Br
    csr_replacements: dict[int, str] = {}
    for ci, cdata in enumerate(csr_list):
        segments = csr_segments.get(ci, [])
        if not segments:
            orig_csr = cdata['match'].group(0)
            has_br = '<Br' in orig_csr
            is_trailing = ci > max_text_idx
            is_leading = ci < min_text_idx
            is_close_trailing = (ci == first_trailing_decoration)
            is_punct = cdata['is_punct']
            orig_had_text = any(
                c.strip() for c in cdata.get('contents', [])
            )
            orig_all_ws = all(
                not c.strip() for c in cdata.get('contents', [])
            )

            if is_punct:
                # A1: 尾随 punct 分隔符（原始纯空白内容）→ 保留 Br
                if has_br and is_trailing and orig_all_ws:
                    csr_replacements[ci] = _clear_content_keep_br(
                        orig_csr, strip_groups=is_split_copy
                    )
                else:
                    csr_replacements[ci] = ''
            elif is_close_trailing and not orig_had_text:
                # A2: 紧邻内容尾部的空 CSR → 保留装饰 Br
                csr_replacements[ci] = _clear_content_keep_br(
                    orig_csr, strip_groups=is_split_copy
                )
            elif is_split_copy:
                # A3: 分割副本 → 全部剥离
                csr_replacements[ci] = _clear_content_strip_br(
                    orig_csr, strip_groups=True
                )
            elif not is_leading and not is_trailing and has_br and orig_all_ws:
                # A3.5: 中间区域（文字 CSR 之间）的空 + Br CSR → 保留
                # 如偈颂前换行、段落内分行等排版需求
                csr_replacements[ci] = _clear_content_keep_br(orig_csr)
            else:
                # A4: leading / 远 trailing / 其他 → 剥离 Br
                csr_replacements[ci] = _clear_content_strip_br(orig_csr)
            continue

        if cdata['is_punct']:
            # 旧句号 CSR：保留原 CSR 中的 Br，Content 用模板替换
            orig_csr = cdata['match'].group(0)
            has_br = '<Br' in orig_csr
            punct_segments = [t for is_p, t in segments if is_p]
            if not punct_segments:
                # 无新句号 → 清空 Content
                csr_replacements[ci] = (
                    _clear_content_keep_br(orig_csr, strip_groups=is_split_copy)
                    if has_br else ''
                )
            elif punct_template:
                fill = ''.join(punct_template for _ in punct_segments)
                if has_br:
                    # 模板可能无 Br → 在最后追加原 CSR 的 Br
                    br_match = re.search(r'<Br\s*/>', orig_csr)
                    if br_match and '<Br' not in fill:
                        fill += br_match.group(0)
                csr_replacements[ci] = fill
            continue

        # 文字 CSR：检查是否需要拆分
        match = cdata['match']
        csr_xml = match.group(0)
        content_start = csr_xml.find('<Content>')
        content_end = csr_xml.rfind('</Content>') + len('</Content>')
        csr_prefix = csr_xml[:content_start]
        csr_suffix = csr_xml[content_end:]

        orig_contents = cdata.get('contents', [])
        is_multi_content = len(orig_contents) > 1
        has_punct_inside = any(p for p, _ in segments)

        if is_multi_content:
            # 多 Content CSR：按原 Content 数量比例分配文字（含句号）
            orig_lens = [len(c) for c in orig_contents]
            total_orig = sum(orig_lens)
            new_text = ''.join(t for _, t in segments)
            if total_orig > 0:
                parts_xml = csr_xml
                pos = 0
                for oi, ol in enumerate(orig_lens):
                    if oi == len(orig_contents) - 1:
                        share = len(new_text) - pos
                    else:
                        share = max(1, len(new_text) * ol // total_orig)
                    part_text = new_text[pos:pos + share]
                    pos += share
                    old_ctag = f'<Content>{orig_contents[oi]}</Content>'
                    new_ctag = f'<Content>{_xml_escape(part_text)}</Content>'
                    parts_xml = parts_xml.replace(old_ctag, new_ctag, 1)
                # 分割副本：剥离多 Content 间的 Br
                # （原单段落的节标题格式在分割后不再适用）
                if is_split_copy:
                    parts_xml = re.sub(r'<Br\s*/>', '', parts_xml)
                csr_replacements[ci] = parts_xml
            else:
                csr_replacements[ci] = csr_xml
            continue

        if not has_punct_inside:
            # 单 Content、无拆分：全部文字合并
            text = ''.join(t for _, t in segments)
            csr_replacements[ci] = (
                csr_prefix
                + f'<Content>{_xml_escape(text)}</Content>'
                + csr_suffix
            )
        else:
            # 需要拆分：生成多个 CSR（文字 + 句号交错）
            # - csr_prefix（含 Br/Group）仅给第一个文本部分
            # - csr_suffix（含 Br）放在所有部分末尾
            # - 中间的文本部分和句号部分用干净前后缀
            #   （剥离 Br 避免多余换行，剥离 Group 避免重复 ID）
            clean_prefix = re.sub(r'<Br\s*/>', '', csr_prefix)
            clean_prefix = re.sub(
                r'<Group[^>]*>.*?</Group>', '', clean_prefix, flags=re.DOTALL
            )
            clean_suffix = csr_xml[csr_xml.rfind('</CharacterStyleRange>'):]
            non_punct_parts = [i for i, (is_p, _) in enumerate(segments) if not is_p]
            parts = []
            for i, (is_p, text) in enumerate(segments):
                if is_p and punct_template:
                    parts.append(punct_template)
                else:
                    pfx = csr_prefix if i == non_punct_parts[0] else clean_prefix
                    parts.append(
                        pfx
                        + f'<Content>{_xml_escape(text)}</Content>'
                        + clean_suffix
                    )
            # 后缀加在整个拆分序列末尾
            parts[-1] = parts[-1].replace(clean_suffix, csr_suffix)
            csr_replacements[ci] = ''.join(parts)

    # 5. 应用替换：从后往前
    result = original_psr_xml
    for ci in range(len(csr_list) - 1, -1, -1):
        cdata = csr_list[ci]
        if ci not in csr_replacements:
            continue
        repl = csr_replacements[ci]
        match = cdata['match']
        result = result[:match.start()] + repl + result[match.end():]

    return result


def _remove_empty_punct_csrs(xml: str, csr_pattern: str) -> str:
    """删除 Content 为空的句号 CSR。"""
    result = xml
    # 从后往前删除，避免位置偏移
    for m in reversed(list(re.finditer(csr_pattern, xml, re.DOTALL))):
        attrs = m.group(1)
        if 'CharacterStyle/句号' not in attrs:
            continue
        contents = re.findall(r'<Content>(.*?)</Content>', m.group(0), re.DOTALL)
        if all(c == '' for c in contents):
            result = result[:m.start()] + result[m.end():]
    return result


def _insert_punct_csrs(
    xml: str, punct_records: list[dict], template: str
) -> str:
    """将句号 CSR 插入到 XML 中对应 text CSR 之后。"""
    # 按 after_csr 分组，从后往前插入，保持位置稳定
    punct_after: dict[int, list[dict]] = {}
    for prec in punct_records:
        ci = prec.get('after_csr', -1)
        if ci < 0:
            continue
        punct_after.setdefault(ci, []).append(prec)

    if not punct_after:
        return xml

    # 找到每个 csr_idx 对应的 </CharacterStyleRange> 位置
    csr_pattern = r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)'
    csr_closes = []  # [(csr_idx, close_pos), ...]
    csr_idx = 0
    for csr_match in re.finditer(csr_pattern, xml, re.DOTALL):
        attrs = csr_match.group(1)
        is_punct_csr = (
            'CharacterStyle/句号' in attrs
            or ''.join(slot_contents) == '。'
        )
        end_pos = csr_match.end()
        csr_closes.append((csr_idx, end_pos, is_punct_csr))
        csr_idx += 1

    # 从后往前插入
    result = xml
    for ci in sorted(punct_after.keys(), reverse=True):
        # 找到 csr_idx=ci 的 CSR 结束位置。跳过旧句号 CSR（已被清空）
        close_pos = None
        for idx, pos, is_punct in csr_closes:
            if idx == ci:
                close_pos = pos
                break
        if close_pos is None:
            continue
        # 在 close_pos 处插入该 csr 后跟的所有句号 CSR
        tail = ''.join(template for _ in punct_after[ci])
        result = result[:close_pos] + tail + result[close_pos:]

    # 处理 after_csr=-1 的句号（应该没有），放末尾
    overflow = [p for p in punct_records if p.get('after_csr', -1) < 0]
    if overflow:
        tail = ''.join(template for _ in overflow)
        last_close = result.rfind('</CharacterStyleRange>')
        if last_close >= 0:
            insert_pos = result.find('>', last_close) + 1
            result = result[:insert_pos] + tail + result[insert_pos:]

    return result


def _clear_content_keep_br(csr_xml: str, strip_groups: bool = False) -> str:
    """清空 CSR 的 Content 文本，保留 Br 标签和 CSR 结构。

    用于段落分割后 trailing 区域的清理：Br 标签保留以确保
    分割段落尾部保留原始换行（如空行分隔符）。

    Args:
        strip_groups: 是否同时移除 Group 元素（分割副本需设为 True
                      以避免重复 Self ID）。
    """
    result = csr_xml
    if strip_groups:
        result = re.sub(r'<Group[^>]*>.*?</Group>', '', result, flags=re.DOTALL)
    result = re.sub(
        r'<Content>.*?</Content>',
        '<Content></Content>',
        result,
        flags=re.DOTALL,
    )
    return result


def _clear_content_strip_br(csr_xml: str, strip_groups: bool = False) -> str:
    """清空 CSR 的 Content 文本、移除 Br，保留基本 CSR 结构。

    用于段落分割后 leading 区域的清理：
    - Br 标签不应出现在新段落开头（会造成多余空行）

    Args:
        strip_groups: 是否同时移除 Group 元素（分割副本需设为 True
                      以避免重复 Self ID）。
    """
    result = re.sub(r'<Br\s*/>', '', csr_xml)
    if strip_groups:
        result = re.sub(r'<Group[^>]*>.*?</Group>', '', result, flags=re.DOTALL)
    result = re.sub(
        r'<Content>.*?</Content>',
        '<Content></Content>',
        result,
        flags=re.DOTALL,
    )
    return result


def _rebuild_story_xml(header: str, para_xmls: list[str], footer: str) -> str:
    """用重建的段落 XML 拼接完整的 Story XML。

    参数:
        header: Story XML 头部（第一个 ParagraphStyleRange 之前的所有内容）。
        para_xmls: 重建后的各段落 XML 列表。
        footer: Story XML 尾部（最后一个 ParagraphStyleRange 之后的所有内容）。

    返回:
        完整的 Story XML 字符串。
    """
    return header + '\n'.join(para_xmls) + footer


def _write_stories_to_idml(idml_path: str, new_story_xmls: dict[str, str]) -> None:
    """将修改后的 Story XML 写回 IDML ZIP 文件。

    读取 IDML ZIP 的全部内容到内存，替换指定 Story 的 XML，然后写回。
    非 Story 文件（图片、字体、designmap 等）原样保留。

    参数:
        idml_path: IDML 文件路径（已由 shutil.copy2 复制为目标文件）。
        new_story_xmls: 映射 story_name -> 新的 Story XML 字符串。
    """
    # 读取原始 ZIP 全部内容
    with zipfile.ZipFile(idml_path, 'r') as zf:
        all_files: dict[str, bytes] = {}
        for name in zf.namelist():
            all_files[name] = zf.read(name)

    # 替换修改过的 Story XML
    for story_name, new_xml in new_story_xmls.items():
        story_path = f'Stories/Story_{story_name}.xml'
        if story_path in all_files:
            all_files[story_path] = new_xml.encode('utf-8')
        else:
            print(f"  警告: Story 文件 {story_path} 在 ZIP 中未找到，跳过")

    # 写回 ZIP
    with zipfile.ZipFile(idml_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in all_files.items():
            zf.writestr(name, data)


def generate_idml(
    idml_path: str,
    stories: list[dict],
    grouped_records: dict,
    split_sources: dict,
    output_path: str,
) -> None:
    """将新字符记录写回 IDML。

    核心流程:
        1. 复制原始 IDML 到输出路径
        2. 遍历每个 Story，对每个段落取对应的 grouped_records
        3. 用新记录重建 ParagraphStyleRange XML
        4. 拼接完整 Story XML
        5. 写回 ZIP

    参数:
        idml_path: 原始 IDML 文件路径。
        stories: extract_from_idml() 返回的 stories 列表。
        grouped_records: validate_and_align() 返回的分组记录字典。
            grouped_records[story_idx][para_idx] = 该段落的新字符记录列表。
        split_sources: dict mapping (story_idx, effective_para_idx) → original_para_idx
            指示分割产生的新段落的来源段落。
        output_path: 输出 IDML 文件的路径。
    """
    # 复制原始 IDML
    shutil.copy2(idml_path, output_path)

    # 查找全局句号 CSR 模板（用于没有原句号 CSR 的段落）
    global_punct_template: str | None = None
    for story in stories:
        for para in story['paragraphs']:
            csr_pattern = (
                r'<CharacterStyleRange([^>]*?CharacterStyle/句号[^>]*?)>'
                r'.*?</CharacterStyleRange>'
            )
            tm = re.search(csr_pattern, para['raw_xml'], re.DOTALL)
            if tm:
                global_punct_template = tm.group(0)
                break
        if global_punct_template:
            break

    new_story_xmls: dict[str, str] = {}
    para_rebuilt_count = 0
    para_unchanged_count = 0
    para_split_count = 0

    for story_idx, story in enumerate(stories):
        meta = grouped_records.get(story_idx, {})
        max_orig_para_idx = len(story['paragraphs'])

        # 构建 (position, para_xml) 列表用于排序
        # position: 原始段落用 para_idx，分割段落用 source_para_idx + 0.5
        positioned_parts: list[tuple[float, str]] = []

        # 处理原始段落
        for para_idx, para in enumerate(story['paragraphs']):
            para_records = meta.get(para_idx, [])

            if para_records:
                new_psr_xml = _rebuild_paragraph_xml(
                    para['raw_xml'], para_records, global_punct_template
                )
                para_rebuilt_count += 1
            else:
                new_psr_xml = para['raw_xml']
                para_unchanged_count += 1

            positioned_parts.append((float(para_idx), new_psr_xml))

        # 处理因空行边界而分割出的新段落（para_idx >= max_orig_para_idx）
        extra_para_indices = sorted(
            [pi for pi in meta if pi >= max_orig_para_idx]
        )
        for para_idx in extra_para_indices:
            para_records = meta[para_idx]
            # 找到分割来源段落，使用其 raw_xml 作为模板
            source_key = (story_idx, para_idx)
            source_para_idx = split_sources.get(source_key)
            if source_para_idx is not None and source_para_idx < len(story['paragraphs']):
                template_xml = story['paragraphs'][source_para_idx]['raw_xml']
                # 新段落插入到源段落之后（position = source + 0.5）
                position = float(source_para_idx) + 0.5
            else:
                # 回退：使用最后一个段落作为模板，放在末尾
                template_xml = story['paragraphs'][-1]['raw_xml']
                position = float(len(story['paragraphs']))
            new_psr_xml = _rebuild_paragraph_xml(
                template_xml, para_records, global_punct_template,
                is_split_copy=True,
            )
            positioned_parts.append((position, new_psr_xml))
            para_split_count += 1

        # 按位置排序
        positioned_parts.sort(key=lambda x: x[0])
        story_xml_parts = [pxml for _, pxml in positioned_parts]

        new_story_xmls[story['name']] = _rebuild_story_xml(
            story['xml_header'],
            story_xml_parts,
            story['xml_footer'],
        )

    print(f"  重建 {para_rebuilt_count} 个段落，{para_unchanged_count} 个段落保持不变，"
          f"{para_split_count} 个新段落（来自分割）")

    _write_stories_to_idml(output_path, new_story_xmls)


def _verify_structure(
    input_path: str, output_path: str,
    stories: list[dict], split_sources: dict,
    grouped_records: dict,
) -> None:
    """输出 IDML 结构完整性验证（在写入 ZIP 后、返回前调用）。

    检查项：
    1. Group Self ID 全局唯一（防止模板复制导致的重复 ID）
    2. Br 数量在合理范围内（防止大量丢失或多余）
    3. 分割段落无 leading Br（防止段首空行/隐形字符）
    4. 段落数一致性
    5. 所有文字 Content 可被正确解析

    任何检查失败都会删除输出文件并抛出 ValueError。
    """
    errors: list[str] = []

    # ---- 1: Group Self ID 唯一性 ----
    group_ids: dict[str, list[str]] = {}  # {id: [story_name, ...]}
    with zipfile.ZipFile(output_path, 'r') as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            xml = zf.read(name).decode('utf-8')
            for gid in re.findall(r'Self="([^"]+)"', xml):
                group_ids.setdefault(gid, []).append(name)

    dup_groups = {gid: stories for gid, stories in group_ids.items()
                  if len(stories) > 1}
    if dup_groups:
        details = ', '.join(
            f'{gid}(×{len(s)})' for gid, s in dup_groups.items()
        )
        errors.append(f"Group Self ID 重复: {details}")

    # ---- 2: Br 数量合理性 ----
    def _count_br(xml: str) -> int:
        return xml.count('<Br />') + xml.count('<Br/>')

    csr_pattern = (
        r'<CharacterStyleRange([^>]*?CharacterStyle/句号[^>]*?)>'
        r'.*?</CharacterStyleRange>'
    )

    in_br_total = 0
    out_br_total = 0
    br_in_old_punct = 0
    br_in_orig_empty = 0

    with zipfile.ZipFile(input_path, 'r') as in_zf, \
         zipfile.ZipFile(output_path, 'r') as out_zf:
        for name in in_zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            in_xml = in_zf.read(name).decode('utf-8')
            out_xml = out_zf.read(name).decode('utf-8')

            in_br_total += _count_br(in_xml)
            out_br_total += _count_br(out_xml)

            br_in_old_punct += sum(
                _count_br(m.group(0))
                for m in re.finditer(csr_pattern, in_xml, re.DOTALL)
            )

            for psr in re.finditer(
                r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>',
                in_xml, re.DOTALL
            ):
                for m in re.finditer(
                    r'<CharacterStyleRange([^>]*?)(?:>'
                    r'(.*?)</CharacterStyleRange>|/>)',
                    psr.group(0), re.DOTALL
                ):
                    contents = re.findall(
                        r'<Content>(.*?)</Content>',
                        m.group(0), re.DOTALL
                    )
                    if not any(c.strip() for c in contents):
                        br_in_orig_empty += _count_br(m.group(0))

    br_min = max(0, in_br_total - br_in_old_punct - br_in_orig_empty)

    if out_br_total < br_min:
        errors.append(
            f"Br 丢失过多: 输入 {in_br_total} → 输出 {out_br_total} "
            f"（最低预期 {br_min}，旧句号清除 {br_in_old_punct}，"
            f"原始装饰 {br_in_orig_empty}）"
        )

    # ---- 3: 分割段落无 leading Br ----
    with zipfile.ZipFile(output_path, 'r') as zf:
        story_xmls = {}
        for name in zf.namelist():
            if name.startswith('Stories/Story_'):
                story_xmls[name] = zf.read(name).decode('utf-8')

    for (si, new_pi), orig_pi in split_sources.items():
        story_name = f'Stories/Story_{stories[si]["name"]}.xml'
        if story_name not in story_xmls:
            continue
        xml = story_xmls[story_name]
        psrs = list(re.finditer(
            r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>',
            xml, re.DOTALL
        ))
        # 找到这个分割段落（position = orig_pi + 0.5）
        # 简化：遍历所有段落，找 leading Br
        for i, psr in enumerate(psrs):
            csrs = list(re.finditer(
                r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
                psr.group(0), re.DOTALL
            ))
            first_content = None
            for j, m in enumerate(csrs):
                inner = m.group(2) or ''
                c = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
                if any(t.strip() for t in c):
                    first_content = j
                    break
            if first_content is None:
                continue
            for j in range(first_content):
                if '<Br' in csrs[j].group(0):
                    errors.append(
                        f"分割段落 Para[{i}] CSR[{j}] 存在 leading Br"
                    )

    # ---- 4: 段落数一致性（仅统计有注入操作的 Story） ----
    expected_paras = 0
    actual_total = 0
    for story_idx, story in enumerate(stories):
        meta = grouped_records.get(story_idx, {})
        if not meta:
            continue  # 无注入操作的 Story 跳过
        expected_paras += len(story['paragraphs'])
        # 加上这个 Story 的分割段落
        max_orig = len(story['paragraphs'])
        extras = [pi for pi in meta if pi >= max_orig]
        expected_paras += len(extras)

        story_path = f"Stories/Story_{story['name']}.xml"
        if story_path in story_xmls:
            actual_total += len(re.findall(
                r'<ParagraphStyleRange[^>]*>',
                story_xmls[story_path], re.DOTALL
            ))

    if actual_total != expected_paras:
        errors.append(
            f"段落数不一致: 预期 {expected_paras}, 实际 {actual_total}"
        )

    # ---- 判断 ----
    if errors:
        try:
            os.remove(output_path)
        except OSError:
            pass
        raise ValueError(
            "输出 IDML 结构验证失败！\n"
            + "\n".join(f"  • {e}" for e in errors)
            + f"\n（输出文件已删除: {output_path}）"
        )


def _verify_br_count(input_path: str, output_path: str) -> None:
    """报告输入/输出 IDML 的 Br 数量变化。

    预期变化：
    1. 旧句号 CSR 的 Br → 清除（句号由新 punct 模板接管）
    2. 被清空的文字 CSR 的 Br → 清除（段落分割后原 Br 不重复保留）

    字符级输出验证（_verify_output）是真正的质量保证。
    """
    def _count_br(xml: str) -> int:
        return xml.count('<Br />') + xml.count('<Br/>')

    csr_pattern = r'<CharacterStyleRange([^>]*?CharacterStyle/句号[^>]*?)>.*?</CharacterStyleRange>'

    in_br_total = 0
    out_br_total = 0
    br_in_old_punct = 0

    with zipfile.ZipFile(input_path, 'r') as in_zf, \
         zipfile.ZipFile(output_path, 'r') as out_zf:
        for name in in_zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            in_xml = in_zf.read(name).decode('utf-8')
            out_xml = out_zf.read(name).decode('utf-8')
            in_br_total += _count_br(in_xml)
            out_br_total += _count_br(out_xml)
            br_in_old_punct += sum(
                _count_br(m.group(0))
                for m in re.finditer(csr_pattern, in_xml, re.DOTALL)
            )

    br_cleared_text = in_br_total - br_in_old_punct - out_br_total

    print(f"  Br 统计: 输入 {in_br_total} → 输出 {out_br_total}"
          f"（旧句号清除 {br_in_old_punct}, 清空文字 CSR 清除 {br_cleared_text}）")


def _verify_output(output_path: str, expected_chars: list[str]) -> None:
    """输出自检：从生成的 IDML 重新提取字符序列并与输入比对。

    如果发现任何差异，立即删除输出文件并抛出异常。
    这是防止写入过程（XML 重建、ZIP 打包）引入数据丢失的最后一道防线。
    """
    # 重新提取
    stories = extract_from_idml(output_path)
    all_records: list[dict] = []
    for story in stories:
        story_clean = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean < 50:
            continue
        for para in story['paragraphs']:
            for rec in para['chars']:
                all_records.append(rec)

    # 构建输出字符序列（排除比对空白，因为对齐时已丢弃结果中的空白，
    # 只保留 IDML 的空白，所以输出在空白上必然与输入不同）
    output_chars: list[str] = []
    for rec in all_records:
        ch = rec['char']
        if _is_unicode_whitespace(ch):
            continue
        if _is_ws_for_compare(ch):
            continue
        output_chars.append(ch)

    # 比对（排除空白后，文字和句号序列必须一致）
    expected_filtered = [c for c in expected_chars if not _is_ws_for_compare(c)]
    expected_str = ''.join(expected_filtered)
    output_str = ''.join(output_chars)

    if output_str == expected_str:
        print(f"  输出验证通过: {len(output_str)} 个字符与输入完全一致")
        return

    # 验证失败 — 删除坏文件，报告差异
    try:
        os.remove(output_path)
    except OSError:
        pass

    min_len = min(len(expected_str), len(output_str))
    for i in range(min_len):
        if expected_str[i] != output_str[i]:
            ctx = max(0, i - 30)
            raise ValueError(
                f"输出 IDML 验证失败！生成的 IDML 与输入句读结果不一致。\n"
                f"（输出文件已删除: {output_path}）\n"
                f"输入字符数: {len(expected_str)}\n"
                f"输出字符数: {len(output_str)}\n"
                f"第一个差异在位置 {i}:\n"
                f"  输入: ...{expected_str[ctx:i+30]}...\n"
                f"  输出: ...{output_str[ctx:i+30]}...\n"
                f"  输入 @{i}: U+{ord(expected_str[i]):04X} ('{expected_str[i]}')\n"
                f"  输出 @{i}: U+{ord(output_str[i]):04X} ('{output_str[i]}')"
            )
    raise ValueError(
        f"输出 IDML 验证失败！字符数不一致: "
        f"输入 {len(expected_str)} vs 输出 {len(output_str)}"
        f"\n（输出文件已删除: {output_path}）"
    )


def process(idml_path, result_path, output_path):
    """主处理流程"""
    print("=" * 60)
    print("IDML 句读结果回注工具")
    print("=" * 60)

    # Step 1: 从 IDML 提取（含提取自检）
    print("\n[1/5] 解析 IDML...")
    stories = extract_from_idml(idml_path)
    total_chars = sum(
        len(p['chars']) for s in stories for p in s['paragraphs']
    )
    print(f"  提取 {len(stories)} 个 Story, {total_chars} 个字符记录")

    # Step 2: 从句读结果提取
    print("\n[2/5] 读取句读结果...")
    result_data = extract_from_result(result_path)
    result_chars = result_data['chars']
    punct_count = sum(1 for c in result_chars if c == '。')
    print(f"  提取 {len(result_chars)} 个字符（含 {punct_count} 个句号）")
    if result_data['para_breaks']:
        print(f"  检测到 {len(result_data['para_breaks'])} 个段落边界")

    # Step 3: 验证并对齐
    print("\n[3/5] 验证并对齐...")
    alignment = validate_and_align(stories, result_data)
    grouped_records = alignment['grouped']
    split_sources = alignment['split_sources']

    # Step 4: 生成输出
    print("\n[4/5] 生成输出 IDML...")
    generate_idml(idml_path, stories, grouped_records, split_sources, output_path)

    # Step 5: 多层验证 — 结构 → Br → 字符
    print("\n[5/5] 验证输出 IDML...")
    _verify_structure(idml_path, output_path, stories,
                      split_sources, grouped_records)
    _verify_br_count(idml_path, output_path)
    _verify_output(output_path, result_chars)

    print(f"\n{'=' * 60}")
    print(f"完成！输出文件: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
