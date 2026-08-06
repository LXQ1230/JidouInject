# -*- coding: utf-8 -*-
"""v1.5.0 497 实数据对照（一次性验证）。

497 新句读结果（497有图_WD句读结果.txt，纯句号）在 v1.4.3 下已产出
done/497/497导出_WD注入.idml（2026-08-06 13:20）。本脚本用 v1.5.0
新代码重跑同输入，与既有输出做 ZIP 全成员字节对比，验证标点开放
改动对大型真实经书（58 万+字符、Story_u562 单 Story 219MB 解压）
零副作用。
"""
import os
import sys
import types
import zipfile
import tempfile
import shutil

sys.stdout.reconfigure(encoding='utf-8')

INJECT = r"D:\Desktop\JidouInject\code\inject.py"
IDML = r"D:\Desktop\JidouInject\done\497\497有图.idml"
RESULT = r"D:\Desktop\JidouInject\done\497\497有图_WD句读结果.txt"
BASELINE = r"D:\Desktop\JidouInject\done\497\497导出_WD注入.idml"


def load_module(path: str, name: str):
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    mod = types.ModuleType(name)
    mod.__file__ = path
    sys.modules[name] = mod
    exec(compile(source, path, 'exec'), mod.__dict__)
    return mod


def zip_members_bytes(path: str) -> dict[str, bytes]:
    result = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            result[name] = zf.read(name)
    return result


def main():
    mod = load_module(INJECT, "inject_new")
    tmp = tempfile.mkdtemp(prefix="reg_p150_497_")
    try:
        out = os.path.join(tmp, "497导出_WD注入_v150.idml")
        print(f"处理中（497 大型经书，约 80s）...")
        mod.process(IDML, RESULT, out)
        base = zip_members_bytes(BASELINE)
        new = zip_members_bytes(out)
        diff_names = set(base) ^ set(new)
        diff_bytes = [n for n in set(base) & set(new) if base[n] != new[n]]
        if not diff_names and not diff_bytes:
            print(f"\n[通过] 497 输出 ZIP 全成员字节与 v1.4.3 基线完全一致"
                  f"（{len(new)} 个成员）")
        else:
            print(f"\n[失败] 成员差异 {len(diff_names)}: {sorted(diff_names)[:5]}")
            print(f"       字节差异 {len(diff_bytes)} 个成员")
            for n in sorted(diff_bytes)[:3]:
                print(f"       {n}: 基线 {len(base[n])}B vs 新 {len(new[n])}B")
            sys.exit(1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
