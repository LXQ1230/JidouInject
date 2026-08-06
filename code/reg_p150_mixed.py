# -*- coding: utf-8 -*-
"""v1.5.0 混合标点功能测试。

以 461 的纯句号句读结果为基底，程序化把部分句号替换为 ，、；：？！，
跑 v1.5.0 process()，验证：
1. FIX-1B 白名单放行（混合标点结果不再被拒）
2. 输出 IDML 中标点类型齐全、数量正确（内置 _verify_output 已逐字核对，
   此处再独立从输出 ZIP 原始 XML 复核标点字符与注入样式）
3. 白名单外标点（如「」）仍被 FIX-1B 拒绝
"""
import os
import re
import sys
import types
import zipfile
import tempfile
import shutil

sys.stdout.reconfigure(encoding='utf-8')

INJECT = r"D:\Desktop\JidouInject\code\inject.py"
IDML = r"D:\Desktop\JidouInject\done\461\461导出.idml"
SRC_RESULT = r"D:\Desktop\JidouInject\done\461\461导出_WD句读结果.md"

PUNCTS = '，、；：？！。'


def load_module(path: str, name: str):
    with open(path, 'r', encoding='utf-8') as f:
        source = f.read()
    mod = types.ModuleType(name)
    mod.__file__ = path
    sys.modules[name] = mod
    exec(compile(source, path, 'exec'), mod.__dict__)
    return mod


def output_punct_stats(path: str) -> dict[str, int]:
    """从输出 IDML 的 Story XML 直接统计 Content 中的标点数量。"""
    stats = {p: 0 for p in PUNCTS}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            raw = zf.read(name).decode('utf-8')
            contents = re.findall(r'<Content>(.*?)</Content>', raw, re.DOTALL)
            text = re.sub(r'<\?.*?\?>', '', ''.join(contents))
            for ch in text:
                if ch in stats:
                    stats[ch] += 1
    return stats


def main():
    mod = load_module(INJECT, "inject_new")
    src = open(SRC_RESULT, encoding='utf-8-sig').read()
    hdr = re.match(r'#[^\n]*\n\s*\n---\n', src)
    body = src[hdr.end():] if hdr else src

    # 程序化混合标点：不同间隔把 。 换成其他 6 种标点
    dots = [i for i, ch in enumerate(body) if ch == '。']
    repl = {}
    for k, idx in enumerate(dots):
        if k % 11 == 0:
            repl[idx] = '，'
        elif k % 7 == 0:
            repl[idx] = '；'
        elif k % 5 == 0:
            repl[idx] = '？'
        elif k % 13 == 0:
            repl[idx] = '、'
        elif k % 3 == 0:
            repl[idx] = '：'
        elif k % 2 == 0:
            repl[idx] = '！'
    body_list = list(body)
    for i, p in repl.items():
        body_list[i] = p
    mixed = ''.join(body_list)
    expected_stats = {p: mixed.count(p) for p in PUNCTS}
    if hdr:
        mixed_full = src[:hdr.end()] + mixed
    else:
        mixed_full = mixed

    tmp = tempfile.mkdtemp(prefix="reg_p150_mixed_")
    try:
        result_path = os.path.join(tmp, "461_mixed_句读结果.md")
        with open(result_path, 'w', encoding='utf-8') as f:
            f.write(mixed_full)
        out_path = os.path.join(tmp, "461_mixed注入.idml")

        print("=== 测试 1: 混合标点结果（FIX-1B 白名单放行 + 注入） ===")
        mod.process(IDML, result_path, out_path)
        stats = output_punct_stats(out_path)
        print(f"  结果文件标点统计: {expected_stats}")
        print(f"  输出 IDML 标点统计: {stats}")

        # 输出统计必须等于预期（461 为散文，无仿宋/楷体/偈颂 U+3000
        # 抑制场景，全部标点应注入；若出现抑制差异会在下方指出）
        ok = True
        for p in PUNCTS:
            if stats[p] != expected_stats[p]:
                ok = False
                print(f"  [差异] {p}: 结果 {expected_stats[p]} vs 输出 {stats[p]}")
        if not ok:
            print("  [失败] 输出标点数量与结果不一致")
            sys.exit(1)
        print("  [通过] 7 种标点全部注入，数量与结果文件一致")

        print("\n=== 测试 2: 白名单外标点仍被 FIX-1B 拒绝 ===")
        bad_body = mixed.replace('，', '「', 1)
        bad_path = os.path.join(tmp, "461_bad.txt")
        with open(bad_path, 'w', encoding='utf-8') as f:
            f.write(bad_body)
        try:
            mod.process(IDML, bad_path, os.path.join(tmp, "bad_out.idml"))
            print("  [失败] 含「」的结果未被拒绝")
            sys.exit(1)
        except ValueError as e:
            assert '「' in str(e) and '白名单' in str(e), str(e)
            print(f"  [通过] 已拒绝: {str(e)[:60]}...")

        print("\n=== 测试 3: 输出 XML 中标点样式抽查（思源宋体） ===")
        with zipfile.ZipFile(out_path) as zf:
            xmls = {n: zf.read(n).decode('utf-8') for n in zf.namelist()
                    if n.startswith('Stories/Story_')}
        punct_csrs = 0
        non_sy_csrs = 0
        for xml in xmls.values():
            for m in re.finditer(
                r'<CharacterStyleRange([^>]*)>(.*?)</CharacterStyleRange>',
                xml, re.DOTALL,
            ):
                content_m = re.search(r'<Content>(.*?)</Content>', m.group(2))
                if not content_m:
                    continue
                c = content_m.group(1)
                if c in PUNCTS and c != '。':
                    punct_csrs += 1
                    if '思源宋体' not in m.group(2):
                        non_sy_csrs += 1
        print(f"  非句号标点 CSR: {punct_csrs} 个，非思源宋体: {non_sy_csrs} 个")
        assert punct_csrs > 0 and non_sy_csrs == 0
        print("  [通过] 全部新标点 CSR 均使用思源宋体")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n混合标点功能测试全部通过 ✓")


if __name__ == "__main__":
    main()
