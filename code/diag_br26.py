# -*- coding: utf-8 -*-
"""诊断 26 号文件 Br 丢失:136→107。

monkeypatch _rebuild_paragraph_xml 记录每个 PSR 输入/输出 XML，
按 CSR 场景分类统计 Br 去留，定位丢失名目。
"""
import sys, re, os, io
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import inject

IDML = r"D:/Desktop/JidouInject/pending/26-A.idml"
RESULT = r"D:/Desktop/JidouInject/pending/26-A_WD句读结果.txt"
OUT = r"D:/Desktop/JidouInject/output/26诊断.idml"

CSR_RE = re.compile(
    r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
    re.DOTALL)

def count_br(xml):
    return xml.count('<Br />') + xml.count('<Br/>')

def classify_csrs(psr_xml):
    """返回 (csr_info_list, text_idx_list)。csr_info: {xml, br, has_text,
    is_punct, idx}"""
    out = []
    text_idx = []
    for m in CSR_RE.finditer(psr_xml):
        inner = m.group(2) or ''
        contents = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        has_text = any(c.strip() for c in contents)
        is_punct = ('CharacterStyle/句号' in m.group(1)
                    or ''.join(contents) == '。')
        out.append({
            'xml': m.group(0),
            'br': count_br(m.group(0)),
            'has_text': has_text,
            'is_punct': is_punct,
        })
        if has_text:
            text_idx.append(len(out) - 1)
    return out, text_idx

def main():
    records = []
    orig_fn = inject._rebuild_paragraph_xml
    def wrapped(original_psr_xml, new_char_records, global_punct_template=None,
                is_split_copy=False):
        new_xml = orig_fn(original_psr_xml, new_char_records,
                          global_punct_template, is_split_copy)
        records.append({
            'orig': original_psr_xml,
            'new': new_xml,
            'split': is_split_copy,
            'n_new_punct': sum(1 for r in new_char_records
                               if r.get('is_punct', False)),
        })
        return new_xml
    inject._rebuild_paragraph_xml = wrapped

    try:
        # 捕获验证失败异常，但保留 records
        try:
            inject.process(IDML, RESULT, OUT)
            print("process 完成（未触发验证失败？）")
        except Exception as e:
            print(f"process 异常: {type(e).__name__}: {str(e)[:200]}")
    finally:
        inject._rebuild_paragraph_xml = orig_fn

    # ---- 汇总统计 ----
    tot_in = sum(count_br(r['orig']) for r in records)
    tot_out = sum(count_br(r['new']) for r in records)
    print(f"\n===== 重建记录汇总: {len(records)} 个 PSR =====")
    print(f"重建输入 Br 合计: {tot_in}  重建输出 Br 合计: {tot_out}")

    # 按场景分类丢失的 Br
    cats = {
        'A1 punct尾随分隔': 0,
        'A2 尾饰装饰(空+Br)': 0,
        'A3 分割副本空壳': 0,
        'A3.5 中间空+Br保留': 0,
        'A4 leading/trailing剥离': 0,
        '文字CSR拆分剥离': 0,
        '旧句号CSR': 0,
        '文字CSR(未拆分)': 0,
        '多Content分割副本': 0,
        '其他/未知': 0,
    }
    detail = []
    for ri, r in enumerate(records):
        in_br = count_br(r['orig'])
        out_br = count_br(r['new'])
        if out_br >= in_br:
            continue
        lost = in_br - out_br
        csrs, text_idx = classify_csrs(r['orig'])
        first_text = text_idx[0] if text_idx else None
        last_text = text_idx[-1] if text_idx else None
        for ci, c in enumerate(csrs):
            if not c['br']:
                continue
            # 判断该 CSR 的 Br 在重建后是否保留 —— 粗判：看 new 中是否还有
            # 对应数量的 Br 由该分类贡献。这里按规则推断去向：
            if c['is_punct']:
                cat = '旧句号CSR'
            elif c['has_text']:
                # 有文字的 CSR：若段内有标点注入（可能拆分）或分割副本
                has_punct_in_psr = r['n_new_punct'] > 0
                if r['split']:
                    cat = '文字CSR(分割副本)'
                elif has_punct_in_psr and len(csrs) > 1:
                    cat = '文字CSR拆分剥离'
                else:
                    cat = '文字CSR(未拆分)'
            elif first_text is not None and ci > last_text:
                cat = ('A2 尾饰装饰(空+Br)' if ci == last_text + 1
                       else 'A4 trailing剥离')
            elif first_text is not None and ci < first_text:
                cat = 'A4 leading剥离'
            elif first_text is not None:
                cat = 'A3.5 中间空+Br保留'
            else:
                cat = 'A1 punct尾随分隔' if c['is_punct'] else '其他/未知'
            cats.setdefault(cat, 0)
            cats[cat] += c['br']
        detail.append((ri, r['split'], r['n_new_punct'], in_br, out_br))

    print("\n===== 丢失 Br 按场景归类（按输入 CSR 分类估算） =====")
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        if v:
            print(f"  {k}: {v}")

    # 详细列出丢失的 PSR
    print("\n===== 有 Br 丢失的 PSR 明细 =====")
    for ri, split, npunct, in_br, out_br in detail:
        if in_br > out_br:
            print(f"  PSR[{ri}] split={split} 新标点={npunct} "
                  f"Br: {in_br} -> {out_br} (丢 {in_br-out_br})")

    # 输出文件是否残留在 output/
    if os.path.exists(OUT):
        sz = os.path.getsize(OUT)
        os.remove(OUT)
        print(f"\n（已清理诊断输出文件 {sz} 字节）")

if __name__ == '__main__':
    main()
