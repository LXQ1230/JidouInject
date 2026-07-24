#!/usr/bin/env python3
"""
批量 IDML 句读回注工具

扫描 pending/ 目录，按经号（文件名开头数字）自动配对 IDML 和句读结果文件（.md / .txt），
逐个处理，结果输出到 output/，完成后归档到 done/ + injected/。

用法:
    python code/batch_inject.py
"""

import sys
import os
import re
import shutil
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from inject import resolve_conflicts, _resolve_output_path

PENDING_DIR = os.path.join(PROJECT_ROOT, "pending")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
INJECTED_DIR = os.path.join(PROJECT_ROOT, "injected")
DONE_DIR = os.path.join(PROJECT_ROOT, "done")


def _extract_number(filename: str) -> str | None:
    """从文件名中提取开头的经号（数字）。

    Returns:
        经号字符串，如 '175'；无数字开头则返回 None
    """
    m = re.match(r'^(\d+)', filename)
    return m.group(1) if m else None


def find_pairs():
    """扫描 pending/ 目录，按经号配对 IDML 和句读结果文件。

    规则：
    - IDML：*.idml 即可
    - MD：  *句读结果.md 即可
    - TXT： *句读结果.txt 即可
    - 配对：提取文件名开头的数字（经号），相同经号即配为一对
    """
    if not os.path.isdir(PENDING_DIR):
        print(f"错误: pending/ 目录不存在: {PENDING_DIR}")
        sys.exit(1)

    all_files = os.listdir(PENDING_DIR)

    # 按经号分组 IDML
    idml_by_number: dict[str, list[str]] = {}
    for f in all_files:
        if f.endswith(".idml"):
            num = _extract_number(f)
            if num is None:
                print(f"警告: {f} 文件名无经号，跳过")
                continue
            idml_by_number.setdefault(num, []).append(f)

    # 按经号分组 MD/TXT
    md_by_number: dict[str, list[str]] = {}
    for f in all_files:
        if f.endswith("句读结果.md") or f.endswith("句读结果.txt"):
            num = _extract_number(f)
            if num is None:
                print(f"警告: {f} 文件名无经号，跳过")
                continue
            md_by_number.setdefault(num, []).append(f)

    # 配对
    pairs = []
    for num in sorted(idml_by_number):
        idml_list = idml_by_number[num]
        md_list = md_by_number.get(num, [])

        if len(idml_list) > 1:
            print(f"警告: 经号 {num} 有多个 IDML 文件 ({idml_list})，使用第一个: {idml_list[0]}")
        if len(md_list) > 1:
            print(f"警告: 经号 {num} 有多个句读结果 ({md_list})，使用第一个: {md_list[0]}")

        if not md_list:
            print(f"警告: 经号 {num} ({idml_list[0]}) 找不到对应句读结果，跳过")
            continue

        pairs.append((
            os.path.join(PENDING_DIR, idml_list[0]),
            os.path.join(PENDING_DIR, md_list[0]),
            num,
        ))

    return pairs


def collect_conflicts(pairs):
    """收集所有潜在的冲突"""
    conflicts = {}
    for _, _, name in pairs:
        out_file = f"{name}导出_WD注入.idml"
        # 输出文件
        out_path = os.path.join(OUTPUT_DIR, out_file)
        if os.path.exists(out_path):
            conflicts[out_path] = f"output/ 输出文件"
        # injected 汇总
        inj_path = os.path.join(INJECTED_DIR, out_file)
        if os.path.exists(inj_path):
            conflicts[inj_path] = f"injected/ 汇总"
        # done 归档
        done_path = os.path.join(DONE_DIR, name, out_file)
        if os.path.exists(done_path):
            conflicts[done_path] = f"done/{name}/ 归档"
        # pending 源文件不会冲突（本来就是从这里读的）
    return conflicts


def process_one(idml_path, result_path, name, output_path):
    """处理单个文件对"""
    from inject import process

    old_cwd = os.getcwd()
    os.chdir(PROJECT_ROOT)
    try:
        start = time.time()
        process(idml_path, result_path, output_path)
        elapsed = time.time() - start
        return True, elapsed
    except Exception as e:
        print(f"  处理失败: {e}")
        return False, 0
    finally:
        os.chdir(old_cwd)


def archive(name, decisions):
    """归档到 done/ + injected/"""
    out_file = f"{name}导出_WD注入.idml"
    out_src = os.path.join(OUTPUT_DIR, out_file)
    done_dir = os.path.join(DONE_DIR, name)

    if not os.path.isfile(out_src):
        print(f"  警告: 输出文件不存在 {out_src}")
        return

    os.makedirs(done_dir, exist_ok=True)

    # output → injected
    inj_dst = os.path.join(INJECTED_DIR, out_file)
    _smart_copy(out_src, inj_dst, decisions.get(inj_dst, 'overwrite'))

    # output → done
    done_dst = os.path.join(done_dir, out_file)
    _smart_move(out_src, done_dst, decisions.get(done_dst, 'overwrite'))

    # pending 源文件 → done
    for f in os.listdir(PENDING_DIR):
        if _extract_number(f) == name:
            src = os.path.join(PENDING_DIR, f)
            dst = os.path.join(done_dir, f)
            _smart_move(src, dst, decisions.get(dst, 'overwrite'))

    print(f"  已归档 → done/{name}/ + injected/")


def _smart_copy(src, dst, action):
    """智能复制，处理冲突"""
    if os.path.exists(dst):
        dst = _resolve_output_path(dst, action)
        if dst is None:
            return
    shutil.copy2(src, dst)


def _smart_move(src, dst, action):
    """智能移动，处理冲突"""
    if os.path.exists(dst):
        dst = _resolve_output_path(dst, action)
        if dst is None:
            return
    shutil.move(src, dst)


def main():
    pairs = find_pairs()

    if not pairs:
        print("pending/ 中没有找到可处理的文件对。")
        print("请将 *.idml 和 *句读结果.md/.txt 放入 pending/ 目录（文件名以经号开头）。")
        return

    print(f"找到 {len(pairs)} 个待处理文件对:\n")
    for idml, md, name in pairs:
        print(f"  {name}: {os.path.basename(idml)} + {os.path.basename(md)}")

    # ── 冲突检测 ──
    conflicts = collect_conflicts(pairs)
    decisions = resolve_conflicts(conflicts)

    # ── 检查是否全部跳过 ──
    out_file_skips = set()
    for _, _, name in pairs:
        out_path = os.path.join(OUTPUT_DIR, f"{name}导出_WD注入.idml")
        if out_path in decisions and decisions[out_path] == 'skip':
            out_file_skips.add(name)

    # ── 处理 ──
    print(f"\n开始批量处理 ({len(pairs)} 对)...")
    print("=" * 60)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []

    for idml, md, name in pairs:
        print(f"\n[{name}]")

        out_file = f"{name}导出_WD注入.idml"
        out_path = os.path.join(OUTPUT_DIR, out_file)

        # 冲突：跳过
        if out_path in decisions and decisions[out_path] == 'skip':
            print(f"  已跳过（output/ 同名文件）")
            results.append((name, "-", "跳过"))
            continue

        # 冲突：重命名
        if out_path in decisions and decisions[out_path] == 'rename_v2':
            resolved = _resolve_output_path(out_path, 'rename_v2')
            if resolved:
                out_path = resolved

        ok, elapsed = process_one(idml, md, name, out_path)
        if ok:
            archive(name, decisions)
            results.append((name, "✓", f"{elapsed:.1f}s"))
        else:
            results.append((name, "✗", "-"))

    # ── 汇总 ──
    print("\n" + "=" * 60)
    print("处理完成\n")
    print(f"{'文件':<15} {'状态':<5} {'耗时':<10}")
    print("-" * 30)
    for name, status, elapsed in results:
        print(f"{name:<15} {status:<5} {elapsed:<10}")

    success = sum(1 for _, s, _ in results if s == "✓")
    print(f"\n成功 {success}/{len(results)}")


if __name__ == "__main__":
    main()
