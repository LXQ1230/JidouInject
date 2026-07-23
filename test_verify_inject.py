#!/usr/bin/env python3
"""
inject.py 综合验证测试
确保注入过程不引入以下回归：
1. 原文文字零改动
2. Group Self ID 无重复（模板复制 bug）
3. 分割副本段落无 leading Br
4. 段落间关键空行正确
"""

import sys
import os
import zipfile
import re

# 确保可以 import inject 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from inject import (
    extract_from_idml, extract_from_result, validate_and_align,
    generate_idml, _is_old_punct, _is_unicode_whitespace, _is_ws_for_compare,
    _verify_output,
)


def test_275():
    """275 经本专项测试"""
    idml_path = "275导出.idml"
    result_path = "275从ID中导出文字_WD句读结果.md"
    output_path = "275导出_WD注入_test.idml"

    print("=" * 60)
    print("275 综合验证测试")
    print("=" * 60)

    # 运行注入
    stories = extract_from_idml(idml_path)
    result_data = extract_from_result(result_path)
    alignment = validate_and_align(stories, result_data)
    generate_idml(idml_path, stories, alignment['grouped'],
                  alignment['split_sources'], output_path)

    # ---- 检查 1: 原文文字零改动 ----
    print("\n[1] 原文文字零改动检查...")
    orig_chars = _extract_clean_chars(idml_path)
    out_chars = _extract_clean_chars(output_path)
    assert orig_chars == out_chars, (
        f"文字改动！原始 {len(orig_chars)} 字 vs 输出 {len(out_chars)} 字"
    )
    print(f"    ✓ {len(orig_chars)} 字逐字一致")

    # ---- 检查 2: Group Self ID 无重复 ----
    print("\n[2] Group Self ID 重复检查...")
    group_ids = _collect_group_ids(output_path)
    duplicates = {gid: count for gid, count in group_ids.items() if count > 1}
    assert not duplicates, f"发现重复 Group ID: {duplicates}"
    print(f"    ✓ {len(group_ids)} 个 Group ID 全部唯一")

    # ---- 检查 3: 分割副本段落无 leading Br ----
    print("\n[3] 分割段落 leading Br 检查...")
    split_leading_br = _check_split_leading_br(output_path, alignment['split_sources'])
    assert not split_leading_br, (
        f"分割段落存在 leading Br: {split_leading_br}"
    )
    print(f"    ✓ 分割段落无 leading Br")

    # ---- 检查 4: 关键段落间空行 ----
    print("\n[4] 关键段落间空行检查...")
    para_bounds = _check_key_boundaries(output_path)
    for check_name, result in para_bounds.items():
        status = "✓" if result["ok"] else "✗"
        print(f"    {status} {check_name}: {result['detail']}")
    all_ok = all(r["ok"] for r in para_bounds.values())
    assert all_ok, "段落间空行不符合预期"

    # ---- 检查 5: 输出自检 ----
    print("\n[5] 输出字符序列与输入一致...")
    from inject import _verify_output
    try:
        _verify_output(output_path, result_data['chars'])
        print("    ✓ 通过")
    except ValueError as e:
        print(f"    ✗ {e}")
        raise

    # 清理
    os.remove(output_path)
    print(f"\n{'=' * 60}")
    print("全部检查通过 ✓")
    print(f"{'=' * 60}")


def _extract_clean_chars(path: str) -> list[str]:
    """提取 IDML 中所有非标点、非比对空白的文字。

    使用 _is_ws_for_compare（含 U+3000）与 validate_and_align 的比对逻辑一致。
    """
    with zipfile.ZipFile(path, 'r') as zf:
        xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')
    all_contents = re.findall(r'<Content>(.*?)</Content>', xml, re.DOTALL)
    full = re.sub(r'<\?.*?\?>', '', ''.join(all_contents))
    return [ch for ch in full
            if not _is_ws_for_compare(ch)
            and not _is_old_punct(ch)]


def _collect_group_ids(path: str) -> dict[str, int]:
    """统计所有 Group Self ID 出现次数"""
    with zipfile.ZipFile(path, 'r') as zf:
        xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')
    ids = re.findall(r'Self="([^"]+)"', xml)
    counts = {}
    for gid in ids:
        counts[gid] = counts.get(gid, 0) + 1
    return counts


def _check_split_leading_br(output_path: str, split_sources: dict) -> list[str]:
    """检查分割副本段落是否有 leading Br"""
    issues = []
    with zipfile.ZipFile(output_path, 'r') as zf:
        xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')

    psrs = list(re.finditer(
        r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>', xml, re.DOTALL
    ))

    for (si, new_pi), orig_pi in split_sources.items():
        # 在 generate_idml 中，分割段落 position = orig_pi + 0.5
        # 需要找到输出 XML 中对应的段落
        for i, psr in enumerate(psrs):
            csrs = list(re.finditer(
                r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
                psr.group(0), re.DOTALL
            ))
            # 找第一个有非空 Content 的 CSR
            first_content_idx = None
            for j, m in enumerate(csrs):
                inner = m.group(2) or ''
                c = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
                if any(t.strip() for t in c):
                    first_content_idx = j
                    break
            if first_content_idx is None:
                continue
            # 检查第一个 content CSR 之前是否有 Br
            for j in range(first_content_idx):
                if '<Br' in csrs[j].group(0):
                    issues.append(
                        f"Para[{i}] CSR[{j}] has leading Br "
                        f"(first content at CSR[{first_content_idx}])"
                    )
    return issues


def _check_key_boundaries(output_path: str) -> dict:
    """检查 275 关键段落边界"""
    with zipfile.ZipFile(output_path, 'r') as zf:
        xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')

    psrs = list(re.finditer(
        r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>', xml, re.DOTALL
    ))

    para_texts = []
    para_trailing_br = []
    para_leading_br = []

    for i, psr in enumerate(psrs):
        contents = re.findall(r'<Content>(.*?)</Content>', psr.group(0), re.DOTALL)
        text = re.sub(r'<\?.*?\?>', '', ''.join(contents))
        para_texts.append(text)

        csrs = list(re.finditer(
            r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
            psr.group(0), re.DOTALL
        ))
        # Count trailing Br (after last content CSR)
        last_content = None
        for j, m in enumerate(csrs):
            inner = m.group(2) or ''
            c = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
            if any(t.strip() for t in c):
                last_content = j
        trailing_br = 0
        if last_content is not None:
            for j in range(last_content + 1, len(csrs)):
                if '<Br' in csrs[j].group(0):
                    trailing_br += 1
        para_trailing_br.append(trailing_br)

        # Count leading Br (before first content CSR)
        first_content = None
        for j, m in enumerate(csrs):
            inner = m.group(2) or ''
            c = re.findall(r'<Content>(.*?)</Content>', inner, re.DOTALL)
            if any(t.strip() for t in c):
                first_content = j
                break
        leading_br = 0
        if first_content is not None:
            for j in range(first_content):
                if '<Br' in csrs[j].group(0):
                    leading_br += 1
        para_leading_br.append(leading_br)

    results = {}

    # Para[4] → Para[5]: 信受奉行。 → 金剛般若波羅蜜經。
    # 预期: 需要 1 个空行（来自 Para[4] trailing Br 或 Para[5] leading Br）
    ok_4_5 = (para_trailing_br[4] >= 1 or para_leading_br[5] >= 1)
    results["Para[4]→Para[5] 空行"] = {
        "ok": ok_4_5,
        "detail": (f"Para[4] trailing={para_trailing_br[4]}Br, "
                   f"Para[5] leading={para_leading_br[5]}Br")
    }

    # Para[6] → Para[7]: 莎婆訶。→ 御製金剛...
    # 预期: Para[6] 需要 2 trailing Br（= 1 空行）
    ok_6_7 = para_trailing_br[6] >= 2
    results["Para[6]→Para[7] 空行"] = {
        "ok": ok_6_7,
        "detail": f"Para[6] trailing={para_trailing_br[6]}Br (需要 ≥2)"
    }

    # Para[7] 无 leading Br
    ok_7_leading = para_leading_br[7] == 0
    results["Para[7] 无 leading Br"] = {
        "ok": ok_7_leading,
        "detail": f"Para[7] leading={para_leading_br[7]}Br (需要 =0)"
    }

    return results


def test_461():
    """461 经本专项测试"""
    idml_path = "461导出.idml"
    result_path = "461从ID中导出文字_WD句读结果.md"
    output_path = "461导出_WD注入_test.idml"

    print("\n" + "=" * 60)
    print("461 综合验证测试")
    print("=" * 60)

    stories = extract_from_idml(idml_path)
    result_data = extract_from_result(result_path)
    alignment = validate_and_align(stories, result_data)
    generate_idml(idml_path, stories, alignment['grouped'],
                  alignment['split_sources'], output_path)

    # 检查 1: 原文零改动
    print("\n[1] 原文文字零改动检查...")
    orig_chars = _extract_clean_chars(idml_path)
    out_chars = _extract_clean_chars(output_path)
    assert orig_chars == out_chars, (
        f"文字改动！原始 {len(orig_chars)} 字 vs 输出 {len(out_chars)} 字"
    )
    print(f"    ✓ {len(orig_chars)} 字逐字一致")

    # 检查 2: Group ID 无重复
    print("\n[2] Group Self ID 重复检查...")
    group_ids = _collect_group_ids(output_path)
    duplicates = {gid: count for gid, count in group_ids.items() if count > 1}
    assert not duplicates, f"发现重复 Group ID: {duplicates}"
    print(f"    ✓ {len(group_ids)} 个 Group ID 全部唯一")

    # 检查 3: 分割副本段落无 leading Br
    print("\n[3] 分割段落 leading Br 检查...")
    split_issues = _check_split_leading_br(output_path, alignment['split_sources'])
    assert not split_issues, f"分割段落存在 leading Br: {split_issues}"
    print(f"    ✓ {len(alignment['split_sources'])} 个分割段落无 leading Br")

    # 检查 4: 输出自检
    print("\n[4] 输出字符序列与输入一致...")
    try:
        _verify_output(output_path, result_data['chars'])
        print("    ✓ 通过")
    except ValueError as e:
        print(f"    ✗ {e}")
        raise

    os.remove(output_path)
    print(f"\n{'=' * 60}")
    print("全部检查通过 ✓")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    test_275()
    test_461()
    print("\n" + "=" * 60)
    print("所有测试全部通过 ✓")
    print("=" * 60)
