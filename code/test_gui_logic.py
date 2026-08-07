#!/usr/bin/env python3
"""launcher/gui_inject 纯逻辑测试（不依赖真实 Tk 窗口）。"""
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import gui_inject as g


def test_check_idml_valid():
    # 不存在的文件
    assert g.check_idml_valid(r"C:\no\such\file.idml") is not None
    # 非 ZIP
    with tempfile.NamedTemporaryFile(suffix=".idml", delete=False) as f:
        f.write(b"not a zip")
        bad = f.name
    assert g.check_idml_valid(bad) is not None
    os.remove(bad)
    print("  check_idml_valid OK")


def test_find_pairs():
    tmp = tempfile.mkdtemp(prefix="jd_pairs_")
    for name in [
        "497导出.idml", "497句读结果.md",
        "497导出_WD注入.idml",            # 排除：注入输出
        "123导出_old_test.idml",          # 排除：测试文件
        "888导出.idml",                   # 无结果 → 跳过
    ]:
        with open(os.path.join(tmp, name), "w") as f:
            f.write("")
    pairs = g.find_pairs_in_dir(tmp)
    assert len(pairs) == 1, pairs
    idml, md, num = pairs[0]
    assert num == "497"
    assert os.path.basename(idml) == "497导出.idml"
    assert os.path.basename(md) == "497句读结果.md"
    print("  find_pairs_in_dir OK:", pairs)

    # 目录不存在
    try:
        g.find_pairs_in_dir(r"C:\no\such\dir")
        assert False, "应抛 FileNotFoundError"
    except FileNotFoundError:
        pass
    print("  find_pairs_in_dir 异常路径 OK")


def test_queue_writer():
    import queue
    q = queue.Queue()
    w = g.QueueWriter(q)
    assert w.isatty() is False
    assert w.encoding == "utf-8"
    n = w.write("你好\n")
    assert n == 3
    assert q.get() == "你好\n"
    w.write("")
    assert q.empty()
    print("  QueueWriter OK")


def test_real_dir_pairing():
    # 真实数据：done/275 目录应配对出 275导出.idml + 句读结果
    done275 = os.path.join(os.path.dirname(SCRIPT_DIR), "done", "275")
    if os.path.isdir(done275):
        pairs = g.find_pairs_in_dir(done275)
        print("  done/275 配对结果:", pairs)
        assert pairs, "done/275 应能配对"
    else:
        print("  done/275 不存在，跳过")


if __name__ == "__main__":
    print("== gui_inject 纯逻辑测试 ==")
    test_check_idml_valid()
    test_find_pairs()
    test_queue_writer()
    test_real_dir_pairing()
    print("== 全部通过 ==")
