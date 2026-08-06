# -*- coding: utf-8 -*-
"""v1.5.0 标点开放回归测试。

新旧代码（v1.4.3 备份 vs v1.5.0 标点开放）对相同文件对各跑一次 process()，
对比输出 IDML 全成员字节。v1.5.0 仅开放白名单标点（，、；：？！。），
对纯句号结果的输出必须与 v1.4.3 字节完全一致（零副作用）。
"""
import os
import sys
import types
import zipfile
import tempfile
import shutil

sys.stdout.reconfigure(encoding='utf-8')

OLD = r"D:\Desktop\JidouInject\backup\inject.py.v1.4.3-punct-expand-2026.08.06.bak"
NEW = r"D:\Desktop\JidouInject\code\inject.py"

# (名称, IDML, 句读结果) — 取 done/ 归档的历史实际处理组合
CASES = [
    ("461", r"D:\Desktop\JidouInject\done\461\461导出.idml",
     r"D:\Desktop\JidouInject\done\461\461导出_WD句读结果.md"),
    ("275", r"D:\Desktop\JidouInject\done\275\275导出.idml",
     r"D:\Desktop\JidouInject\done\275\275从ID中导出文字_WD句读结果.md"),
    ("3093", r"D:\Desktop\JidouInject\done\3093\3093偈颂测试.idml",
     r"D:\Desktop\JidouInject\done\3093\3093偈颂测试句读结果.txt"),
]


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


def run(mod, idml, result, out_path):
    try:
        mod.process(idml, result, out_path)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main():
    old_mod = load_module(OLD, "inject_old")
    new_mod = load_module(NEW, "inject_new")
    print(f"旧代码: {OLD}")
    print(f"新代码: {NEW}")
    print()

    tmp = tempfile.mkdtemp(prefix="reg_p150_")
    all_ok = True
    try:
        for name, idml, result in CASES:
            print(f"=== {name}: {os.path.basename(idml)} + {os.path.basename(result)} ===")
            if not os.path.isfile(idml) or not os.path.isfile(result):
                print(f"    [跳过] 文件缺失: {idml} / {result}")
                continue
            out_old = os.path.join(tmp, f"{name}_old.idml")
            out_new = os.path.join(tmp, f"{name}_new.idml")
            ok_old, err_old = run(old_mod, idml, result, out_old)
            ok_new, err_new = run(new_mod, idml, result, out_new)
            if not ok_old:
                print(f"    [旧代码失败] {err_old}")
                all_ok = False
                continue
            if not ok_new:
                print(f"    [新代码失败] {err_new}")
                all_ok = False
                continue
            m_old = zip_members_bytes(out_old)
            m_new = zip_members_bytes(out_new)
            if set(m_old) == set(m_new) and all(m_old[n] == m_new[n] for n in m_old):
                print(f"    [通过] 输出 ZIP 全成员字节一致 ({len(m_new)} 个成员)")
            else:
                all_ok = False
                names_diff = set(m_old) ^ set(m_new)
                bytes_diff = [n for n in set(m_old) & set(m_new) if m_old[n] != m_new[n]]
                print(f"    [回归失败] 输出不一致: 成员差异 {sorted(names_diff)[:5]}, "
                      f"字节差异 {len(bytes_diff)} 个成员")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 60)
    print(f"回归结果: {'全部通过 ✓' if all_ok else '存在差异 ✗'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
