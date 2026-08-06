# -*- coding: utf-8 -*-
"""诊断抑制逻辑：复现 validate_and_align 的对齐循环，打印每个 。 的抑制判定细节。

用法: python code/_diag_suppress.py <idml> <result> [--window "关键词"]
"""
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from inject import (
    extract_from_idml, extract_from_result, _should_suppress_punct,
    _get_prev_non_ws_font, _get_next_non_ws_font,
    _is_ws_for_compare, _is_unicode_whitespace,
)

MIN_CLEAN = 50


def build_flat(stories):
    """与 validate_and_align 相同：构建 all_idml_records 与 idml_clean_indices"""
    all_idml_records = []
    for story in stories:
        story_clean_count = sum(
            1 for para in story['paragraphs']
            for rec in para['chars']
            if not rec['is_punct'] and not rec.get('is_special', False)
            and not _is_unicode_whitespace(rec['char'])
        )
        if story_clean_count < MIN_CLEAN:
            continue
        for para in story['paragraphs']:
            for rec in para['chars']:
                all_idml_records.append(rec)

    idml_clean_indices = []
    for i, rec in enumerate(all_idml_records):
        ch = rec['char']
        if rec['is_punct'] or rec.get('is_special', False):
            continue
        if _is_unicode_whitespace(ch):
            continue
        idml_clean_indices.append(i)
    return all_idml_records, idml_clean_indices


def dump_records(all_records, idml_clean_indices, start, end, title):
    print(f"\n── {title} ──")
    for j in range(max(0, start), min(len(idml_clean_indices), end)):
        ti = idml_clean_indices[j]
        r = all_records[ti]
        ch = r['char']
        if ch == '　':
            disp = 'U+3000(全角空格)'
        elif _is_unicode_whitespace(ch):
            disp = f'U+{ord(ch):04X}(空白)'
        else:
            disp = ch
        print(f"  clean#{j} rec#{ti} ch={disp!r:12} font={r.get('font')!r:22} "
              f"story={r['story_idx']} para={r['para_idx']} csr={r['csr_idx']} "
              f"slot={r['content_slot']} punct={r['is_punct']}")


def main():
    idml_path = sys.argv[1]
    result_path = sys.argv[2]
    keyword = None
    if '--window' in sys.argv:
        keyword = sys.argv[sys.argv.index('--window') + 1]

    print(f"IDML: {idml_path}")
    print(f"结果: {result_path}")

    stories = extract_from_idml(idml_path)
    all_records, clean_idx = build_flat(stories)
    print(f"总记录 {len(all_records)}，净字索引 {len(clean_idx)} 个")

    result_data = extract_from_result(result_path)
    result_chars = result_data['chars']
    print(f"句读结果字符数: {len(result_chars)}")

    # ── 复现对齐循环，记录每个 。 的判定 ──
    idml_idx = 0
    last_slot = None
    decisions = []  # (result_pos, idml_idx_at_slot, last_slot, decision, detail)

    para_breaks = result_data['para_breaks']

    # 段落分割状态（简化：不影响 。 抑制判定，但影响 last_slot 的 para 一致性）
    current_effective = {}
    orig_para_max = {}
    for rec in all_records:
        si, pi = rec['story_idx'], rec['para_idx']
        orig_para_max.setdefault(si, 0)
        orig_para_max[si] = max(orig_para_max[si], pi)
    next_new_idx = {si: m + 1 for si, m in orig_para_max.items()}
    for si, m in orig_para_max.items():
        for pi in range(m + 1):
            current_effective[(si, pi)] = pi
    new_split_sources = {}

    for i, ch in enumerate(result_chars):
        if i in para_breaks and i > 0 and last_slot:
            si, pi = last_slot[0], last_slot[1]
            new_idx = next_new_idx.get(si, pi + 1)
            current_effective[(si, pi)] = new_idx
            new_split_sources[(si, new_idx)] = pi
            next_new_idx[si] = new_idx + 1

        if ch == '。':
            suppress = _should_suppress_punct(idml_idx, clean_idx, all_records, last_slot)
            decisions.append((i, idml_idx, last_slot, suppress))
        elif _is_ws_for_compare(ch):
            pass
        else:
            while idml_idx < len(clean_idx):
                target_idx = clean_idx[idml_idx]
                orig_rec = all_records[target_idx]
                idml_idx += 1
                last_slot = (orig_rec['story_idx'], orig_rec['para_idx'],
                             orig_rec['csr_idx'], orig_rec['content_slot'],
                             orig_rec.get('slot_pos', 0))
                if not _is_ws_for_compare(orig_rec['char']):
                    break

    print(f"共 {len(decisions)} 个句号")

    # ── 打印目标窗口内的句号判定 ──
    win = 60  # 字符窗口
    printed = 0
    for i, iidx, slot, suppress in decisions:
        ctx = ''.join(result_chars[max(0, i - 12):i + 13])
        if keyword is not None and keyword not in ctx:
            continue
        printed += 1
        print(f"\n{'='*70}")
        print(f"句号#{i}  判定={'抑制(不插入。)' if suppress else '保留(插入。)'}")
        print(f"  上下文: {ctx!r}")
        print(f"  当时 idml_idx={iidx}  last_slot={slot}")

        # 详细拆解判定（与 _should_suppress_punct 一致：以槽位段落为 anchor）
        anchor = (slot[0], slot[1]) if slot else None
        font_prev = _get_prev_non_ws_font(iidx, clean_idx, all_records, anchor)
        font_next = _get_next_non_ws_font(iidx, clean_idx, all_records, anchor)
        print(f"  font_prev={font_prev!r} font_next={font_next!r}")
        from inject import _is_suppress_always_target, _is_suppress_width_target
        print(f"  prev是仿宋/楷体(无条件抑制)={_is_suppress_always_target(font_prev)}")
        print(f"  next是仿宋/楷体={_is_suppress_always_target(font_next)}")

        # 规则B拆解
        if iidx < len(clean_idx):
            next_idx = None
            next_rec = None
            for j in range(iidx, len(clean_idx)):
                ti = clean_idx[j]
                rec = all_records[ti]
                if not _is_ws_for_compare(rec['char']):
                    next_idx = j
                    next_rec = rec
                    break
            if next_rec is not None:
                print(f"  规则B: next_rec ch={next_rec['char']!r} font={next_rec.get('font')!r} "
                      f"story={next_rec['story_idx']} para={next_rec['para_idx']} "
                      f"csr={next_rec['csr_idx']}")
                if slot:
                    print(f"  规则B: 与last_slot同CSR? "
                          f"{next_rec['csr_idx'] == slot[2]}; 同story/para? "
                          f"{(next_rec['story_idx'], next_rec['para_idx']) == (slot[0], slot[1])}")
                    print(f"  规则B: next是思源宋体? {_is_suppress_width_target(next_rec.get('font'))}")
                    between = []
                    for j in range(iidx, next_idx):
                        ti = clean_idx[j]
                        between.append(all_records[ti]['char'])
                    print(f"  规则B: 两字间字符(含索引{iidx}~{next_idx-1}): {between!r}")
                    print(f"  规则B: 含U+3000? {'　' in between}")

        # 打印周边 IDML 记录
        lo = max(0, iidx - 8)
        hi = min(len(clean_idx), iidx + 10)
        dump_records(all_records, clean_idx, lo, hi, f"IDML记录 clean#{lo}~{hi-1}")

        if printed >= 6:
            print("\n... 已打印 6 个窗口，停止")
            break

    if printed == 0:
        print(f"\n未找到含关键词 {keyword!r} 的句号")


if __name__ == '__main__':
    main()
