#!/usr/bin/env python3
"""drag_input 拖拽解析纯逻辑测试（不依赖 GUI/真实拖拽）。"""
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import drag_input as d


def _make_tree(base):
    """构造测试目录树。"""
    files = {
        "275导出.idml": "", "275句读结果.md": "",       # 275 对
        "497导出.idml": "", "497结果.txt": "",           # 497 对（txt）
        "461导出.idml": "",                              # 461 只有 IDML（散文件场景）
        "461句读结果.md": "",                            # 461 孤立结果（无对应 IDML）
        "888导出.idml": "", "888句读结果.md": "",        # 888 对
        "497导出_WD注入.idml": "",                       # 排除：注入输出
        "275_old_test.idml": "", "275_old_test.txt": "", # 排除：测试产物
        "777导出.idml": "",                              # 777 无任何结果
        "698导出.idml": "", "698句读.md": "",            # 698：不同名同经号（第 2 级查找）
        "垃圾.docx": "",                                 # 无效类型
    }
    for name, content in files.items():
        with open(os.path.join(base, name), "w", encoding="utf-8") as f:
            f.write(content)

    sub = os.path.join(base, "batch")
    os.makedirs(sub)
    for name in ("556导出.idml", "556句读结果.md", "556导出_WD注入.idml"):
        with open(os.path.join(sub, name), "w", encoding="utf-8") as f:
            f.write("")
    return sub


def test_two_files_reversed_order():
    """结果文件在前、IDML 在后 → 仍正确识别为 single（顺序自适应）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([
            os.path.join(tmp, "275句读结果.md"),
            os.path.join(tmp, "275导出.idml"),
        ])
        assert plan.mode == "single", plan
        assert os.path.basename(plan.idml) == "275导出.idml", plan.idml
        assert os.path.basename(plan.result) == "275句读结果.md", plan.result
    print("  two_files_reversed_order OK")


def test_single_idml_auto_find_same_name():
    """只拖 1 个 IDML，同目录有同名结果 → 自动找到（第 1 级）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([os.path.join(tmp, "275导出.idml")])
        assert plan.mode == "single", plan
        assert os.path.basename(plan.result) == "275句读结果.md", plan.result
    print("  single_idml_auto_find_same_name OK")


def test_single_idml_auto_find_by_number():
    """只拖 1 个 IDML，无同名但有同经号结果 → 自动找到（第 2 级）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([os.path.join(tmp, "698导出.idml")])
        assert plan.mode == "single", plan
        assert os.path.basename(plan.result) == "698句读.md", plan.result
    print("  single_idml_auto_find_by_number OK")


def test_single_idml_need_result():
    """只拖 1 个 IDML 且无任何结果 → single_need_result。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([os.path.join(tmp, "777导出.idml")])
        assert plan.mode == "single_need_result", plan
        assert os.path.basename(plan.idml) == "777导出.idml", plan.idml
        assert plan.result is None
    print("  single_idml_need_result OK")


def test_result_only_error():
    """只拖句读结果 → error，提示缺少 IDML。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([os.path.join(tmp, "461句读结果.md")])
        assert plan.mode == "error", plan
        assert any("缺少 IDML" in m for m in plan.messages), plan.messages
    print("  result_only_error OK")


def test_multi_pairs_loose():
    """多对散文件（IDML+结果混合）→ batch 配对正确。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([
            os.path.join(tmp, "275导出.idml"),
            os.path.join(tmp, "497结果.txt"),
            os.path.join(tmp, "275句读结果.md"),
            os.path.join(tmp, "497导出.idml"),
        ])
        assert plan.mode == "batch", plan
        nums = sorted(p[2] for p in plan.pairs)
        assert nums == ["275", "497"], plan.pairs
        assert plan.base_dir == tmp
    print("  multi_pairs_loose OK")


def test_folder_batch():
    """拖入整个文件夹 → batch（排除 _WD注入 与测试产物）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([tmp])
        assert plan.mode == "batch", plan
        nums = sorted(p[2] for p in plan.pairs)
        # 275/461/497/698/888 配对；777 无结果跳过；排除项不计
        assert nums == ["275", "461", "497", "698", "888"], plan.pairs
        assert plan.base_dir == tmp
    print("  folder_batch OK")


def test_folder_no_pairs_error():
    """拖入无配对文件的目录 → error。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty)
        plan = d.classify_paths([empty])
        assert plan.mode == "error", plan
    print("  folder_no_pairs_error OK")


def test_mixed_folder_and_files():
    """文件夹 + 散文件混合 → batch 合并。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        sub = _make_tree(tmp)
        plan = d.classify_paths([
            sub,
            os.path.join(tmp, "275导出.idml"),
            os.path.join(tmp, "275句读结果.md"),
        ])
        assert plan.mode == "batch", plan
        nums = sorted(p[2] for p in plan.pairs)
        assert "556" in nums and "275" in nums, plan.pairs
    print("  mixed_folder_and_files OK")


def test_invalid_type_ignored():
    """无效文件类型忽略 + 警告；不影响有效配对。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([
            os.path.join(tmp, "275导出.idml"),
            os.path.join(tmp, "275句读结果.md"),
            os.path.join(tmp, "垃圾.docx"),
        ])
        assert plan.mode == "single", plan
        assert any("垃圾.docx" in m for m in plan.messages), plan.messages
    print("  invalid_type_ignored OK")


def test_all_invalid_error():
    """全部无效类型 → error。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        plan = d.classify_paths([os.path.join(tmp, "a.docx")])
        assert plan.mode == "error", plan
    print("  all_invalid_error OK")


def test_nonexistent_path_error():
    """不存在路径 → error。"""
    plan = d.classify_paths([r"C:\no\such\file.idml"])
    assert plan.mode == "error", plan
    assert any("没有可用" in m for m in plan.messages), plan.messages
    print("  nonexistent_path_error OK")


def test_excluded_inputs():
    """拖入 _WD注入/测试产物 → 排除并警告。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        plan = d.classify_paths([
            os.path.join(tmp, "497导出_WD注入.idml"),
            os.path.join(tmp, "275_old_test.idml"),
            os.path.join(tmp, "275句读结果.md"),
        ])
        # 两个 IDML 均被排除 → 只剩结果 → error，且提示缺少 IDML
        assert plan.mode == "error", plan
        assert any("缺少 IDML" in m for m in plan.messages), plan.messages
        # 排除类文件出现在输入中时应有提示信息
        assert plan.messages, plan.messages
    print("  excluded_inputs OK")


def test_find_result_levels():
    """find_result_for_idml：同名（1 级）/ 同经号（2 级）/ 无（None）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        r1 = d.find_result_for_idml(os.path.join(tmp, "275导出.idml"))
        assert os.path.basename(r1) == "275句读结果.md", r1
        r2 = d.find_result_for_idml(os.path.join(tmp, "698导出.idml"))
        assert os.path.basename(r2) == "698句读.md", r2
        r3 = d.find_result_for_idml(os.path.join(tmp, "777导出.idml"))
        assert r3 is None
    print("  find_result_levels OK")


def test_directory_pairing_parity():
    """drag_input.find_pairs_in_dir 与 gui_inject 迁移前行为一致（回归锚点）。"""
    with tempfile.TemporaryDirectory(prefix="jd_dnd_") as tmp:
        _make_tree(tmp)
        pairs = d.find_pairs_in_dir(tmp)
        assert len(pairs) == 5, pairs  # 275/461/497/698/888
        assert all(len(p) == 3 for p in pairs)
    print("  directory_pairing_parity OK")


if __name__ == "__main__":
    print("== drag_input 拖拽解析测试 ==")
    test_two_files_reversed_order()
    test_single_idml_auto_find_same_name()
    test_single_idml_auto_find_by_number()
    test_single_idml_need_result()
    test_result_only_error()
    test_multi_pairs_loose()
    test_folder_batch()
    test_folder_no_pairs_error()
    test_mixed_folder_and_files()
    test_invalid_type_ignored()
    test_all_invalid_error()
    test_nonexistent_path_error()
    test_excluded_inputs()
    test_find_result_levels()
    test_directory_pairing_parity()
    print("\n全部通过 ✓")
