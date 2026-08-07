# -*- coding: utf-8 -*-
"""分支模拟 v2：对每个带 Br 的 CSR，按 _rebuild_paragraph_xml 的规则判定
重建分支与 Br 去向。分别模拟 PSR[0] 与 PSR[1]（均 31 Br）。"""
import sys, os, re, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

import inject

IDML = r"D:/Desktop/JidouInject/pending/26-A.idml"
RESULT = r"D:/Desktop/JidouInject/pending/26-A_WD句读结果.txt"
OUT = r"D:/Desktop/JidouInject/output/26诊断4.idml"

CSR_RE = re.compile(
    r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
    re.DOTALL)


def count_br(x):
    return x.count('<Br />') + x.count('<Br/>')


def simulate(orig, recs, split, label):
    all_records = [r for r in recs if not r.get('is_special', False)]
    csr_list = []
    for m in CSR_RE.finditer(orig):
        inner = m.group(2) or ''
        contents = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        csr_list.append({
            'is_punct': ('CharacterStyle/句号' in m.group(1)
                         or ''.join(contents) == '。'),
            'contents': contents,
            'match': m,
        })
    csr_segments = {}
    for rec in all_records:
        ci = rec.get('after_csr', -1) if rec.get('is_punct', False) \
            else rec['csr_idx']
        if ci < 0:
            continue
        csr_segments.setdefault(ci, []).append(rec)
    text_content_csrs = {
        ci for ci, segs in csr_segments.items()
        if any(not r.get('is_punct', False) for r in segs)
        and not csr_list[ci]['is_punct']
    }
    min_text_idx = min(text_content_csrs) if text_content_csrs else 0
    max_text_idx = max(text_content_csrs) if text_content_csrs else len(csr_list) - 1
    first_trailing_decoration = None
    for ci in range(max_text_idx + 1, len(csr_list)):
        cdata = csr_list[ci]
        if cdata['is_punct']:
            continue
        if any(c.strip() for c in cdata.get('contents', [])):
            break
        if '<Br' in cdata['match'].group(0):
            first_trailing_decoration = ci
            break

    print(f"\n===== {label}: {len(csr_list)} CSR, 有记录 {len(csr_segments)}, "
          f"min={min_text_idx} max={max_text_idx} "
          f"first_trailing={first_trailing_decoration} =====")
    br_lost = 0
    for ci, cdata in enumerate(csr_list):
        x = cdata['match'].group(0)
        if '<Br' not in x:
            continue
        nbr = count_br(x)
        segs = csr_segments.get(ci, [])
        contents = cdata['contents']
        orig_all_ws = all(not c.strip() for c in contents)
        has_punct_seg = any(r.get('is_punct', False) for r in segs)
        n_text_seg = sum(1 for r in segs if not r.get('is_punct', False))
        prev = (contents[0][:14] if contents else '(无)')

        if not segs:
            if cdata['is_punct']:
                branch = 'A1 删除(带Br的旧句号CSR)!'
                keep = False
            elif ci == first_trailing_decoration:
                branch = 'A2 保留Br'
                keep = True
            elif ci < min_text_idx or ci > max_text_idx:
                branch = 'A4 剥Br'
                keep = False
            elif nbr > 0 and orig_all_ws:
                branch = 'A3.5 保留Br'
                keep = True
            else:
                branch = 'A4 剥Br'
                keep = False
            if not keep:
                br_lost += nbr
            print(f"  CSR[{ci}] Br={nbr} [无记录] {prev!r} → {branch}")
        elif cdata['is_punct']:
            if has_punct_seg and not n_text_seg:
                keep = True
                branch = f'旧句号: 模板+追加Br (标点{sum(1 for r in segs if r.get("is_punct"))}个)'
            elif not has_punct_seg:
                keep = True
                branch = '旧句号: 清空保留Br'
            else:
                keep = True
                branch = '旧句号+文字 fallthrough'
            print(f"  CSR[{ci}] Br={nbr} [punct+记录] → {branch}")
        else:
            is_multi = len(contents) > 1
            if is_multi:
                keep = True
                branch = '文字 多Content 保留Br'
            elif has_punct_seg:
                cs = x.find('<Content>')
                ce = x.rfind('</Content>') + len('</Content>')
                pre_br = count_br(x[:cs])
                suf_br = count_br(x[ce:])
                keep = pre_br
                br_lost += suf_br
                branch = f'文字 拆分(前缀Br {pre_br} 保留, 后缀Br {suf_br} 丢)'
            else:
                keep = True
                branch = '文字 单Content 合并保留'
            print(f"  CSR[{ci}] Br={nbr} [文字] {prev!r} → {branch}")
    print(f"  >>> {label} 丢失 Br 合计: {br_lost}")


def main():
    with zipfile.ZipFile(IDML, 'r') as zf:
        in_xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')

    captured = []
    orig_fn = inject._rebuild_paragraph_xml
    def wrapped(original_psr_xml, new_char_records, global_punct_template=None,
                is_split_copy=False):
        captured.append((original_psr_xml, list(new_char_records), is_split_copy))
        return orig_fn(original_psr_xml, new_char_records,
                       global_punct_template, is_split_copy)
    inject._rebuild_paragraph_xml = wrapped
    try:
        try:
            inject.process(IDML, RESULT, OUT)
        except Exception:
            pass
    finally:
        inject._rebuild_paragraph_xml = orig_fn

    br31 = [(o, r, s) for o, r, s in captured if count_br(o) == 31 and not s]
    print(f"Br=31 原段 record 数: {len(br31)}")
    for ti, (o, r, s) in enumerate(br31):
        simulate(o, r, s, f"原段#{ti}")

    # 分割副本
    split_recs = [(o, r, s) for o, r, s in captured if s]
    print(f"\n分割副本 record 数: {len(split_recs)}")
    for ti, (o, r, s) in enumerate(split_recs):
        simulate(o, r, s, f"分割副本#{ti}")

    for p in (OUT,):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


if __name__ == '__main__':
    main()
