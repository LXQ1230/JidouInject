# -*- coding: utf-8 -*-
"""v1.5.2/1.5.3 回归测试（方案 C 标点重分配 + 括号保留）。

见 plan-csr-reuse-and-brackets-2026-08-07.md 第四章分层验证方案：
  L1 净文本对比（铁律层）：
    CASES  — 新代码输出 vs 基线输出，逐 Story 净文本完全一致
    SPECIAL— 新代码输出正文 vs 混合标点 txt（排除 U+3000/ACE/括号）
  L2 结构指标对比（靶向层）：story_metrics 逐 Story
    br/psr 必须相等（硬性）；csr 新≤旧；single1 ≤ 原始×1.3；
    oldpunct 与原始 IDML ±10%；emptycsr 显著下降；preserved_multichar
    ≥95% 硬通过 / 85-95% 警告 / <85% 失败；bracket 保留数 = 原始数
  L3 样式抽查：原始多字文字 CSR 的样式三元组
    （AppliedFont/PointSize/FillColor）在输出中按文本匹配保持一致；
    35 号句号 CSR 复用抽查（Content 为实际标点、样式来自原文）

基线：v1.5.2（括号保留实施前备份）——v1.5.3 括号保留后，无括号文件
（461/275/35）应新旧零差异；有括号文件（3093 龟甲括号 2 个）允许
「输出 = 基线 + 括号字符」的增量。

注意：v1.5.2 方案 C 必然改变 CSR 结构，字节级对比退出历史舞台，
由净文本+结构指标+样式抽查替代。
"""
import html
import io
import os
import re
import shutil
import sys
import tempfile
import types
import zipfile
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

OLD = r"D:\Desktop\JidouInject\backup\inject.py.v1.5.2-brackets-baseline-20260807.bak"
NEW = r"D:\Desktop\JidouInject\code\inject.py"

CASES = [
    ("461", r"D:\Desktop\JidouInject\done\461\461导出.idml",
     r"D:\Desktop\JidouInject\done\461\461导出_WD句读结果.md"),
    ("275", r"D:\Desktop\JidouInject\done\275\275导出.idml",
     r"D:\Desktop\JidouInject\done\275\275从ID中导出文字_WD句读结果.md"),
    ("3093", r"D:\Desktop\JidouInject\done\3093\3093偈颂测试.idml",
     r"D:\Desktop\JidouInject\done\3093\3093偈颂测试句读结果.txt"),
]

SPECIAL = [
    ("35", r"D:\Desktop\JidouInject\done\35\35导出.idml",
     r"D:\Desktop\JidouInject\done\35\35_WD句读结果_vs_35_对比文本_20260807-0900.txt"),
    # 20 号（v1.5.3）：正文含几何装饰符号（■□◎◇▲△○ 字间镶嵌）+ 校勘注
    # 全角圆括号 9 对。基线（v1.5.2/1.5.3-brackets）无法处理几何符号
    # （对齐失败），只跑新代码 vs 原始 IDML：保留符号 24 个零丢失 +
    # 正文文字 == txt（14821 字）+ 句读标点正确注入。
    ("20", r"D:\Desktop\JidouInject\pending\20.idml",
     r"D:\Desktop\JidouInject\pending\20_WD句读结果.txt"),
]

_INJECTABLE = frozenset('，、；：？！。')

# v1.5.3: 保留排版符号（与 inject.py 的 _KEEP_BRACKETS + _KEEP_ORNAMENTS
# 一致，用于 L1 排除与 bracket 指标统计）：成对符号 + 几何装饰符号
_KEEP_BRACKETS = frozenset(
    '（）()〔〕《》〈〉「」『』【】〖〗［］'
    '■□△▲○●◇◆▢▣▤▥▦▧▨▩▪▫▬▭▮▯'
    '▴▵▷▸▹►▻▽▾▿◀◁◂◃◄◅'
    '◈◉◊○◌◍◎●◐◑◒◓◔◕◖◗'
    '★☆✦✧※'
)

CSR_RE = re.compile(
    r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
    re.DOTALL,
)
PSR_OPEN_RE = re.compile(r'<ParagraphStyleRange[^>]*?>', re.DOTALL)

_STYLE_ATTRS = ('AppliedFont', 'PointSize', 'FillColor')


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def load_module(path: str, name: str):
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    mod = types.ModuleType(name)
    mod.__file__ = path
    sys.modules[name] = mod
    exec(compile(source, path, 'exec'), mod.__dict__)
    return mod


def run_process(mod, idml, result, out_path):
    """运行 process，捕获 stdout；失败时回放输出并返回异常。"""
    buf = io.StringIO()
    old_out = sys.stdout
    sys.stdout = buf
    try:
        mod.process(idml, result, out_path)
        return None
    except Exception as e:
        print(buf.getvalue())
        return (type(e).__name__, str(e))
    finally:
        sys.stdout = old_out


def story_text_contents(path: str) -> dict[str, str]:
    """提取每个 Story 的全部 Content 净文本（去 ACE 指令、解实体）。"""
    result = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            contents = re.findall(
                r'<Content>(.*?)</Content>', raw, re.DOTALL)
            text = re.sub(r'<\?.*?\?>', '', ''.join(contents))
            result[name] = html.unescape(text)
    return result


def strip_u3000(s: str) -> str:
    """排除 U+3000 分字间隔（与 IDML 保留、txt 跳过的不对称有关）。"""
    return s.replace('\u3000', '')


def split_text_punct(s: str) -> tuple[str, str]:
    """L1 诊断：把净文本拆为「文字序列」与「标点序列」两条 diff 通道。"""
    text_seq = ''.join(c for c in s if c not in _INJECTABLE)
    punct_seq = ''.join(c for c in s if c in _INJECTABLE)
    return text_seq, punct_seq


# --------------------------------------------------------------------------
# L2 结构指标
# --------------------------------------------------------------------------

def story_metrics(path: str) -> dict[str, dict]:
    """每 Story 统计指标：br/psr/csr/single1/oldpunct/emptycsr/bracket。

    oldpunct 口径：只认 `CharacterStyle/句号` 样式（v1.5.2 修正）。
    不把 Content=='。' 的兜底拆分 CSR 计入——拆分标点块继承文字前缀
    （无句号样式），若计入会虚增（461：1297→1546 假性偏离）。

    bracket（v1.5.3）：Content 内成对符号计数（输出须 == 原始，零丢失）。
    """
    result = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            br = raw.count('<Br')
            psr = len(PSR_OPEN_RE.findall(raw))
            csr = 0
            single1 = 0
            oldpunct = 0
            emptycsr = 0
            bracket = 0
            for m in CSR_RE.finditer(raw):
                attrs = m.group(1)
                inner = m.group(2) or ''
                contents = re.findall(
                    r'<Content>(.*?)</Content>', inner, re.DOTALL)
                csr += 1
                joined = ''.join(contents)
                if 'CharacterStyle/句号' in attrs:
                    oldpunct += 1
                if len(joined) == 1:
                    single1 += 1
                if not any(c.strip() for c in contents):
                    emptycsr += 1
                bracket += sum(1 for c in joined if c in _KEEP_BRACKETS)
            result[name] = {
                'br': br, 'psr': psr, 'csr': csr,
                'single1': single1, 'oldpunct': oldpunct,
                'emptycsr': emptycsr, 'bracket': bracket,
            }
    return result


def metrics_summary(m: dict[str, dict]) -> dict:
    """把 Story 级指标聚合成单条摘要（用于打印）。"""
    return {k: sum(v[k] for v in m.values()) for k in
            ('br', 'psr', 'csr', 'single1', 'oldpunct', 'emptycsr',
             'bracket')}


def preserved_multichar(orig_path: str, new_path: str) -> float:
    """原始 IDML 中多字文字 CSR（≥2 字符、非句号样式）在输出中保持为
    完整单 CSR 的比例。按 Story 内文本计数匹配（Counter min），
    输出中相同文本的单字拆分不算匹配。≥95% 为通过（方案 C 主路径证据）。"""
    def multi_counter(path):
        result = {}
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if not name.startswith('Stories/Story_'):
                    continue
                raw = zf.read(name).decode('utf-8')
                texts = []
                for m in CSR_RE.finditer(raw):
                    attrs = m.group(1)
                    inner = m.group(2) or ''
                    contents = re.findall(
                        r'<Content>(.*?)</Content>', inner, re.DOTALL)
                    joined = html.unescape(''.join(contents))
                    if ('CharacterStyle/句号' in attrs or joined == '。'):
                        continue
                    if len(joined) >= 2:
                        texts.append(joined)
                result[name] = Counter(texts)
        return result

    oc, nc = multi_counter(orig_path), multi_counter(new_path)
    total = matched = 0
    for story, ocnt in oc.items():
        ncnt = nc.get(story, Counter())
        for text, cnt in ocnt.items():
            total += cnt
            matched += min(cnt, ncnt.get(text, 0))
    return (matched / total) if total else 1.0


# --------------------------------------------------------------------------
# L3 样式抽查
# --------------------------------------------------------------------------

def style_signature(csr_xml: str) -> tuple:
    """抽取 AppliedFont/PointSize/FillColor 三元组（未命中取 None）。"""
    sigs = []
    for attr in _STYLE_ATTRS:
        m = re.search(
            rf'<{attr}[^>]*>.*?</{attr}>', csr_xml, re.DOTALL)
        sigs.append(m.group(0) if m else None)
    return tuple(sigs)


def collect_multichar_style(path: str) -> dict[str, list]:
    """{story: [(text, signature), ...]}——原始/输出两侧共用。"""
    result = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            items = []
            for m in CSR_RE.finditer(raw):
                attrs = m.group(1)
                inner = m.group(2) or ''
                contents = re.findall(
                    r'<Content>(.*?)</Content>', inner, re.DOTALL)
                joined = html.unescape(''.join(contents))
                if ('CharacterStyle/句号' in attrs or joined == '。'):
                    continue
                if len(joined) >= 2:
                    items.append((joined, style_signature(m.group(0))))
            result[name] = items
    return result


def style_check(orig_path: str, new_path: str, sample: int = 20) -> dict:
    """L3：原始多字文字 CSR 的样式三元组在输出中按文本匹配保持一致。
    返回 {checked, mismatched, examples}。"""
    oc = collect_multichar_style(orig_path)
    nc = collect_multichar_style(new_path)
    checked = 0
    mismatched = 0
    examples = []
    for story, oitems in oc.items():
        nlist = nc.get(story, [])
        # 按文本分组，组内排队匹配
        n_by_text: dict[str, list] = {}
        for t, sig in nlist:
            n_by_text.setdefault(t, []).append(sig)
        for t, sig in oitems:
            if checked >= sample and mismatched:
                break
            if checked >= sample:
                break
            pool = n_by_text.get(t)
            if not pool:
                continue  # 输出中未保留该多字 CSR（计入 preserved 但样式抽查跳过）
            used = pool.pop(0)
            checked += 1
            if used != sig:
                mismatched += 1
                if len(examples) < 5:
                    examples.append(
                        f"[{story}] 文本「{t[:20]}」: 原 {sig} vs 新 {used}")
        if checked >= sample and mismatched:
            break
        if checked >= sample and not mismatched:
            break
    return {'checked': checked, 'mismatched': mismatched,
            'examples': examples}


# --------------------------------------------------------------------------
# L1 诊断
# --------------------------------------------------------------------------

def diff_report(name: str, old_text: str, new_text: str) -> list[str]:
    lines = [f"  Story {name}: 净文本长度 旧 {len(old_text)} vs 新 {len(new_text)}"]
    ot, op = split_text_punct(old_text)
    nt, np_ = split_text_punct(new_text)
    if ot != nt:
        # 找第一个文字差异位置
        k = next((i for i, (a, b) in enumerate(zip(ot, nt)) if a != b),
                 min(len(ot), len(nt)))
        lines.append(f"    文字序列差异 @{k}: 旧「{ot[max(0,k-5):k+5]}」"
                     f" vs 新「{nt[max(0,k-5):k+5]}」")
    else:
        lines.append(f"    文字序列一致（{len(ot)} 字）")
    if op != np_:
        k = next((i for i, (a, b) in enumerate(zip(op, np_)) if a != b),
                 min(len(op), len(np_)))
        lines.append(f"    标点序列差异 @{k}: 旧「{op[max(0,k-5):k+5]}」"
                     f" vs 新「{np_[max(0,k-5):k+5]}」（{len(op)} vs {len(np_)}）")
    else:
        lines.append(f"    标点序列一致（{len(op)} 个）")
    return lines


# --------------------------------------------------------------------------
# 35 号专项检查
# --------------------------------------------------------------------------

def check_dunju_structure(path: str) -> dict:
    """35 号专项：净文本「時、離垢施女、則為梵志而說頌曰」位置不应逐字拆分。
    判定：找到「離垢施女、」（后跟顿号的那个，txt 有两处「離垢施」但只有
    「離垢施女、」对应方案 C 原始复现点），验证该 CSR 的 Content 含
    「離垢施女」整块（≥4 字未拆散），且紧随其后存在句号样式 CSR 承载「、」。
    注意：35 号 u621 有分割段副本，副本同样含该文本；须继续搜索直到找到
    结构合法的位置（副本中若「離垢施女」恰在段尾会越界，跳过）。
    """
    out = {'found': False, 'ok': False, 'detail': ''}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            if '離垢施女' not in raw:
                continue
            # 跳过装饰 Story（<50 字，不参与对齐；35 号有页眉
            # 「佛說離垢施女經」在 u53b 等装饰 Story，须找正文 u621）
            body = sum(1 for m in CSR_RE.finditer(raw)
                       for c in re.findall(
                           r'<Content>(.*?)</Content>', m.group(2) or '',
                           re.DOTALL)
                       if c.strip() and not c.isspace())
            if body < 50:
                continue
            items = []  # (csr_text, csr_xml, is_old_punct)
            for m in CSR_RE.finditer(raw):
                attrs = m.group(1)
                inner = m.group(2) or ''
                contents = re.findall(
                    r'<Content>(.*?)</Content>', inner, re.DOTALL)
                joined = ''.join(contents)
                is_op = ('CharacterStyle/句号' in attrs or joined == '。')
                items.append((joined, m.group(0), is_op))
            lens = [len(t) for t, _, _ in items]
            full = ''.join(t for t, _, _ in items)
            # 依次尝试所有「離垢施女、」出现位置
            search_from = 0
            while True:
                pos = full.find('離垢施女、', search_from)
                if pos < 0:
                    break
                search_from = pos + 1
                acc = 0
                ci = 0
                for i, ln in enumerate(lens):
                    if pos < acc + ln:
                        ci = i
                        break
                    acc += ln
                if ci + 1 >= len(items):
                    continue  # 后邻越界（如分割段尾），尝试下一个位置
                csr_text, csr_xml, _ = items[ci]
                inner_idx = pos - acc
                has_four = csr_text[inner_idx:inner_idx + 4] == '離垢施女'
                nt, nxml, nop = items[ci + 1]
                next_punct_ok = (nop and nt == '、')
                if has_four and next_punct_ok:
                    out['found'] = True
                    out['ok'] = True
                    out['detail'] = (
                        f"「離垢施女」所在 CSR Content len={len(csr_text)} "
                        f"(含 4 字整块=是)；后邻句号 CSR Content=「、」")
                    return out
            # 无合法位置：输出首个「離垢施女」的定位详情供诊断
            pos = full.find('離垢施女')
            if pos >= 0:
                acc = 0
                ci = 0
                for i, ln in enumerate(lens):
                    if pos < acc + ln:
                        ci = i
                        break
                    acc += ln
                csr_text = items[ci][0]
                inner_idx = pos - acc
                out['found'] = True
                out['ok'] = False
                nxt = items[ci + 1][0] if ci + 1 < len(items) else '(段尾)'
                out['detail'] = (
                    f"「離垢施女」所在 CSR Content len={len(csr_text)} "
                    f"(含 4 字整块="
                    f"{'是' if csr_text[inner_idx:inner_idx+4] == '離垢施女' else '否'})；"
                    f"后邻 CSR Content=「{nxt}」"
                    f"句号样式="
                    f"{'是' if ci+1 < len(items) and items[ci+1][2] else '否'}")
            break
    return out


def count_reused_punct(path: str) -> dict:
    """SPECIAL L3：输出中句号样式 CSR 的 Content 分布（复用抽查）。
    返回 {non_dot_count, dot_count, sample_styles, ok}。"""
    non_dot = 0
    dot = 0
    samples = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            for m in CSR_RE.finditer(raw):
                attrs = m.group(1)
                inner = m.group(2) or ''
                contents = re.findall(
                    r'<Content>(.*?)</Content>', inner, re.DOTALL)
                joined = ''.join(contents)
                if 'CharacterStyle/句号' not in attrs:
                    continue
                if joined == '。':
                    dot += 1
                elif joined and all(c in _INJECTABLE for c in joined):
                    non_dot += 1
                    if len(samples) < 5:
                        samples.append(
                            (joined, style_signature(m.group(0))))
    return {'non_dot': non_dot, 'dot': dot, 'samples': samples}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def main():
    old_mod = load_module(OLD, "inject_old")
    new_mod = load_module(NEW, "inject_new")
    print(f"旧代码(基线): {OLD}")
    print(f"新代码(v1.5.2): {NEW}")
    print()

    tmp = tempfile.mkdtemp(prefix="reg_v152_")
    all_ok = True
    try:
        # ---- CASES: 461 / 275 / 3093（新 vs 旧基线） ----
        for name, idml, result in CASES:
            print(f"=== {name}: {os.path.basename(idml)} + "
                  f"{os.path.basename(result)} ===")
            if not (os.path.isfile(idml) and os.path.isfile(result)):
                print("    [跳过] 文件缺失")
                continue
            out_old = os.path.join(tmp, f"{name}_old.idml")
            out_new = os.path.join(tmp, f"{name}_new.idml")
            print("  [旧代码] 处理中...")
            err = run_process(old_mod, idml, result, out_old)
            if err:
                print(f"    [失败] 旧代码: {err[0]}: {err[1]}")
                all_ok = False
                continue
            print("  [新代码] 处理中...")
            err = run_process(new_mod, idml, result, out_new)
            if err:
                print(f"    [失败] 新代码: {err[0]}: {err[1]}")
                all_ok = False
                continue

            # ---- L1: 净文本逐 Story 一致（v1.5.3 允许括号增量） ----
            # 基线（v1.5.2）不含括号；v1.5.3 保留括号后，有括号文件的
            # 净文本 = 基线 + 括号字符。对比时排除括号（strip_brackets），
            # 无括号文件（461/275/35）保持严格一致语义。
            c_old = story_text_contents(out_old)
            c_new = story_text_contents(out_new)
            l1_ok = True
            for story in sorted(set(c_old) | set(c_new)):
                if story not in c_old:
                    l1_ok = False
                    print(f"    [L1失败] Story {story} 在旧输出缺失")
                    continue
                if story not in c_new:
                    l1_ok = False
                    print(f"    [L1失败] Story {story} 在新输出缺失")
                    continue
                a = ''.join(c for c in c_old[story] if c not in _KEEP_BRACKETS)
                b = ''.join(c for c in c_new[story] if c not in _KEEP_BRACKETS)
                if a != b:
                    l1_ok = False
                    for line in diff_report(story, c_old[story], c_new[story]):
                        print(f"    {line}")
            print(f"  [L1 净文本] {'通过（逐 Story 一致，含括号增量豁免）' if l1_ok else '失败'}")

            # ---- L2: 结构指标 ----
            m_old = story_metrics(out_old)
            m_new = story_metrics(out_new)
            s_old = metrics_summary(m_old)
            s_new = metrics_summary(m_new)
            orig_metrics = metrics_summary(story_metrics(idml))
            l2_errors = []
            l2_warns = []
            for story in sorted(set(m_old) | set(m_new)):
                a, b = m_old.get(story), m_new.get(story)
                if not a or not b:
                    continue
                if a['br'] != b['br']:
                    l2_errors.append(f"br {story}: 旧{a['br']} vs 新{b['br']}")
                if a['psr'] != b['psr']:
                    l2_errors.append(f"psr {story}: 旧{a['psr']} vs 新{b['psr']}")
                if b['csr'] > a['csr']:
                    l2_errors.append(f"csr 不降 {story}: 旧{a['csr']} vs 新{b['csr']}")
            # single1 对比原始 IDML（v1.5.2 判定）：逐字拆分消除后应回到
            # 原文水平（275 原始即逐字 CSR 结构：2669→新 2674 ✓）。
            # 允许少量兜底句号（无法重分配的标点各产生 1 个单字 CSR）。
            s_orig = metrics_summary(story_metrics(idml))
            if s_new['single1'] > s_orig['single1'] * 1.3:
                l2_errors.append(
                    f"single1 {s_new['single1']} > 原始×1.3"
                    f"（{s_orig['single1']:.0f}）——逐字拆分未充分消除")
            # oldpunct 与原始 IDML ±10%（只认句号样式口径）
            op_new = sum(v['oldpunct'] for v in m_new.values())
            op_orig = orig_metrics['oldpunct']
            if op_orig > 0 and abs(op_new - op_orig) > op_orig * 0.10:
                l2_errors.append(
                    f"oldpunct 偏离原始 ±10%: 原始{op_orig} vs 新{op_new}")
            # v1.5.3: 括号零丢失（输出 == 原始；基线 v1.5.2 无括号时
            # 新输出保留括号属预期增量，判定以原始 IDML 为准）
            brk_new = sum(v['bracket'] for v in m_new.values())
            brk_orig = orig_metrics['bracket']
            if brk_new != brk_orig:
                l2_errors.append(
                    f"bracket 保留数不一致: 原始{brk_orig} vs 新{brk_new}"
                    f"（成对符号零丢失要求）")
            # emptycsr 显著下降
            ec_old = s_old['emptycsr']
            ec_new = s_new['emptycsr']
            if ec_new >= ec_old:
                l2_warns.append(f"emptycsr 未下降: 旧{ec_old} vs 新{ec_new}")
            # preserved_multichar ≥ 95% 硬通过；85-95% 警告（461 数据特性：
            # txt 句读密度高、IDML 长句块多，句号在 CSR 中间属必要拆分）；
            # <85% 失败
            pm = preserved_multichar(idml, out_new)
            if pm < 0.85:
                l2_errors.append(f"preserved_multichar {pm:.1%} < 85%")
            elif pm < 0.95:
                l2_warns.append(f"preserved_multichar {pm:.1%}（85-95% 区间，"
                                f"拆分为必要拆分——句号位于 CSR 中间或"
                                f"后邻非句号 CSR）")
            print(f"  [L2 结构] csr {s_old['csr']}→{s_new['csr']} | "
                  f"single1 {s_old['single1']}→{s_new['single1']}"
                  f"（原始 {s_orig['single1']}）| "
                  f"emptycsr {ec_old}→{ec_new} | "
                  f"oldpunct 新{op_new}(原始{op_orig}) | "
                  f"preserved {pm:.1%} | "
                  f"bracket 新{brk_new}(原始{brk_orig})")
            for w in l2_warns:
                print(f"    [L2提示] {w}")
            if l2_errors:
                for e in l2_errors:
                    print(f"    [L2失败] {e}")
            else:
                print("  [L2 结构] 通过")

            # ---- L3: 样式抽查 ----
            sc = style_check(idml, out_new)
            if sc['mismatched']:
                print(f"  [L3失败] 样式差异 {sc['mismatched']}/{sc['checked']}")
                for ex in sc['examples']:
                    print(f"    {ex}")
            else:
                print(f"  [L3 样式] 通过（抽查 {sc['checked']} 个，0 差异）")

            ok = l1_ok and not l2_errors and sc['mismatched'] == 0
            all_ok = all_ok and ok
            print(f"  → {'通过 ✓' if ok else '失败 ✗'}\n")

        # ---- SPECIAL: 35（混合标点）/ 20（几何符号+校勘注），新代码 vs 原始 ----
        for name, idml, result in SPECIAL:
            kind = '混合标点' if name == '35' else '纯句号+保留符号'
            print(f"=== SPECIAL {name}: {os.path.basename(idml)} + "
                  f"{os.path.basename(result)}（{kind}） ===")
            if not (os.path.isfile(idml) and os.path.isfile(result)):
                print("    [跳过] 文件缺失")
                continue
            out_new = os.path.join(tmp, f"{name}_new.idml")
            print("  [新代码] 处理中...")
            err = run_process(new_mod, idml, result, out_new)
            if err:
                print(f"    [失败] 新代码: {err[0]}: {err[1]}")
                all_ok = False
                continue

            # ---- L1: 正文文字序列 vs txt ----
            # 说明：IDML 正文 Story（clean>=50，本用例为 Story_u621）与 txt
            # 完全对应（u621 文字 10038 == txt 文字 10038，逐字 0 差异）；
            # 题记/装饰内容在 <50 的装饰 Story 中，不参与对齐、原样保留。
            # 且 _should_suppress_punct 会丢弃部分 txt 标点（仿宋/楷体区域、
            # U+3000 间隔，v1.5.0 既有规则），IDML 的 ASCII 空格/U+3000
            # 作为布局空白被对齐跳过（_is_unicode_whitespace 语义）。
            # 故 L1 判定 = 输出正文 Story 的「文字序列（去标点/去全部空白）」
            # == txt 文字序列（注入正确 + 原文零改动的核心证据）。
            c_new = story_text_contents(out_new)
            body_chars: list[str] = []
            for story, text in c_new.items():
                clean = sum(1 for c in text
                            if c not in _INJECTABLE and not c.isspace()
                            and c not in _KEEP_BRACKETS)
                if clean < 50:
                    continue  # 装饰 Story：不参与对齐
                body_chars.extend(
                    c for c in text
                    if c not in _INJECTABLE and not c.isspace()
                    and c not in _KEEP_BRACKETS)  # v1.5.3: 括号是 IDML 保留
            txt_chars = [
                c for c in open(result, encoding='utf-8').read()
                .replace('\r', '').replace('\n', '')
                if c not in _INJECTABLE and not c.isspace()
                and c not in _KEEP_BRACKETS]
            out_text = ''.join(body_chars)
            txt_text = ''.join(txt_chars)
            l1_ok = (out_text == txt_text)
            if not l1_ok:
                k = next(
                    (i for i, (a, b) in enumerate(zip(out_text, txt_text))
                     if a != b),
                    min(len(out_text), len(txt_text)))
                print(f"    文字序列差异 @{k}: "
                      f"输出「{out_text[max(0,k-5):k+5]}」 vs "
                      f"txt「{txt_text[max(0,k-5):k+5]}」"
                      f"（长度 {len(out_text)} vs {len(txt_text)}）")
            print(f"  [L1 正文文字 vs txt] "
                  f"{'通过（一致）' if l1_ok else '失败'} "
                  f"（{len(txt_text)} 字）")

            # ---- L2: csr ≤ 原始×1.5、体积、符号零丢失、35 号无逐字 ----
            orig_metrics = metrics_summary(story_metrics(idml))
            new_metrics = metrics_summary(story_metrics(out_new))
            out_size = os.path.getsize(out_new)
            orig_size = os.path.getsize(idml)
            l2_errors = []
            if new_metrics['csr'] > orig_metrics['csr'] * 1.5:
                l2_errors.append(
                    f"csr {new_metrics['csr']} > 原始×1.5"
                    f"（{orig_metrics['csr']:.0f}）")
            if out_size > orig_size * 2.0:
                l2_errors.append(
                    f"体积未回落: 输出 {out_size/1024:.0f}KB vs "
                    f"原始 {orig_size/1024:.0f}KB")
            # v1.5.3: 保留排版符号（括号+几何装饰）零丢失
            brk_new = new_metrics['bracket']
            brk_orig = orig_metrics['bracket']
            if brk_new != brk_orig:
                l2_errors.append(
                    f"保留符号数量不一致: 原始{brk_orig} vs 输出{brk_new}"
                    f"（成对符号+几何装饰零丢失要求）")
            ds = None
            if name == '35':
                ds = check_dunju_structure(out_new)
                if not ds['ok']:
                    l2_errors.append(f"「時、離垢施」逐字拆分: {ds['detail']}")
            print(f"  [L2 结构] csr 原始{orig_metrics['csr']} → "
                  f"输出{new_metrics['csr']} | "
                  f"体积 原始{orig_size/1024:.0f}KB → 输出{out_size/1024:.0f}KB | "
                  f"保留符号 {brk_orig}→{brk_new}")
            if ds:
                print(f"    {ds['detail']}")
            if l2_errors:
                for e in l2_errors:
                    print(f"    [L2失败] {e}")
            else:
                print("  [L2 结构] 通过")

            # ---- L3: 句号 CSR 复用抽查 ----
            rp = count_reused_punct(out_new)
            orig_oldpunct = orig_metrics['oldpunct']
            if name == '35':
                # 混合标点：非句号标点（，、等）复用生效 + 总标点覆盖 ≥90%
                l3_ok = (rp['non_dot'] > 0
                         and rp['non_dot'] + rp['dot'] >= orig_oldpunct * 0.9)
            else:
                # 纯句号（20 号）：句号复用覆盖 ≥90%
                l3_ok = (rp['dot'] >= orig_oldpunct * 0.9)
            print(f"  [L3 复用] 句号样式 CSR: 非句号标点 {rp['non_dot']} 个"
                  f"（，、等复用）, 句号 {rp['dot']} 个, "
                  f"原始句号 CSR {orig_oldpunct} 个")
            for t, sig in rp['samples']:
                print(f"    抽查: Content「{t}」 样式 {sig}")
            if not l3_ok:
                print(f"    [L3失败] 复用数量异常")
                all_ok = False
            else:
                print("  [L3 复用] 通过")

            ok = l1_ok and not l2_errors and l3_ok
            all_ok = all_ok and ok
            print(f"  → {'通过 ✓' if ok else '失败 ✗'}\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("=" * 60)
    print(f"v1.5.2/1.5.3 回归结果: {'全部通过 ✓' if all_ok else '存在差异 ✗'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
