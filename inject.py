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
            'style': str | None,    # CharacterStyleRange XML 模板（Content 替换为 {content}）
            'story_idx': int,
            'para_idx': int,
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
        for rec in story['paragraphs']:
            for rec in rec['chars']:
                ch = rec['char']
                if rec.get('is_special', False):
                    continue
                if rec['is_punct']:
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

        # 查找 ALL Content 元素（处理同一 CSR 内有多个 <Content> 被 <Br/> 等隔开的情况）
        content_matches = list(
            re.finditer(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        )
        if not content_matches:
            continue
        content_text = ''.join(m.group(1) for m in content_matches)

        # 生成样式模板 — 覆盖从第一个 Content 到最后一个 Content 的全部范围
        # 将多 Content + 中间元素（如 <Br/>）整体替换为 {content} 占位符
        full_csr_xml = match.group(0)
        full_content_matches = list(
            re.finditer(r'<Content>(.*?)</Content>', full_csr_xml, re.DOTALL)
        )
        if full_content_matches:
            first_start = full_content_matches[0].start()
            last_end = full_content_matches[-1].end()
            style_template = (
                full_csr_xml[:first_start]
                + '{content}'
                + full_csr_xml[last_end:]
            )
        else:
            style_template = full_csr_xml

        # 特殊加工指令（如 <?ACE 18?>）
        if re.match(r'<\?ACE\s', content_text):
            chars.append({
                'char': content_text,
                'is_punct': False,
                'is_special': True,
                'style': style_template,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
            continue

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
                ctx_start = max(0, i - 50)
                ctx_end = min(min_len, i + 50)
                # 构建差异位置的十六进制上下文
                idml_hex = ' '.join(f'{ord(c):04X}' for c in idml_clean_str[ctx_start:ctx_end])
                result_hex = ' '.join(f'{ord(c):04X}' for c in result_clean_str[ctx_start:ctx_end])
                raise ValueError(
                    f"字数验证失败！\n"
                    f"IDML 净文字数: {len(idml_clean_str)}\n"
                    f"句读结果净文字数: {len(result_clean_str)}\n"
                    f"第一个差异在位置 {i} (上下文 {ctx_start}-{ctx_end}):\n"
                    f"  IDML: ...{idml_clean_str[ctx_start:ctx_end]}...\n"
                    f"  结果: ...{result_clean_str[ctx_start:ctx_end]}...\n"
                    f"  IDML @{i}: U+{ord(a):04X} ('{a}')\n"
                    f"  结果 @{i}: U+{ord(b):04X} ('{b}')\n"
                    f"提示: 句读结果与 IDML 原文不一致，"
                    f"请确认结果文件是从该 IDML 导出的文本生成的。"
                )
        raise ValueError(
            f"字数验证失败！IDML: {len(idml_clean_str)} 字, "
            f"结果: {len(result_clean_str)} 字（内容相同但长度不同）"
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
    print("  警告: 未在 IDML 中找到已有的句号样式（CharacterStyle/句号），"
          "新增句号将使用段落默认样式")
    return None


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
    original_psr_xml: str, new_char_records: list[dict]
) -> str:
    """用新的字符记录重建 ParagraphStyleRange 的 XML。

    连续的相同样式字符合并为一个 CharacterStyleRange 以减少输出大小。
    特殊标记（is_special=True）不参与合并，其内容按原样保留不转义。
    is_punct 记录不与其他样式合并。

    参数:
        original_psr_xml: 原始 ParagraphStyleRange 的完整 XML 字符串。
        new_char_records: 该段落的新字符记录列表。

    返回:
        重建后的 ParagraphStyleRange XML 字符串。
    """
    if not new_char_records:
        return original_psr_xml

    # 提取 ParagraphStyleRange 的前缀（第一个 CharacterStyleRange 之前的内容）
    first_csr = re.search(r'<CharacterStyleRange', original_psr_xml)
    if not first_csr:
        return original_psr_xml

    prefix = original_psr_xml[:first_csr.start()]

    # 提取 ParagraphStyleRange 的后缀（最后一个 CharacterStyleRange 之后的内容）
    last_csr_end = original_psr_xml.rfind('</CharacterStyleRange>')
    if last_csr_end >= 0:
        close_bracket = original_psr_xml.find('>', last_csr_end)
        if close_bracket >= 0:
            suffix_start = close_bracket + 1
            suffix = original_psr_xml[suffix_start:]
        else:
            # 防御性处理：理论上有效 XML 不应该走到这里
            suffix = '\n</ParagraphStyleRange>'
    else:
        suffix = '\n</ParagraphStyleRange>'

    # 生成新的 CharacterStyleRange 元素，合并连续相同样式的字符
    csr_elements: list[str] = []
    i = 0
    while i < len(new_char_records):
        rec = new_char_records[i]

        if rec.get('is_special', False):
            # 特殊标记：使用样式模板但内容不转义
            if rec.get('style'):
                csr_xml = rec['style'].replace(
                    '{content}', f'<Content>{rec["char"]}</Content>'
                )
                csr_elements.append(csr_xml)
            else:
                # 回退：直接保留字符值（不应发生，因为已修复提取逻辑）
                csr_elements.append(rec['char'])
            i += 1
            continue

        # 收集连续相同样式的字符
        chars_in_group = [rec['char']]
        j = i + 1
        while j < len(new_char_records):
            next_rec = new_char_records[j]
            if (
                next_rec.get('is_special', False)
                or next_rec.get('style') != rec.get('style')
                or next_rec.get('is_punct') != rec.get('is_punct')
            ):
                break
            chars_in_group.append(next_rec['char'])
            j += 1

        group_text = ''.join(chars_in_group)

        if rec.get('style'):
            csr_xml = rec['style'].replace(
                '{content}', f'<Content>{_xml_escape(group_text)}</Content>'
            )
            csr_elements.append(csr_xml)

        i = j

    return prefix + '\n'.join(csr_elements) + suffix


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
        output_path: 输出 IDML 文件的路径。
    """
    # 复制原始 IDML
    shutil.copy2(idml_path, output_path)

    new_story_xmls: dict[str, str] = {}
    para_rebuilt_count = 0
    para_unchanged_count = 0

    for story_idx, story in enumerate(stories):
        story_xml_parts: list[str] = []

        for para_idx, para in enumerate(story['paragraphs']):
            para_records = grouped_records.get(story_idx, {}).get(para_idx, [])

            if para_records:
                new_psr_xml = _rebuild_paragraph_xml(para['raw_xml'], para_records)
                para_rebuilt_count += 1
            else:
                new_psr_xml = para['raw_xml']
                para_unchanged_count += 1

            story_xml_parts.append(new_psr_xml)

        new_story_xmls[story['name']] = _rebuild_story_xml(
            story['xml_header'],
            story_xml_parts,
            story['xml_footer'],
        )

    print(f"  重建 {para_rebuilt_count} 个段落，{para_unchanged_count} 个段落保持不变")

    _write_stories_to_idml(output_path, new_story_xmls)


def process(idml_path, result_path, output_path):
    """主处理流程"""
    print("=" * 60)
    print("IDML 句读结果回注工具")
    print("=" * 60)

    # Step 1: 从 IDML 提取
    print("\n[1/4] 解析 IDML...")
    stories = extract_from_idml(idml_path)
    total_chars = sum(
        len(p['chars']) for s in stories for p in s['paragraphs']
    )
    print(f"  提取 {len(stories)} 个 Story, {total_chars} 个字符记录")

    # Step 2: 从句读结果提取
    print("\n[2/4] 读取句读结果...")
    result_chars = extract_from_result(result_path)
    punct_count = sum(1 for c in result_chars if c == '。')
    print(f"  提取 {len(result_chars)} 个字符（含 {punct_count} 个句号）")

    # Step 3: 验证并对齐
    print("\n[3/4] 验证并对齐...")
    grouped_records = validate_and_align(stories, result_chars)

    # Step 4: 生成输出
    print("\n[4/4] 生成输出 IDML...")
    generate_idml(idml_path, stories, grouped_records, output_path)

    print(f"\n{'=' * 60}")
    print(f"完成！输出文件: {output_path}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
