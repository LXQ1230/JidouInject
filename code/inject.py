#!/usr/bin/env python3
"""
IDML 句读结果回注工具
将 _WD句读结果.md 中的文字和白名单标点（，、；：？！。）注入回 IDML，
排版样式原封不动。

用法:
    python inject.py --idml 275导出.idml --result 275从ID中导出文字_WD句读结果.md
    或拖拽两个文件到 inject.bat 上

版本: v1.5.0（2026-08-06 标点开放）— 回注标点从仅「。」扩展为
_INJECTABLE_PUNCT（，、；：？！。），抑制规则对新标点一视同仁，
样式沿用 CharacterStyle/句号 模板、Content 替换为实际标点。
"""

import sys
import os
import re
import html
import argparse
import shutil
import zipfile
import unicodedata
import ctypes
import time
import gc
from dataclasses import dataclass


@dataclass(slots=True)
class CharRecord:
    """字符记录 — 紧凑结构（slots dataclass，约 90-120B/条，dict 约 250-300B/条）。

    兼容 dict 读取接口（rec['char'] / rec.get('char', default)），
    字段与旧 dict 字面量完全同名，所有读取点无需改动。
    """
    char: str
    is_punct: bool
    is_special: bool
    story_idx: int
    para_idx: int
    csr_idx: int
    content_slot: int
    font: str | None = None       # 解析阶段有；对齐阶段记录无
    after_csr: int = -1           # 仅对齐阶段句号记录使用
    after_slot: int | None = None # 仅对齐阶段句号记录使用
    slot_pos: int = 0             # 字符在 content_slot 内的偏移（解析阶段）
    after_pos: int | None = None  # 句号跟随字符的 slot 内偏移（对齐阶段）

    def __getitem__(self, key: str):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)


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


# 可回注标点白名单（v1.5.0）— 句读结果中允许出现、并可注入回 IDML 的标点。
# 原实现仅允许「。」（FIX-1B 会拒绝任何非句号标点）。v1.5.0 开放为常用
# 中文标点全套：句号/逗号/顿号/分号/冒号/问号/叹号。
# 此集合之外的旧标点（引号、括号、书名号、省略号等成对/装饰符号）仍被
# 拒绝——它们多为原文排版符号，不属于句读结果。
#
# 注意：此集合是 _OLD_PUNCT_CHARS 的子集。回注时该集合内的标点作为
# 「可注入标点」处理（校验时排除、对齐时插入、重建时生成独立 CSR）；
# 集合外的旧标点在结果文件中出现即拒绝（疑似以原文导出文本冒充结果）。
_INJECTABLE_PUNCT: frozenset[str] = frozenset('，、；：？！。')


# P3-11: 非法 HTML 实体替换计数器。
# html.unescape 对非法实体（保留码位/超范围等）输出 U+FFFD 替换字符，
# 需计数并警告，防止静默的字符损坏进入输出。
_REPLACEMENT_COUNT: dict[str, int] = {'replaced': 0}

# P3-14: 分割副本空壳 CSR 删除哨兵。_rebuild_paragraph_xml 中
# csr_replacements 的值若为此对象，表示该 CSR 在重建输出中整体删除。
# 用于分割段落（is_split_copy=True）的无记录空壳 CSR —— 原实现输出
# 清空后的空壳，4319 个分割段 × 源段数百个空 CSR 骨架导致输出解压体积
# 膨胀 19 倍（497 的 Story_u562：71MB → 1364MB），验证阶段需反复全量
# 正则扫描该体积，单次运行耗时 20 分钟以上。
_DROP_CSR = object()


def _unescape_entities(text: str) -> str:
    """解码 HTML 实体；统计被替换为 U+FFFD 的非法实体（P3-11）。

    0080 等经书使用合法十六进制实体（如 &#xfdc4f;）表示增补平面字符，
    html.unescape 正常解码不产生 U+FFFD。仅当实体非法时才替换为 U+FFFD。
    """
    decoded = html.unescape(text)
    if '\ufffd' in decoded and '\ufffd' not in text:
        n = decoded.count('\ufffd')
        _REPLACEMENT_COUNT['replaced'] += n
        print(f"  [警告] 检测到 {n} 个非法 HTML 实体被替换为 U+FFFD"
              f"（字符可能损坏，请检查 IDML 来源）")
    return decoded


# 仅当同 CSR 内两字间有 U+3000 时才抑制 。 的字体（思源宋体/法藏大宋）
# 使用 startswith 前缀匹配：如 '思源宋体' 匹配 '思源宋体 CN'、'FaZangDaSong' 匹配 'FaZangDaSong SC'
_FONTS_SUPPRESS_WIDTH: list[str] = [
    '思源宋体',
    'FaZangDaSong',
]

# 前字或后字属于这些字体时无条件抑制 。（仿宋/楷体）
# 使用 startswith 前缀匹配：如 '仿宋' 匹配 '经书仿宋1'、'方正仿宋 GB18030L2' 等所有变体
_FONTS_SUPPRESS_ALWAYS: list[str] = [
    '仿宋',
    '楷体',
]


def _extract_font_from_csr(csr_attrs: str, csr_inner: str) -> str | None:
    """从 CSR 的 XML 片段中提取 AppliedFont 名称。

    字体名存储在 <Properties><AppliedFont type="string">xxx</AppliedFont></Properties> 中。
    """
    font_match = re.search(
        r'<AppliedFont\s+type="string">([^<]+)</AppliedFont>',
        csr_inner,
    )
    return font_match.group(1) if font_match else None


def _is_suppress_width_target(font: str | None) -> bool:
    """检查字体是否属于仅限 U+3000 间隔抑制的目标（思源宋体）。前缀匹配。"""
    if font is None:
        return False
    return any(font.startswith(prefix) for prefix in _FONTS_SUPPRESS_WIDTH)

def _is_suppress_always_target(font: str | None) -> bool:
    """检查字体是否属于无条件抑制的目标（仿宋/楷体）。包含匹配。

    用 in 而非 startswith：实际字体名如 '经书仿宋1'、'方正仿宋 GB18030L2'、
    '法藏仿宋'、'经书楷体2' 等，核心字通常在中间而非前缀。
    """
    if font is None:
        return False
    return any(keyword in font for keyword in _FONTS_SUPPRESS_ALWAYS)


def _get_prev_non_ws_font(
    idml_idx: int,
    idml_clean_indices: list[int],
    all_idml_records: list[dict],
    anchor: tuple | None = None,
) -> str | None:
    """从 idml_idx 往回找上一个非空白文字字符，返回其字体名。

    P2-3: 不跨 Story/段落边界。边界判定以 anchor（(story_idx, para_idx)，
    即句号槽位所属段落的 story/para）为基准：前一个记录与 anchor 不同
    story 或 para 时按 None 处理（视为无前字），避免跨边界取到装饰/相
    邻段落的字体，造成错误的抑制判断。

    必须用 anchor 而非 idml_idx 处记录作基准：句号槽位位于段落末尾时，
    idml_idx 已指向下一段的首字，若以该字为基准，前向扫描会立即跨段而
    误报「无前字」（P3-12）。anchor 为 None（无槽位上下文）时退化为以
    idml_idx 处记录为准。
    """
    if not (0 <= idml_idx < len(idml_clean_indices)):
        return None
    if anchor is not None:
        bound = anchor
    else:
        cur = all_idml_records[idml_clean_indices[idml_idx]]
        bound = (cur['story_idx'], cur['para_idx'])
    for j in range(idml_idx - 1, -1, -1):
        ti = idml_clean_indices[j]
        rec = all_idml_records[ti]
        if (rec['story_idx'], rec['para_idx']) != bound:
            return None  # 跨 Story/段落边界
        if not _is_ws_for_compare(rec['char']):
            return rec.get('font')
    return None


def _get_next_non_ws_font(
    idml_idx: int,
    idml_clean_indices: list[int],
    all_idml_records: list[dict],
    anchor: tuple | None = None,
) -> str | None:
    """从 idml_idx 向前找下一个非空白文字字符，返回其字体名。

    P2-3: 不跨 Story/段落边界。边界判定以 anchor（句号槽位所属段落的
    story/para）为基准：后一个记录与 anchor 不同 story 或 para 时按
    None 处理（视为无后字）。句号槽位位于段落末尾时，下一段的首字不
    属于槽位所在段落，应视为无后字，避免下一段字体（如偈颂仿宋）影响
    本段句号的抑制判定（P3-12）。anchor 为 None 时退化为以 idml_idx
    处记录为准。
    """
    if not (0 <= idml_idx < len(idml_clean_indices)):
        return None
    if anchor is not None:
        bound = anchor
    else:
        cur = all_idml_records[idml_clean_indices[idml_idx]]
        bound = (cur['story_idx'], cur['para_idx'])
    for j in range(idml_idx, len(idml_clean_indices)):
        ti = idml_clean_indices[j]
        rec = all_idml_records[ti]
        if (rec['story_idx'], rec['para_idx']) != bound:
            return None  # 跨 Story/段落边界
        if not _is_ws_for_compare(rec['char']):
            return rec.get('font')
    return None

def _should_suppress_punct(
    idml_idx: int,
    idml_clean_indices: list[int],
    all_idml_records: list[dict],
    last_slot: tuple | None,
) -> bool:
    """判断 WD 结果中的标点（。或 v1.5.0 开放的其他白名单标点）是否应被抑制。

    函数本身对标点类型无感（基于槽位位置与前后字体判断），因此
    白名单内所有标点（，、；：？！。）统一走同一套抑制规则（一视同仁）。

    规则 A（仿宋/楷体 — 区域内抑制）：
        前字属于仿宋/楷体 → 无条件抑制 （无论后字是什么）。
        后字属于仿宋/楷体 且 前字不是仿宋/楷体 → 思源散文→仿宋偈颂过渡边界，
        句号属于散文侧语法标点，不抑制。
        段首句号（无前字）+ 后字仿宋/楷体 → 抑制。

    规则 B（思源宋体 — 仅 U+3000 间隔抑制）：
        同 CSR + 思源宋体 + 两字间有 U+3000 → 抑制 。。
        保留偈颂/目录中 U+3000 空格间隔的原样排版。

    前字/后字的查找以句号槽位所属段落（last_slot 的 story/para）为边界
    基准（P3-12）：段尾句号不会误取下一段的字体，段首也不会误丢本段前字。
    """
    if last_slot is None:
        return False

    # P3-12: 以槽位所属段落为跨段边界基准，而非 idml_idx 处记录
    # （段尾句号时 idml_idx 已指向下一段首字，以它为基准会误报无前字）
    anchor = (last_slot[0], last_slot[1])
    font_prev = _get_prev_non_ws_font(idml_idx, idml_clean_indices,
                                       all_idml_records, anchor)
    font_next = _get_next_non_ws_font(idml_idx, idml_clean_indices,
                                       all_idml_records, anchor)

    is_prev_always = _is_suppress_always_target(font_prev)
    is_next_always = _is_suppress_always_target(font_next)

    # 前字是仿宋/楷体 → 无条件抑制
    if is_prev_always:
        return True

    # 后字是仿宋/楷体 且 前字不是 → 思源→仿宋过渡边界，放行
    if is_next_always and not is_prev_always:
        if font_prev is None:
            return True   # 段首句号 + 仿宋后字 → 抑制
        return False      # 思源散文末尾句号 → 放行

    # ── 规则B：思源宋体 — U+3000 间隔抑制（现有逻辑） ──
    # 若抑制成立，标点不插入；IDML 原文的 U+3000 仍作为 IDML 记录保留在输出中。
    if idml_idx >= len(idml_clean_indices):
        return False

    # 找下一个 IDML 文字字符（含其索引，供 U+3000 扫描）
    next_idx = None
    next_rec = None
    for j in range(idml_idx, len(idml_clean_indices)):
        ti = idml_clean_indices[j]
        rec = all_idml_records[ti]
        if not _is_ws_for_compare(rec['char']):
            next_idx = j
            next_rec = rec
            break

    if next_rec is None:
        return False

    prev_si, prev_pi, prev_ci, prev_sl, _prev_pos = last_slot

    # 同 CSR？
    if next_rec['csr_idx'] != prev_ci:
        return False
    # 同 story/para？
    if next_rec['story_idx'] != prev_si:
        return False
    if next_rec['para_idx'] != prev_pi:
        return False
    # 字体是思源宋体？
    if not _is_suppress_width_target(next_rec.get('font')):
        return False
    # 两者之间有没有 U+3000？
    for j in range(idml_idx, next_idx):
        ti = idml_clean_indices[j]
        rec = all_idml_records[ti]
        if rec['char'] == '　':
            return True

    return False


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

    def _ask(prompt: str) -> str:
        """读取用户输入；无 TTY（管道/CI）时 EOFError → 返回空串（默认跳过）。

        P3-5: 批处理脚本在非交互环境运行时 input() 会抛 EOFError，
        默认按「全部跳过」处理，避免进程崩溃。
        """
        try:
            return input(prompt).strip().upper()
        except EOFError:
            print("  [提示] 非交互环境无输入，默认全部跳过")
            return 'S'

    while True:
        choice = _ask("\n> ")
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
                    sub = _ask(
                        f"  {path}\n"
                        f"  [O]覆盖 [S]跳过 [R]重命名 [Q]取消全部 > ")
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
    parser.add_argument(
        "--min-clean", type=int, default=50, dest="min_clean_chars",
        help="正文 Story 判定阈值：净字符数低于此值的 Story 视为装饰性元素，"
             "不参与对齐（默认 50）",
    )
    args = parser.parse_args()

    if args.min_clean_chars < 1:
        print("错误: --min-clean 必须 >= 1")
        sys.exit(1)

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

    # FIX-7: --output 不能与 --idml 同路径（会覆盖源文件）
    if os.path.abspath(args.output) == os.path.abspath(args.idml):
        print("错误: --output 不能与 --idml 同路径（会覆盖源文件）")
        sys.exit(1)

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
        process(args.idml, args.result, args.output,
                min_clean_chars=args.min_clean_chars)
    except ValueError as e:
        print(f"\n处理失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n未预期的错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _get_memory_info() -> dict:
    """读取进程峰值内存与系统可用内存（Windows，失败返回空 dict）。

    使用标准库 ctypes 调用 psapi/kernel32，不引入第三方依赖。
    """
    try:
        psapi = ctypes.WinDLL("psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        handle = kernel32.GetCurrentProcess()
        psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb)
        return {
            'peak_rss_mb': pmc.PeakWorkingSetSize / 1024 / 1024,
            'rss_mb': pmc.WorkingSetSize / 1024 / 1024,
        }
    except Exception:
        return {}


def _progress_bar(done: int, total: int, width: int = 40) -> str:
    """生成 \r 进度条字符串（纯标准库）"""
    if total <= 0:
        return ""
    pct = done / total
    filled = int(width * pct)
    bar = '█' * filled + '─' * (width - filled)
    return f"[{bar}] {pct * 100:5.1f}% ({done}/{total})"


def _mem_suffix() -> str:
    """当前内存占用后缀（失败时为空串）"""
    info = _get_memory_info()
    if not info:
        return ""
    return f"  内存峰值 {info['peak_rss_mb']:.0f} MB / 当前 {info['rss_mb']:.0f} MB"


def _log_progress(s: str) -> None:
    """进度输出（P3-8）：TTY 用 \\r 覆盖式进度条，非 TTY（管道/日志/CI）
    退化为普通换行日志，避免输出被 \\r 覆盖丢失或污染日志流。"""
    if sys.stdout.isatty():
        print(s, end='', flush=True)
    else:
        print(s, flush=True)


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def extract_from_idml(
    idml_path: str,
    preloaded_xmls: dict[str, str] | None = None,
) -> list[dict]:
    """    从 IDML 中提取所有文字及其样式信息。

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
        # 注意：designmap 的 StoryList 可能含文件缺失的 story（如 3093 的 ub3），
        # 若用 enumerate 序号作为 story_idx 会带空洞，导致 grouped/split_sources
        # 的 key 与 stories 列表索引错位（隐患：stories[story_idx] 越界被静默跳过重建）。
        # 因此 story_idx 取 stories 列表的实际索引（无空洞），保证全局一致性。
        #
        # P3-14: 进度条分母必须用"实际存在的 Story 文件数"而非 designmap 声明数。
        # IDML 的 StoryList 常含已删除/未导出的 story 引用（如 ub3/uac），文件缺失
        # 时循环 continue 跳过；若分母用声明数，进度条永远到不了 100%
        # （如 497：声明 39 / 实际 38 → 最大显示 97.4%）。提前统计实际数量，
        # 并一次性缓存 namelist（避免循环内反复重建成员列表）。
        member_names = set(zf.namelist())
        n_available = sum(
            1 for s in story_order
            if f'Stories/Story_{s}.xml' in member_names
        )
        n_missing = len(story_order) - n_available
        if n_missing:
            missing_names = [
                s for s in story_order
                if f'Stories/Story_{s}.xml' not in member_names
            ]
            print(f"  [提示] designmap 声明 {len(story_order)} 个 Story，"
                  f"其中 {n_missing} 个文件缺失已跳过: "
                  f"{', '.join(missing_names)}")
        for story_name in story_order:
            story_path = f'Stories/Story_{story_name}.xml'
            if story_path not in member_names:
                continue

            if preloaded_xmls is not None and story_path in preloaded_xmls:
                # 已预加载（验证阶段复用同一份内存 dict，免二次解压与驻留）
                story_xml = preloaded_xmls[story_path]
                raw_story_xmls[story_name] = story_xml
            else:
                story_xml = zf.read(story_path).decode('utf-8')
                raw_story_xmls[story_name] = story_xml
            story_idx = len(stories)
            paragraphs = _parse_story_xml(story_xml, story_idx)
            stories.append({
                'name': story_name,
                'path': story_path,
                'xml_header': _get_story_header(story_xml),
                'xml_footer': _get_story_footer(story_xml),
                'paragraphs': paragraphs,
            })
            if n_available > 10:
                # 大文件：逐 Story 显示解析进度（TTY 覆盖式 / 非 TTY 普通日志）
                _log_progress(
                    f"\r  解析 Story [{story_idx + 1}/{n_available}] "
                    f"{story_name}  {_progress_bar(story_idx + 1, n_available)}")
        if n_available > 10:
            print()

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
        # 解码 HTML 十六进制实体，与解析器行为一致
        raw_text = html.unescape(raw_text)
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
            # 解码 HTML 十六进制实体，与解析器行为一致
            psr_text = html.unescape(psr_text)
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

    # P3-13: 兼容自闭合空段落（<ParagraphStyleRange ... />，InDesign 排版的
    # 空段标记，无文字内容）。原正则按"开+闭标签"配对会漏算自闭合段，
    # 导致其被 _get_story_footer 划入尾部、验证阶段开标签数与段落数不一致。
    # 自闭合段作为空段落（chars=[]）纳入解析；普通段落匹配结果与原来一致。
    pattern = (r'(<ParagraphStyleRange[^>]*?/>'
               r'|<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>)')
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

        # 提取此 CSR 的字体（用于抑制目标字体中 U+3000 前的 。）
        font = _extract_font_from_csr(match.group(1), inner)

        # 每个 <Content> → 一组字符，打上槽位标签
        for slot_idx, cm in enumerate(content_matches):
            content_text = cm.group(1)

            # 解码 HTML 十六进制实体（如 &#xfdc4f; → U+FDC4F），
            # 确保增补平面字符不会被当作多个 ASCII 字符处理
            # （P3-11: 非法实体替换为 U+FFFD 时计数并警告）
            content_text = _unescape_entities(content_text)

            # 特殊加工指令（如 <?ACE 18?>）
            if re.match(r'<\?ACE\s', content_text):
                chars.append(CharRecord(
                    char=content_text,
                    is_punct=False,
                    is_special=True,
                    story_idx=story_idx,
                    para_idx=para_idx,
                    csr_idx=csr_idx,
                    content_slot=slot_idx,
                    font=font,
                ))
                continue

            for pos, ch in enumerate(content_text):
                chars.append(CharRecord(
                    char=sys.intern(ch),
                    is_punct=_is_old_punct(ch),
                    is_special=False,
                    story_idx=story_idx,
                    para_idx=para_idx,
                    csr_idx=csr_idx,
                    content_slot=slot_idx,
                    font=font,
                    slot_pos=pos,
                ))

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
    """提取 Story XML 最后一个段落（含自闭合空段）之后的内容"""
    # P3-13: 原实现只找最后一个 </ParagraphStyleRange>，若 Story 末尾是
    # 自闭合空段（<ParagraphStyleRange ... />，无闭标签）会被划入 footer，
    # 与 _parse_story_xml 的段落边界不一致。改用与解析相同的段落结构正则，
    # footer 从最后一个段落（普通或自闭合）结束之后开始。
    pattern = (r'<ParagraphStyleRange[^>]*?/>'
               r'|<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>')
    last_end = 0
    for m in re.finditer(pattern, story_xml, re.DOTALL):
        last_end = m.end()
    if last_end > 0:
        return story_xml[last_end:]
    return ''


def extract_from_result(md_path: str) -> dict:
    """
    从句读结果 MD 文件提取字符序列和段落边界。

    - 跳过文件头（# 标题到第一个 --- 之间的元数据）
    - 忽略空格、制表符等 ASCII 空白字符
    - 保留可见字符（含白名单标点，v1.5.0 起为 ，、；：？！。；原仅「。」）和全角空格 U+3000
    - 检测空行作为段落边界标记

    返回: {
        'chars': 字符列表，如 ['如', '是', '我', '聞', '。', '一', '時', '。', ...],
        'para_breaks': set of int — chars 中的位置索引，表示段落边界
                        （边界在位置 i 表示 chars[i] 是新段落的第一个字符）
    }
    """
    with open(md_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()

    # P2-7: 跳过文件头 — 仅当文件以「# 标题\n\n---」三段式开头时
    # （句读结果标准头），跳过标题与第一个 --- 之间的元数据。
    # 正文中出现的 --- 不再截断（旧实现 split('---',1) 会误切正文）。
    body = content
    header_match = re.match(r'#[^\n]*\n\s*\n---\n', content)
    if header_match:
        body = content[header_match.end():]

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

    # FIX-1B（P0）: 句读结果身份强校验 — AI 句读结果文件应只含文字 + 白名单标点。
    # 若含白名单以外的旧标点（，；：？！。 之外，如引号、括号、书名号等），
    # 说明疑似以原文导出文本冒充句读结果（原文标点以 。 为主，可令旧校验自洽
    # 通过，造成静默错误注入）。
    # v1.5.0: 白名单从仅「。」扩展为 _INJECTABLE_PUNCT（，、；：？！。）。
    # 集合外的旧标点仍一律拒绝；注意成对标点（「」（）等）不在白名单内——
    # 它们在原文中是排版装饰符号，不参与句读，混入结果文件视为异常。
    for ch in chars:
        if _is_old_punct(ch) and ch not in _INJECTABLE_PUNCT:
            raise ValueError(
                f"句读结果文件含白名单外旧标点「{ch}」(U+{ord(ch):04X})，"
                f"疑似以原文导出文本冒充句读结果，已拒绝。"
                f"请确认为真正的句读结果文件（仅文字+白名单标点"
                f"{''.join(sorted(_INJECTABLE_PUNCT))}）。")

    return {'chars': chars, 'para_breaks': para_breaks}


def validate_and_align(
    stories: list[dict], result_data: dict, min_clean_chars: int = 50
) -> dict:
    """
    验证 IDML 净文字与句读结果净文字一致，然后执行字符级对齐。

    核心逻辑：
    - IDML 的非标点、非特殊标记字符在句读结果中必有对应
    - 句读结果中新增的标点（v1.5.0 起为白名单 ，、；：？！。）插入在
      对应位置，归属上一字符的段落
    - 对齐后的每个 new_record 都标记了所属的 (story_idx, para_idx)
    - 句读结果中的空行（段落边界）会触发 IDML 段落分割：
      边界位置的字符及其后续内容分配到新的虚拟段落

    Args:
        min_clean_chars: 判定「正文 Story」的最小净字符数阈值（P2-8 参数化，
            默认 50）。低于阈值的 Story 视为装饰性元素（页眉、译者信息等），
            不参与对齐。

    返回: grouped_records，结构为 {story_idx: {para_idx: [records]}}
    """
    result_chars: list[str] = result_data['chars']
    para_breaks: set[int] = result_data['para_breaks']

    # 扁平化所有 IDML 字符记录
    # 跳过内容过少的故事（装饰性元素，如页眉标题、译者信息等）
    # 这些装饰故事的内容不在句读结果中，不应参与对齐
    all_idml_records: list[dict] = []
    for story in stories:
        # 检查此 story 是否有足够的正文内容
        story_clean_count = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean_count < min_clean_chars:
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

    # 比对用的净文字：双方都排除比对空白（含 U+3000）与白名单标点
    idml_compare_chars = [
        all_idml_records[i]['char'] for i in idml_clean_indices
        if not _is_ws_for_compare(all_idml_records[i]['char'])
    ]
    result_compare_chars = [
        c for c in result_chars
        if c not in _INJECTABLE_PUNCT and not _is_ws_for_compare(c)
    ]

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

    # P3-13: next_new_idx 起点改为"该 Story 段落总数"（含自闭合空段），
    # 而非 max_pi+1。原实现假设段落索引连续 0..max_pi，但自闭合空段
    # 无字符记录、不出现在 all_idml_records，导致 max_pi 偏小 1；若该
    # Story 发生空行分割，第一个分割段索引会撞上自闭合段的 para_idx，
    # 分割内容会被误当作自闭合段记录而丢失。对无自闭合段的文件
    # （段落索引连续 0..n-1），para_total == max_pi+1，行为不变。
    para_total = {i: len(s['paragraphs']) for i, s in enumerate(stories)}
    for si in orig_para_max:
        next_new_idx[si] = para_total[si]
        for pi in range(para_total[si]):
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

        if ch in _INJECTABLE_PUNCT:
            # 检查是否应抑制标点：IDML 原文此处为 U+3000 分字间隔或
            # 前字为仿宋/楷体（规则 A/B，见 _should_suppress_punct）。
            # v1.5.0: 白名单内所有标点（，、；：？！。）统一走同一抑制逻辑。
            if _should_suppress_punct(idml_idx, idml_clean_indices,
                                       all_idml_records, last_slot):
                # 目标字体 U+3000 间隔/仿宋楷体区域 → 不插入标点。
                # IDML 原文的 U+3000 作为 IDML 记录保留在输出中，对齐循环继续
                pass
            else:
                si, pi, ci, sl, pos = last_slot if last_slot else (0, 0, 0, 0, 0)
                effective_pi = current_effective.get((si, pi), pi)
                new_records.append(CharRecord(
                    char=ch,
                    is_punct=True,
                    is_special=False,
                    story_idx=si,
                    para_idx=effective_pi,
                    csr_idx=-1,
                    content_slot=-1,
                    after_csr=ci,
                    after_slot=sl,
                    after_pos=pos,
                ))
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
                                 orig_rec['csr_idx'], orig_rec['content_slot'],
                                 orig_rec.get('slot_pos', 0))
                    new_records.append(CharRecord(
                        char=orig_rec['char'],
                        is_punct=False,
                        is_special=False,
                        story_idx=orig_rec['story_idx'],
                        para_idx=effective_pi,
                        csr_idx=orig_rec['csr_idx'],
                        content_slot=orig_rec['content_slot'],
                    ))
                else:
                    last_slot = (orig_rec['story_idx'], orig_rec['para_idx'],
                                 orig_rec['csr_idx'], orig_rec['content_slot'],
                                 orig_rec.get('slot_pos', 0))
                    new_records.append(CharRecord(
                        char=orig_rec['char'],
                        is_punct=False,
                        is_special=False,
                        story_idx=orig_rec['story_idx'],
                        para_idx=effective_pi,
                        csr_idx=orig_rec['csr_idx'],
                        content_slot=orig_rec['content_slot'],
                    ))
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
    print(f"对齐完成: {len(new_records)} 个字符（含 {punct_count} 个标点）")

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


def _punct_content_tag(char: str) -> str:
    """生成标点字符的 <Content> 标签（含 XML 转义）。

    v1.5.0: 注入标点时的统一 Content 生成入口，标点字符来自句读结果
    （可能为 ，、；：？！。 中任意一个），而非硬编码「。」。
    """
    return f'<Content>{_xml_escape(char)}</Content>'


def _punct_csr_from_template(template: str, char: str) -> str:
    """将标点模板 CSR 的 Content 文本替换为指定标点字符。

    v1.5.0: 模板（CharacterStyle/句号）承载样式，但 Content 必须替换为
    实际标点——旧实现直接复用模板的「。」文本，导致注入 ，、；：？！ 等
    新标点时被错误写成句号。

    模板可能是完整 CSR XML（旧句号 CSR 复用分支，逐标点复制整段模板）
    或仅 <Content> 标签（拆分分支只取模板的 Content 部分），统一替换
    首个 Content 的文本。对纯句号结果，替换后字节与旧实现完全一致。
    """
    return re.sub(
        r'<Content>.*?</Content>',
        _punct_content_tag(char),
        template,
        count=1,
        flags=re.DOTALL,
    )


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
    # csr_segments: {csr_idx: [(is_punct, text, after_slot|null), ...]}
    # 对于文字: csr_idx = rec['csr_idx'], pos = rec['slot_pos']
    # 对于句号: csr_idx = rec['after_csr'], after_slot = rec['after_slot'],
    #           pos = rec['after_pos']（跟随字符的 slot 内偏移，支持槽内插句号）
    csr_segments: dict[int, list[tuple[bool, str, int | None, int | None]]] = {}
    for rec in all_records:
        if rec.get('is_punct', False):
            ci = rec.get('after_csr', -1)
        else:
            ci = rec['csr_idx']
        if ci < 0:
            continue
        is_p = rec.get('is_punct', False)
        if is_p:
            slot = rec.get('after_slot')
            pos = rec.get('after_pos')
        else:
            slot = rec.get('content_slot')
            pos = rec.get('slot_pos', 0)
        csr_segments.setdefault(ci, []).append((is_p, rec['char'], slot, pos))

    # 3.5 确定文字内容 CSR 的范围（用于区分 leading/trailing 清除区域）
    text_content_csrs = {
        ci for ci, segs in csr_segments.items()
        if any(not is_p for is_p, _, _, _ in segs)
        and not csr_list[ci]['is_punct']
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
    # csr_replacements: {csr_idx: replacement_xml_string | _DROP_CSR}
    # （_DROP_CSR 表示该 CSR 整体删除，见分割副本 A3 分支）
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

            # FIX-6: 正文 Story 内嵌 ACE 加工指令（<?ACE N?>）——
            # 这类 Content 是 InDesign 字形替换指令，清空会破坏正文渲染。
            # 含 ACE 的 CSR 保留其 ACE Content，Br/Group 仍按原规则处理。
            orig_had_ace = '<?ACE' in orig_csr
            if orig_had_ace:
                def _ace(keep_br):
                    return _clear_content_preserve_ace(
                        orig_csr, keep_br=keep_br,
                        strip_groups=is_split_copy)
                if is_punct:
                    if has_br and is_trailing and orig_all_ws:
                        csr_replacements[ci] = _ace(True)
                    else:
                        csr_replacements[ci] = _ace(False)
                elif is_close_trailing and not orig_had_text:
                    csr_replacements[ci] = _ace(True)
                elif is_split_copy:
                    csr_replacements[ci] = _clear_content_preserve_ace(
                        orig_csr, keep_br=False, strip_groups=True)
                elif not is_leading and not is_trailing \
                        and has_br and orig_all_ws:
                    csr_replacements[ci] = _ace(True)
                else:
                    csr_replacements[ci] = _ace(False)
                continue

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
                # A3: 分割副本 → 无记录空壳 CSR 直接删除（P3-14）。
                # 原实现输出清空后的空壳（_clear_content_strip_br），分割段
                # 数量大时（497 新句读结果 4317 个分割段）导致输出解压体积
                # 膨胀 19 倍、验证阶段扫描 1.36GB 文本耗时 20 分钟以上。
                # 空壳 CSR 无 Content/Br/Group（均已剥离），删除与保留的
                # 渲染效果等价；含 ACE 指令的 CSR 已在上方 FIX-6 分支处理，
                # 不会走到此处，ACE 内容不受影响。
                csr_replacements[ci] = _DROP_CSR
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
            punct_segments = [t for is_p, t, _, _ in segments if is_p]
            text_segments = [(is_p, t, slot) for is_p, t, slot, _ in segments
                             if not is_p]
            if text_segments:
                # CSR 带有句号样式但包含非标点内容（如 U+3000 全角空格
                # 因排版需要被赋予了 CharacterStyle/句号样式）。
                # 不作为 punct CSR 处理，fall through 到文字 CSR 逻辑。
                pass
            elif not punct_segments:
                # 无新句号 → 清空 Content
                csr_replacements[ci] = (
                    _clear_content_keep_br(orig_csr, strip_groups=is_split_copy)
                    if has_br else ''
                )
                continue
            elif punct_template:
                # v1.5.0: 逐标点用模板生成 CSR，Content 替换为实际标点
                # （旧实现 ''.join(punct_template ...) 会把 ，、？ 等
                # 新标点错误写成模板里的「。」）
                fill = ''.join(
                    _punct_csr_from_template(punct_template, t)
                    for t in punct_segments
                )
                if has_br:
                    # 模板可能无 Br → 在最后追加原 CSR 的 Br
                    br_match = re.search(r'<Br\s*/>', orig_csr)
                    if br_match and '<Br' not in fill:
                        fill += br_match.group(0)
                csr_replacements[ci] = fill
                continue
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
        has_punct_inside = any(p for p, _, _, _ in segments)

        if is_multi_content:
            # 多 Content CSR：文字按实际 content_slot 分组，标点按 after_slot 分配
            orig_lens = [len(c) for c in orig_contents]
            total_orig = sum(orig_lens)

            # 文字按实际 slot 分组，标点按 after_slot 归属到对应 Content 槽位；
            # 句号携带 after_pos（跟随字符的 slot 内偏移），支持槽内插入
            text_by_slot: dict[int, str] = {}
            punct_by_slot: dict[int, list[tuple[int, str]]] = {}
            for is_p, text, slot, pos in segments:
                if is_p:
                    sl = slot if slot is not None else 0
                    ppos = pos if pos is not None else -1
                    punct_by_slot.setdefault(sl, []).append((ppos, text))
                else:
                    sl = slot if slot is not None else 0
                    text_by_slot[sl] = text_by_slot.get(sl, '') + text

            if total_orig > 0:
                parts_xml = csr_xml
                # FIX-5: 按索引定位替换而非 str.replace(old, new, 1)。
                # 多个相同 Content 文本（如多个空 <Content></Content>）时，
                # replace 顺序替换会错位（把前一个槽位的内容写入后一个）。
                # 用 cursor 从上次替换位置继续搜索，保证一一对应。
                cursor = 0
                for oi, ol in enumerate(orig_lens):
                    part_text = text_by_slot.get(oi, '')
                    # 句号按 after_pos 在 slot 内部插入（隐患 2 修复）：
                    # pos = 句号跟随字符在 slot 内的偏移，插入到该字符之后；
                    # 必须倒序插入——顺序插入会因 part_text 变长导致后续
                    # pos 偏移错位（丢字/错位）；pos 无效时回退到 slot 末尾
                    for ppos, ptext in sorted(
                            punct_by_slot.get(oi, []), reverse=True):
                        if 0 <= ppos < len(part_text):
                            part_text = (part_text[:ppos + 1] + ptext
                                         + part_text[ppos + 1:])
                        else:
                            part_text += ptext
                    old_ctag = f'<Content>{orig_contents[oi]}</Content>'
                    new_ctag = f'<Content>{_xml_escape(part_text)}</Content>'
                    pos = parts_xml.find(old_ctag, cursor)
                    if pos < 0:
                        raise ValueError(
                            f"重建失败：Content 槽位 {oi} 未找到"
                            f"（多 Content 定位替换失效）")
                    parts_xml = (parts_xml[:pos] + new_ctag
                                 + parts_xml[pos + len(old_ctag):])
                    cursor = pos + len(new_ctag)
                if is_split_copy:
                    parts_xml = re.sub(r'<Br\s*/>', '', parts_xml)
                csr_replacements[ci] = parts_xml
            else:
                csr_replacements[ci] = csr_xml
            continue

        if not has_punct_inside:
            # 单 Content、无拆分：全部文字合并
            text = ''.join(t for _, t, _, _ in segments)
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
            # - 句号 CSR 继承前邻文字 CSR 的前缀，确保 PointSize、
            #   AppliedFont 等属性与上下文文字一致（而非全局统一模板）
            clean_prefix = re.sub(r'<Br\s*/>', '', csr_prefix)
            clean_prefix = re.sub(
                r'<Group[^>]*>.*?</Group>', '', clean_prefix, flags=re.DOTALL
            )
            # FIX-4: 拆分副本非首段剥离 Self 属性（仅首段保留原 Self，
            # 中间/句号段复用会导致同一 Self ID 出现在多个 CSR 中）
            clean_prefix = re.sub(r'Self="[^"]*"', '', clean_prefix)
            clean_suffix = csr_xml[csr_xml.rfind('</CharacterStyleRange>'):]
            non_punct_parts = [i for i, (is_p, _, _, _) in enumerate(segments)
                               if not is_p]
            # 找到最后一个文本 segment 的索引，供句号继承其前缀
            last_text_idx: int | None = None
            parts = []
            for i, (is_p, text, _slot, _pos) in enumerate(segments):
                if is_p:
                    if last_text_idx is not None:
                        # 句号继承 last_text_idx 对应文字的前缀
                        text_pfx = csr_prefix if last_text_idx == non_punct_parts[0] else clean_prefix
                    else:
                        # 段首句号：回退到全局模板（极少见）
                        text_pfx = csr_prefix
                    # 强制 AppliedFont 为思源宋体，确保句号在所有字体中正常显示。
                    # 继承前邻文字的 PointSize 等属性（通过 text_pfx），但覆盖字体。
                    text_pfx = re.sub(
                        r'<AppliedFont\s+type="string">[^<]*</AppliedFont>',
                        '<AppliedFont type="string">思源宋体</AppliedFont>',
                        text_pfx,
                    )
                    # v1.5.0: Content 统一用 _punct_content_tag(text) 生成
                    # 实际标点（旧实现硬编码「。」或复用模板 Content，新标点
                    # 会被错误写成句号）。模板只提供样式前缀 text_pfx。
                    parts.append(
                        text_pfx
                        + _punct_content_tag(text)
                        + clean_suffix
                    )
                else:
                    pfx = csr_prefix if i == non_punct_parts[0] else clean_prefix
                    parts.append(
                        pfx
                        + f'<Content>{_xml_escape(text)}</Content>'
                        + clean_suffix
                    )
                    last_text_idx = i
            # 后缀加在整个拆分序列末尾
            parts[-1] = parts[-1].replace(clean_suffix, csr_suffix)
            csr_replacements[ci] = ''.join(parts)

    # 5. 应用替换：一次拼接（O(L)，P3-14 性能修复）
    # 原实现从后往前逐个替换，每个替换都是 O(len) 切片+拼接，
    # K 个替换 → O(K×L)。大经书（497）的 Story_u562 有 25 万 CSR、
    # 单段最大 1.4MB、分割段 4300+，该写法触发二次方退化，单 Story
    # 重建耗时数分钟（表现为生成输出进度条长时间停滞）。
    # 所有 match 位置均基于 original_psr_xml 的原始偏移，一次拼接
    # 即可正确应用全部替换（每个字符只复制一次）。
    #
    # 关键细节（P3-14 空壳删除）：
    # - PSR 开标签与模板前缀（第一个 CSR 之前的内容）必须无条件保留，
    #   否则第一个 CSR 被 _DROP_CSR 删除时开标签随之丢失（275 回归
    #   出现"预期 9 段实际 8 段"）。
    # - 被删 CSR（_DROP_CSR）仅跳过其自身原文区间，CSR 之间的
    #   格式化空白（换行/缩进）与后续保留 CSR 的前置文本照常保留。
    # - 替换为空串 '' 的 CSR（A1/A4 等旧行为）走正常保留分支，
    #   效果是删除该 CSR 原文、前后文本直接相连，与原来一致。
    first_csr_start = (csr_list[0]['match'].start()
                       if csr_list else len(original_psr_xml))
    psr_head = original_psr_xml[:first_csr_start]
    parts: list[str] = [psr_head]
    cursor = first_csr_start
    for ci in range(len(csr_list)):
        if ci not in csr_replacements:
            continue
        repl = csr_replacements[ci]
        m = csr_list[ci]['match']
        if repl is _DROP_CSR:
            cursor = m.end()  # 跳过被删空壳 CSR 的原文区间
            continue
        parts.append(original_psr_xml[cursor:m.start()])
        parts.append(repl)
        cursor = m.end()
    parts.append(original_psr_xml[cursor:])
    result = ''.join(parts)

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


def _clear_content_preserve_ace(
    csr_xml: str, keep_br: bool, strip_groups: bool = False
) -> str:
    """清空非 ACE 的 Content，保留含 <?ACE 加工指令的 Content 文本。

    InDesign 的 `<?ACE N?>` 是字形替换加工指令（如连字/异形字替换），
    位于正文 Story 中时清空会破坏正文渲染。此函数用于无记录 CSR 的清理：
    ACE Content 原样保留，其余 Content 清空为空壳。

    Args:
        keep_br: True 保留 Br（A1/A2/A3.5 语义），False 剥离（A3/A4 语义）。
        strip_groups: 是否剥离 Group 元素（分割副本需 True 防重复 Self ID）。
    """
    result = csr_xml
    if not keep_br:
        result = re.sub(r'<Br\s*/>', '', result)
    if strip_groups:
        result = re.sub(r'<Group[^>]*>.*?</Group>', '', result, flags=re.DOTALL)
    result = re.sub(
        r'<Content>.*?</Content>',
        lambda m: m.group(0) if '<?ACE' in m.group(0) else '<Content></Content>',
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


def _rebuild_one_story(
    story: dict,
    story_idx: int,
    meta: dict,
    split_sources: dict,
    global_punct_template: str | None,
) -> tuple[str, int, int, int]:
    """重建单个 Story 的完整 XML（含分割段落处理）。

    返回: (story_xml, rebuilt_count, unchanged_count, split_count)
    """
    max_orig_para_idx = len(story['paragraphs'])

    # 构建 (position, para_xml) 列表用于排序
    # position: 原始段落用 para_idx，分割段落用 source_para_idx + 0.5
    positioned_parts: list[tuple[float, str]] = []
    rebuilt_count = 0
    unchanged_count = 0

    # 处理原始段落
    for para_idx, para in enumerate(story['paragraphs']):
        para_records = meta.get(para_idx, [])

        if para_records:
            new_psr_xml = _rebuild_paragraph_xml(
                para['raw_xml'], para_records, global_punct_template
            )
            rebuilt_count += 1
        else:
            new_psr_xml = para['raw_xml']
            unchanged_count += 1

        positioned_parts.append((float(para_idx), new_psr_xml))

    # 处理因空行边界而分割出的新段落（para_idx >= max_orig_para_idx）
    extra_para_indices = sorted(
        [pi for pi in meta if pi >= max_orig_para_idx]
    )
    split_count = 0
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
        split_count += 1

    # 按位置排序
    positioned_parts.sort(key=lambda x: x[0])
    story_xml_parts = [pxml for _, pxml in positioned_parts]

    return (
        _rebuild_story_xml(story['xml_header'], story_xml_parts, story['xml_footer']),
        rebuilt_count,
        unchanged_count,
        split_count,
    )


def generate_idml(
    idml_path: str,
    stories: list[dict],
    grouped_records: dict,
    split_sources: dict,
    output_path: str,
) -> None:
    """将新字符记录写回 IDML（流式，不驻留全部 Story XML）。

    核心流程:
        1. 预扫描全局句号 CSR 模板（用于没有原句号 CSR 的段落）
        2. 打开输入 ZIP 与临时输出 ZIP，逐成员处理：
           - 需要修改的 Story：重建后直写
           - 其余成员（图片、字体、designmap 等）：流式拷贝
        3. 原子替换为输出文件

    参数:
        idml_path: 原始 IDML 文件路径。
        stories: extract_from_idml() 返回的 stories 列表。
        grouped_records: validate_and_align() 返回的分组记录字典。
            grouped_records[story_idx][para_idx] = 该段落的新字符记录列表。
        split_sources: dict mapping (story_idx, effective_para_idx) → original_para_idx
            指示分割产生的新段落的来源段落。
        output_path: 输出 IDML 文件的路径。
    """
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

    # story_name → (story_idx, story)
    story_by_name: dict[str, tuple[int, dict]] = {
        story['name']: (idx, story) for idx, story in enumerate(stories)
    }
    # 需要修改的 story_name 集合（grouped_records 的 key 是 story_idx）
    modified_names = {
        stories[story_idx]['name']
        for story_idx in grouped_records
        if story_idx < len(stories)
    }

    para_rebuilt_count = 0
    para_unchanged_count = 0
    para_split_count = 0

    tmp_path = output_path + '.tmp'
    try:
        with zipfile.ZipFile(idml_path, 'r') as in_zf, \
             zipfile.ZipFile(tmp_path, 'w') as out_zf:
            infos = in_zf.infolist()
            n_total = len(infos)
            for i, zinfo in enumerate(infos, 1):
                name = zinfo.filename
                m = re.match(r'^Stories/Story_(.+)\.xml$', name)
                if m and m.group(1) in modified_names:
                    story_name = m.group(1)
                    story_idx, story = story_by_name[story_name]
                    meta = grouped_records.get(story_idx, {})
                    # P3-14: 大 Story 重建耗时可达数分钟（如 497 的
                    # Story_u562：71MB、581 原始段 + 4300+ 分割段）。
                    # 重建前先给出状态消息，避免进度条长时间停滞被误认为
                    # 程序卡死；TTY 下 \r 覆盖，非 TTY 下留一行日志。
                    n_split = sum(
                        1 for pi in meta if pi >= len(story['paragraphs'])
                    )
                    _log_progress(
                        f"\r  写回 {story_name}  {_progress_bar(i - 1, n_total)}"
                        f"  正在重建（{len(story['paragraphs'])} 原始段"
                        f" + {n_split} 分割段）...")
                    new_xml, r_count, u_count, s_count = _rebuild_one_story(
                        story, story_idx, meta, split_sources,
                        global_punct_template,
                    )
                    para_rebuilt_count += r_count
                    para_unchanged_count += u_count
                    para_split_count += s_count
                    out_zf.writestr(zinfo, new_xml.encode('utf-8'))
                    if n_total > 10:
                        _log_progress(
                            f"\r  写回 {story_name} "
                            f"{_progress_bar(i, n_total)}")
                    else:
                        print(f"  写回 [{i}/{n_total}] {story_name} "
                              f"(重建 {r_count} + 不变 {u_count} + 分割 {s_count})")
                else:
                    with in_zf.open(zinfo) as src, out_zf.open(zinfo, 'w') as dst:
                        shutil.copyfileobj(src, dst)
                if n_total > 10 and i % 10 == 0:
                    _log_progress(
                        f"\r  写回 {name} "
                        f"{_progress_bar(i, n_total)}")
        if n_total > 10:
            # P3-14: 循环结束后强制显示 100%，避免进度条停留在
            # (n-1) 处未收尾（原实现仅依赖 %10 节流更新）。
            _log_progress(f"\r  写回完成  {_progress_bar(n_total, n_total)}")
            print()
        os.replace(tmp_path, output_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    print(f"  重建 {para_rebuilt_count} 个段落，{para_unchanged_count} 个段落保持不变，"
          f"{para_split_count} 个新段落（来自分割）")


def _count_br(xml: str) -> int:
    """统计 XML 中 Br 标签数量（<Br /> 与 <Br/> 两种写法）。

    P3-9(#26): 原在 _verify_structure / _verify_br_count 中重复定义，提取为模块级。
    """
    return xml.count('<Br />') + xml.count('<Br/>')


def _read_story_xmls(path: str) -> dict[str, str]:
    """一次打开 ZIP、一次解压全部 Story XML。

    返回: {story_path（如 Stories/Story_u4e8.xml）: xml}
    供 _verify_structure / _verify_br_count / _verify_output 共享，
    将验证链的全量解压扫描从 7 次合并为 2 次（输入 1 次 + 输出 1 次）。
    """
    result: dict[str, str] = {}
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            if name.startswith('Stories/Story_'):
                result[name] = zf.read(name).decode('utf-8')
    return result


def _verify_structure(
    in_story_xmls: dict[str, str],
    out_story_xmls: dict[str, str],
    stories: list[dict], split_sources: dict,
    grouped_records: dict,
    output_path: str,
) -> None:
    """输出 IDML 结构完整性验证（在写入 ZIP 后、返回前调用）。

    检查项：
    1. Group Self ID 全局唯一（防止模板复制导致的重复 ID）
    2. Br 数量在合理范围内（防止大量丢失或多余）
    3. 分割段落无 leading Br（防止段首空行/隐形字符）
    4. 段落数一致性
    5. 所有文字 Content 可被正确解析

    任何检查失败都会删除输出文件并抛出 ValueError。

    参数: in_story_xmls/out_story_xmls 由 _read_story_xmls 预加载共享，
    避免多次全量解压扫描。
    """
    errors: list[str] = []

    # ---- 1: Group Self ID 唯一性 ----
    group_ids: dict[str, list[str]] = {}  # {id: [story_name, ...]}
    for name, xml in out_story_xmls.items():
        for gid in re.findall(r'Self="([^"]+)"', xml):
            group_ids.setdefault(gid, []).append(name)

    dup_groups = {gid: stories for gid, stories in group_ids.items()
                  if len(stories) > 1}
    if dup_groups:
        details = ', '.join(
            f'{gid}(×{len(s)})' for gid, s in dup_groups.items()
        )
        errors.append(
            f"Group Self ID 重复: {details}"
            f"（可能由拆分复制未剥离 Self/Group 导致）"
        )

    # ---- 2: Br 数量合理性 ----
    csr_pattern = (
        r'<CharacterStyleRange([^>]*?CharacterStyle/句号[^>]*?)>'
        r'.*?</CharacterStyleRange>'
    )

    in_br_total = 0
    out_br_total = 0
    br_in_old_punct = 0
    br_in_orig_empty = 0

    for name, in_xml in in_story_xmls.items():
        out_xml = out_story_xmls.get(name, '')

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
    # P2-5: 只检查 split_sources 指定的分割段落，而非遍历全部段落。
    # 分割段落在输出中的 PSR 索引 = 原段落 (orig_pi+1) 个 + 前面
    # orig_pi' < orig_pi 的同 Story 分割段落数（position = orig_pi+0.5 排序）。
    #
    # P3-14: 原实现对每个分割段都重新 finditer 整个 Story XML（O(分割段数×
    # 文本大小)）。497 的 Story_u562 有 4319 个分割段、输出解压 219MB，
    # 该写法需重复扫描约 1TB 文本，验证阶段耗时 15 分钟以上（表现为
    # [5/5] 验证输出长时间无反馈）。改为按 Story 分组缓存 PSR 列表：
    # 每个 Story 只 finditer 一次（O(分割段数 + 文本大小)）。
    psr_cache: dict[str, list] = {}
    for (si, _new_pi), _orig_pi in split_sources.items():
        story_path = f'Stories/Story_{stories[si]["name"]}.xml'
        if story_path not in out_story_xmls:
            continue
        if story_path not in psr_cache:
            psr_cache[story_path] = list(re.finditer(
                r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>',
                out_story_xmls[story_path], re.DOTALL
            ))

    for (si, new_pi), orig_pi in split_sources.items():
        story_path = f'Stories/Story_{stories[si]["name"]}.xml'
        psrs = psr_cache.get(story_path)
        if not psrs:
            continue
        splits_of_story = sorted(
            (op, np) for (s, np), op in split_sources.items() if s == si
        )
        before_splits = sum(1 for op, _ in splits_of_story if op < orig_pi)
        out_idx = orig_pi + 1 + before_splits
        if out_idx >= len(psrs):
            continue
        psr = psrs[out_idx]
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
                    f"分割段落 Para[{out_idx}] CSR[{j}] 存在 leading Br"
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
        if story_path in out_story_xmls:
            # P3-13: 统计口径与 _parse_story_xml 一致（配对段 + 自闭合段
            # 各计 1 个），避免 footer 残留自闭合空段时开标签数与段落数漂移
            actual_total += len(re.findall(
                r'<ParagraphStyleRange[^>]*?/>'
                r'|<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>',
                out_story_xmls[story_path], re.DOTALL
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


def _verify_br_count(
    in_story_xmls: dict[str, str],
    out_story_xmls: dict[str, str],
) -> None:
    """报告输入/输出 IDML 的 Br 数量变化（纯计算，不重复读盘）。

    预期变化：
    1. 旧句号 CSR 的 Br → 清除（句号由新 punct 模板接管）
    2. 被清空的文字 CSR 的 Br → 清除（段落分割后原 Br 不重复保留）

    字符级输出验证（_verify_output）是真正的质量保证。
    """
    csr_pattern = r'<CharacterStyleRange([^>]*?CharacterStyle/句号[^>]*?)>.*?</CharacterStyleRange>'

    in_br_total = 0
    out_br_total = 0
    br_in_old_punct = 0

    for name, in_xml in in_story_xmls.items():
        out_xml = out_story_xmls.get(name, '')
        in_br_total += _count_br(in_xml)
        out_br_total += _count_br(out_xml)
        br_in_old_punct += sum(
            _count_br(m.group(0))
            for m in re.finditer(csr_pattern, in_xml, re.DOTALL)
        )

    br_cleared_text = in_br_total - br_in_old_punct - out_br_total

    # P3-4: br_cleared_text 为负时给出提示而非直接打印负数
    #（输出 Br 多于「输入−旧句号清除」，常见于新增句号模板自带 Br，非错误）
    if br_cleared_text < 0:
        print(f"  Br 统计: 输入 {in_br_total} → 输出 {out_br_total}"
              f"（旧句号清除 {br_in_old_punct}, 清空文字 CSR 清除 {br_cleared_text}）")
        print(f"  [提示] 清除数为负：输出 Br 比预期多 {-br_cleared_text} 个，"
              f"通常来自新增句号模板携带的 Br（属正常情况，非错误）")
    else:
        print(f"  Br 统计: 输入 {in_br_total} → 输出 {out_br_total}"
              f"（旧句号清除 {br_in_old_punct}, 清空文字 CSR 清除 {br_cleared_text}）")


def _verify_output(
    output_path: str,
    expected_chars: list[str],
    preloaded_xmls: dict[str, str] | None = None,
    expected_special: set[str] | None = None,
    min_clean_chars: int = 50,
) -> None:
    """输出自检：从生成的 IDML 重新提取字符序列并与输入比对。

    如果发现任何差异，立即删除输出文件并抛出异常。
    这是防止写入过程（XML 重建、ZIP 打包）引入数据丢失的最后一道防线。

    参数: preloaded_xmls 由 _read_story_xmls 预加载共享，
    避免全量解压扫描与 Story XML 二次驻留。
    expected_special: 输入 IDML 提取的 is_special 指令集合（如 <?ACE N?>）。
    传入时核对输出保留情况（FIX-6）。
    min_clean_chars: 正文 Story 判定阈值（P2-8，与 validate_and_align 一致）。
    """
    # 重新提取（复用预加载的 Story XML，避免再次解压）
    stories = extract_from_idml(output_path, preloaded_xmls=preloaded_xmls)
    all_records: list[dict] = []
    for story in stories:
        story_clean = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean < min_clean_chars:
            continue
        for para in story['paragraphs']:
            for rec in para['chars']:
                all_records.append(rec)

    # 构建输出字符序列：
    # - 跳过 Unicode 空白（_is_unicode_whitespace）
    # - 保留 U+3000（它在 _is_unicode_whitespace 中返回 False）
    # - 保留所有可见字符和标点（v1.5.0 起含白名单标点）
    # FIX-6: is_special 指令（ACE 等）单独收集核对，不混入正文字符序列
    output_chars: list[str] = []
    output_special: set[str] = set()
    for rec in all_records:
        if rec.get('is_special', False):
            output_special.add(rec['char'])
            continue
        ch = rec['char']
        if _is_unicode_whitespace(ch):
            continue
        output_chars.append(ch)

    # expected_chars 也按同规则处理（跳过 unicode_whitespace）
    expected_filtered = [
        c for c in expected_chars
        if not _is_unicode_whitespace(c)
    ]
    expected_str = ''.join(expected_filtered)
    output_str = ''.join(output_chars)

    # FIX-6: is_special 指令集合核对（输入输出一致）。
    # 若输入正文含 ACE 指令而输出丢失，立即报错，防止静默破坏正文渲染。
    if expected_special is not None and output_special != expected_special:
        missing = sorted(expected_special - output_special)
        extra = sorted(output_special - expected_special)
        try:
            os.remove(output_path)
        except OSError:
            pass
        raise ValueError(
            f"输出 IDML 验证失败！is_special 指令集合不一致"
            f"（输出文件已删除: {output_path}）\n"
            f"  输入有但输出丢失: {missing}\n"
            f"  输出有但输入没有: {extra}\n"
            f"这通常意味着正文 Story 内嵌的 ACE 等加工指令在重建时被清空。"
        )

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


def process(idml_path, result_path, output_path, min_clean_chars: int = 50):
    """主处理流程

    Args:
        min_clean_chars: 正文 Story 判定阈值（P2-8，默认 50）。
    """
    t0 = time.time()
    print("=" * 60)
    print("IDML 句读结果回注工具")
    print("=" * 60)

    # Step 1: 从 IDML 提取（含提取自检）
    print("\n[1/5] 解析 IDML...")
    stories = extract_from_idml(idml_path)
    total_chars = sum(
        len(p['chars']) for s in stories for p in s['paragraphs']
    )
    print(f"  提取 {len(stories)} 个 Story, {total_chars} 个字符记录"
          f"{_mem_suffix()}")

    # Step 2: 从句读结果提取
    print("\n[2/5] 读取句读结果...")
    result_data = extract_from_result(result_path)
    result_chars = result_data['chars']
    punct_counts = {p: result_chars.count(p) for p in _INJECTABLE_PUNCT}
    punct_total = sum(punct_counts.values())
    punct_breakdown = ' '.join(
        f"{p}×{n}" for p, n in punct_counts.items() if n
    )
    print(f"  提取 {len(result_chars)} 个字符"
          f"（含 {punct_total} 个标点 [{punct_breakdown}]）")
    if result_data['para_breaks']:
        print(f"  检测到 {len(result_data['para_breaks'])} 个段落边界")

    # Step 3: 验证并对齐
    print("\n[3/5] 验证并对齐...")
    alignment = validate_and_align(stories, result_data, min_clean_chars)
    grouped_records = alignment['grouped']
    split_sources = alignment['split_sources']

    # FIX-1C（P0）: 标点重合度预警 — 结果文件命名不含"句读结果"字样，
    # 且标点数量与 IDML 原旧标点数量相差 <5% 时，疑似以原文导出文本当结果。
    # （修复 B 已拦截含白名单外标点的文件；此处兜底纯句号原文的漏网场景）
    # v1.5.0: 统计口径从仅句号扩展为全部白名单标点。
    idml_punct_count = sum(
        1 for story in stories for para in story['paragraphs']
        for rec in para['chars'] if rec['char'] in _INJECTABLE_PUNCT
    )
    result_punct_count = sum(1 for c in result_chars if c in _INJECTABLE_PUNCT)
    result_base = os.path.basename(result_path)
    if "句读结果" not in result_base and idml_punct_count > 0:
        punct_diff_ratio = abs(idml_punct_count - result_punct_count) / idml_punct_count
        if punct_diff_ratio < 0.05:
            print(
                f"\n[!] 警告: 结果文件「{result_base}」命名不含「句读结果」字样，"
                f"且其标点数量（{result_punct_count}）与 IDML 原旧标点"
                f"（{idml_punct_count}）高度重合（差异 {punct_diff_ratio*100:.1f}% < 5%），"
                f"疑似以原文导出文本冒充句读结果，请人工确认后重跑。")

    # Step 4: 生成输出
    print("\n[4/5] 生成输出 IDML...")
    generate_idml(idml_path, stories, grouped_records, split_sources, output_path)
    print(f"  生成完成{_mem_suffix()}")

    # Step 5: 多层验证 — 结构 → Br → 字符
    print("\n[5/5] 验证输出 IDML...")
    # 合并读盘：输入 1 次 + 输出 1 次全量解压，三处验证共享
    in_story_xmls = _read_story_xmls(idml_path)
    out_story_xmls = _read_story_xmls(output_path)
    _verify_structure(in_story_xmls, out_story_xmls, stories,
                      split_sources, grouped_records, output_path)
    _verify_br_count(in_story_xmls, out_story_xmls)
    # 构建验证用的 expected：从 alignment new_records 提取
    # （用 new_records 而非 result_chars，因为 。 抑制已将 。 替换为 U+3000）
    verify_expected: list[str] = []
    for recs in alignment['grouped'].values():
        for recs2 in recs.values():
            for r in recs2:
                if not _is_unicode_whitespace(r['char']):
                    verify_expected.append(r['char'])
    # FIX-6: 输入 is_special 指令集合（如 <?ACE N?>），供输出核对保留情况。
    # 注意：与 _verify_output 采用相同过滤（仅统计正文 Story，clean>=50）——
    # 装饰 Story（<50）不参与重建，其 XML 原样流式拷贝，ACE 天然保留；
    # 若此处收集全部 Story，会与输出侧（仅正文）不一致造成误报。
    input_special: set[str] = set()
    for story in stories:
        story_clean = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean < min_clean_chars:
            continue
        for para in story['paragraphs']:
            for rec in para['chars']:
                if rec.get('is_special', False):
                    input_special.add(rec['char'])
    # P2-10: 释放 stories 大对象（大经书内存优化）。
    # _verify_output 用 preloaded_xmls 重新提取，不依赖 stories；
    # input_special / verify_expected 已提前计算。
    del stories
    gc.collect()
    _verify_output(output_path, verify_expected,
                   preloaded_xmls=out_story_xmls,
                   expected_special=input_special,
                   min_clean_chars=min_clean_chars)

    # P3-11: 汇总非法实体替换计数
    if _REPLACEMENT_COUNT['replaced'] > 0:
        print(f"\n[警告] 本次处理共 {_REPLACEMENT_COUNT['replaced']} 个非法"
              f"HTML 实体被替换为 U+FFFD（请检查 IDML 来源是否正常）")

    print(f"\n{'=' * 60}")
    print(f"完成！输出文件: {output_path}")
    print(f"总耗时 {time.time() - t0:.1f}s{_mem_suffix()}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    # P2-1: 强制 UTF-8 输出，避免 Windows 控制台 GBK 编码错误
    # （与 inject.bat 的 -X utf8 双保险）
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
