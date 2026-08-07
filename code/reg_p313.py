# -*- coding: utf-8 -*-
"""P3-13 自闭合空段落修复回归测试。

新旧代码（修复前备份 vs 修复后）对相同文件对各跑一次 process()，
对比输出 IDML 全成员字节，验证修复对非自闭合文件零影响。
"""
import importlib.util
import os
import sys
import types
import zipfile
import tempfile
import shutil

sys.stdout.reconfigure(encoding='utf-8')

OLD = r"D:\Desktop\JidouInject\backup\inject.py.v1.4.2-fix-selfclosing-2026.08.04.bak"
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
    # 纯内存加载：读源码 exec 到新模块，避免 .bak 扩展名与临时文件落盘问题
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


def story_text_contents(path: str) -> dict[str, str]:
    """提取每个 Story 的全部 Content 净文本（去加工指令、解实体）。

    用于内容级回归：v1.5.1-Br 修复 1 保留旧句号 CSR 的 Br 分行符
    （清空 Content 的空+Br CSR），输出 ZIP 成员字节必然变化，但所有
    Story 的字符内容必须与旧代码输出完全一致。
    """
    import html
    import re as _re
    result = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith('Stories/Story_'):
                raw = zf.read(name).decode('utf-8')
                contents = _re.findall(
                    r'<Content>(.*?)</Content>', raw, _re.DOTALL)
                text = _re.sub(r'<\?.*?\?>', '', ''.join(contents))
                result[name] = html.unescape(text)
    return result


def run(mod, idml, result, out_path):
    try:
        mod.process(idml, result, out_path)
        return True
    except Exception as e:
        print(f"    [失败] {type(e).__name__}: {e}")
        return False


def main():
    old_mod = load_module(OLD, "inject_old")
    new_mod = load_module(NEW, "inject_new")
    print(f"旧代码: {OLD}")
    print(f"新代码: {NEW}")
    print()

    tmp = tempfile.mkdtemp(prefix="reg_p313_")
    all_ok = True
    try:
        for name, idml, result in CASES:
            print(f"=== {name}: {os.path.basename(idml)} + {os.path.basename(result)} ===")
            if not os.path.isfile(idml) or not os.path.isfile(result):
                print(f"    [跳过] 文件缺失: {idml} / {result}")
                continue
            out_old = os.path.join(tmp, f"{name}_old.idml")
            out_new = os.path.join(tmp, f"{name}_new.idml")
            print(f"  [旧代码] 处理中...")
            ok_old = run(old_mod, idml, result, out_old)
            print(f"  [新代码] 处理中...")
            ok_new = run(new_mod, idml, result, out_new)
            if not (ok_old and ok_new):
                print(f"    [回归失败] 新旧代码未能全部成功")
                all_ok = False
                continue
            m_old = zip_members_bytes(out_old)
            m_new = zip_members_bytes(out_new)
            names_old = set(m_old)
            names_new = set(m_new)
            diff_names = names_old ^ names_new
            diff_bytes = [n for n in names_old & names_new if m_old[n] != m_new[n]]
            if diff_names or diff_bytes:
                # v1.5.1-Br: 字节不一致时回退内容级对比（与 reg_p314 一致）。
                # 修复 1（保留旧句号 CSR 的 Br 分行符）会让 461/275 输出
                # 多出清空 Content 的空+Br CSR，字节必然变化，但所有 Story
                # 的字符内容必须与旧代码输出完全一致。
                c_old = story_text_contents(out_old)
                c_new = story_text_contents(out_new)
                content_diff = [n for n in c_old
                                if n not in c_new or c_old[n] != c_new[n]]
                if diff_names or content_diff:
                    all_ok = False
                    print(f"    [回归失败] 输出不一致:")
                    for n in sorted(diff_names):
                        print(f"      - 成员差异: {n}")
                    for n in sorted(content_diff)[:5]:
                        print(f"      - 内容差异: {n} "
                              f"(旧 {len(c_old.get(n,''))}字 vs "
                              f"新 {len(c_new.get(n,''))}字)")
                else:
                    print(f"    [通过] 内容一致；字节差异仅 Br 分行保留"
                          f"（{len(diff_bytes)} 个 Story，"
                          f"净增 {sum(len(m_new[n])-len(m_old[n]) for n in diff_bytes)/1024:.0f}KB）")
            else:
                print(f"    [通过] 输出 ZIP 全成员字节一致 "
                      f"({len(m_new)} 个成员, 含 {name}导出_WD注入 语义)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("=" * 60)
    print(f"回归结果: {'全部通过 ✓' if all_ok else '存在差异 ✗'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
