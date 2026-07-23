#!/usr/bin/env python3
"""
批量 IDML 句读回注工具

扫描 pending/ 目录，自动配对 IDML 和句读结果文件，
逐个处理，结果输出到 output/，完成后归档到 done/ + injected/。

用法:
    python code/batch_inject.py
"""

import sys
import os
import re
import shutil
import time

# 确保 code/ 在路径中，以便 import inject
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

PENDING_DIR = os.path.join(PROJECT_ROOT, "pending")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
INJECTED_DIR = os.path.join(PROJECT_ROOT, "injected")
DONE_DIR = os.path.join(PROJECT_ROOT, "done")


def find_pairs():
    """扫描 pending/ 目录，返回 (idml_path, result_path, name) 配对列表"""
    if not os.path.isdir(PENDING_DIR):
        print(f"错误: pending/ 目录不存在: {PENDING_DIR}")
        sys.exit(1)

    idml_files = [f for f in os.listdir(PENDING_DIR) if f.endswith("导出.idml")]
    pairs = []

    for idml_file in sorted(idml_files):
        # 提取前缀: "275导出.idml" → "275"
        prefix = idml_file.replace("导出.idml", "")
        # 查找对应的句读结果
        md_candidates = [
            f for f in os.listdir(PENDING_DIR)
            if f.startswith(prefix) and f.endswith("句读结果.md")
        ]
        if not md_candidates:
            print(f"警告: {idml_file} 找不到对应句读结果，跳过")
            continue
        if len(md_candidates) > 1:
            print(f"警告: {idml_file} 匹配到多个句读结果: {md_candidates}，使用第一个")

        md_file = md_candidates[0]
        pairs.append((
            os.path.join(PENDING_DIR, idml_file),
            os.path.join(PENDING_DIR, md_file),
            prefix,
        ))

    return pairs


def process_one(idml_path, result_path, name):
    """处理单个文件对，返回 (成功, 耗时秒)"""
    from inject import process

    output_path = os.path.join(OUTPUT_DIR, f"{name}导出_WD注入.idml")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 临时切换到项目根目录运行（inject.py 输出路径基于当前目录）
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


def archive(name):
    """将 pending/ 中的输入文件 + output/ 中的输出文件归档到 done/ + injected/"""
    done_dir = os.path.join(DONE_DIR, name)
    os.makedirs(done_dir, exist_ok=True)

    # 移动 pending 中的输入文件
    for f in os.listdir(PENDING_DIR):
        if f.startswith(name):
            src = os.path.join(PENDING_DIR, f)
            shutil.move(src, os.path.join(done_dir, f))

    # 复制 output → injected（永久保留）
    output_file = f"{name}导出_WD注入.idml"
    output_src = os.path.join(OUTPUT_DIR, output_file)
    injected_dst = os.path.join(INJECTED_DIR, output_file)
    if os.path.isfile(output_src):
        shutil.copy2(output_src, injected_dst)

    # 移动 output → done
    if os.path.isfile(output_src):
        shutil.move(output_src, os.path.join(done_dir, output_file))

    print(f"  已归档 → done/{name}/ + injected/{output_file}")


def main():
    pairs = find_pairs()

    if not pairs:
        print("pending/ 中没有找到可处理的文件对。")
        print("请将 *导出.idml 和 *句读结果.md 放入 pending/ 目录。")
        return

    print(f"找到 {len(pairs)} 个待处理文件对:\n")
    for idml, md, name in pairs:
        print(f"  {name}: {os.path.basename(idml)} + {os.path.basename(md)}")

    print(f"\n开始批量处理 ({len(pairs)} 对)...")
    print("=" * 60)

    results = []
    for idml, md, name in pairs:
        print(f"\n[{name}]")
        ok, elapsed = process_one(idml, md, name)
        if ok:
            archive(name)
            results.append((name, "✓", f"{elapsed:.1f}s"))
        else:
            results.append((name, "✗", "-"))

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
