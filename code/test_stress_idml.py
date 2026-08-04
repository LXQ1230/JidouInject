#!/usr/bin/env python3
"""
test_stress_idml.py — 超大 IDML 压力测试

程序化合成目标大小（默认 ~200MB）的 IDML：
  - 以 0080-楞伽（含 11MB 大 Story）为模板
  - 大 Story 复制 N 次（Self ID 唯一化）放大文字量
  - 追加大体积假资源成员（STORED）凑压缩体积

然后运行完整回注流水线（process，含三层验证），断言：
  1. 全流程无异常
  2. 输出文字零改动（跨 Story 净字符一致）
  3. 进程峰值 RSS 有界（默认 < 4GB，可用 JIDOU_STRESS_MEM_MB 覆盖）

用法:
    python code/test_stress_idml.py [目标MB] [Story复制次数] [文本放大factor]
    示例: python code/test_stress_idml.py 200 6 50
    - Story 复制次数：文字量倍数（每个复制 Story 净字约 5.3 千 × factor）
    - 文本放大 factor：Content 文本重复次数，用于构造高文字量场景
      （IDML 的 XML 中 Content 占比很小，直接复制 Story 文字量不足）
"""

import sys
import os
import re
import zipfile
import ctypes
import time

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CODE_DIR)
sys.path.insert(0, CODE_DIR)

import inject  # noqa: E402

BASE_IDML = os.path.join(PROJECT_ROOT, "source", "3093偈颂测试.idml")
OUT_DIR = os.path.join(PROJECT_ROOT, "output")
TARGET_MB = int(sys.argv[1]) if len(sys.argv) > 1 else 200
STORY_COPIES = int(sys.argv[2]) if len(sys.argv) > 2 else 2
TEXT_FACTOR = int(sys.argv[3]) if len(sys.argv) > 3 else 30
MEM_LIMIT_MB = int(os.environ.get("JIDOU_STRESS_MEM_MB", "4096"))


class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("pfc", ctypes.c_ulong),
        ("pws", ctypes.c_size_t), ("ws", ctypes.c_size_t),
        ("qpp", ctypes.c_size_t), ("qpp2", ctypes.c_size_t),
        ("qnp", ctypes.c_size_t), ("qnp2", ctypes.c_size_t),
        ("pu", ctypes.c_size_t), ("ppu", ctypes.c_size_t),
    ]


def _peak_rss_mb() -> float:
    try:
        psapi = ctypes.WinDLL("psapi.dll")
        k32 = ctypes.WinDLL("kernel32.dll")
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                   ctypes.byref(pmc), pmc.cb)
        return pmc.pws / 1024 / 1024
    except Exception:
        return -1.0


def _unique_story_xml(xml: str, prefix: str) -> str:
    """将 XML 内全部 Self ID 加上前缀，保证复制后全局唯一"""
    return re.sub(r'Self="([^"]+)"', lambda m: f'Self="{prefix}{m.group(1)}"', xml)


def _expand_story_xml(xml: str, factor: int) -> str:
    """放大 Content 文本（重复 factor 次）以扩大净文字量。

    IDML 的 Content 文本在 XML 中占比很小（686KB XML 仅约 5 千净字），
    直接复制 Story 无法构造高文字量场景。将每个 <Content> 文本重复
    factor 次，保持结构不变，净字符数放大 factor 倍。
    """
    if factor <= 1:
        return xml

    def repl(m):
        text = re.sub(r'<\?.*?\?>', '', m.group(1))
        return f'<Content>{text * factor}</Content>'

    return re.sub(r'<Content>(.*?)</Content>', repl, xml, flags=re.DOTALL)


def build_stress_idml(target_bytes: int, copies: int) -> str:
    """构造目标大小的大 IDML，返回文件路径"""
    os.makedirs(OUT_DIR, exist_ok=True)
    dst = os.path.join(OUT_DIR, f"_stress_{target_bytes // 1024 // 1024}MB"
                                 f"_c{copies}.idml")
    if os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError:
            pass

    with zipfile.ZipFile(BASE_IDML) as zf_in:
        infos = zf_in.infolist()
        # 找最大的 Story（约 68 万字符，作为文字放大单元）
        big = max(infos, key=lambda zi: zi.file_size
                  if "Stories" in zi.filename else 0)
        big_xml = zf_in.read(big).decode("utf-8")
        big_name = big.filename[len("Stories/Story_"):-len(".xml")]

        designmap = zf_in.read("designmap.xml").decode("utf-8")
        orig_stories = [(zi, zf_in.read(zi))
                        for zi in infos if zi.filename.startswith("Stories/")]
        others = [(zi, zf_in.read(zi))
                  for zi in infos
                  if (not zi.filename.startswith("Stories/")
                      and zi.filename != "designmap.xml"
                      and zi.filename != "mimetype")]

        # 追加新 story 名到 designmap
        # 注意：故意保留原始 StoryList（含文件缺失的 story，如 3093 的 ub3），
        # 以覆盖"story_idx 空洞"场景——验证 inject 按实际索引定位 story
        # （修复前：空洞导致复制 story 索引越界被静默跳过重建）。
        story_list_m = re.search(r'StoryList="([^"]*)"', designmap)
        orig_names = story_list_m.group(1).split() if story_list_m else []
        extra_names = [f"cp{i}_{big_name}" for i in range(1, copies + 1)]
        designmap = designmap.replace(
            story_list_m.group(0),
            f'StoryList="{" ".join(orig_names + extra_names)}"')

        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf_out:
            # mimetype 保持 STORED 且首位
            zf_out.writestr(zipfile.ZipInfo("mimetype"),
                            "application/vnd.adobe.idml")
            zf_out.writestr("designmap.xml", designmap)
            for zi, data in others:
                zf_out.writestr(zi, data)
            # 原 Story + 复制 Story（Self ID 唯一化 + 文本放大）
            for zi, data in orig_stories:
                zf_out.writestr(zi, data)
            big_expanded = _expand_story_xml(big_xml, TEXT_FACTOR)
            for i, sname in enumerate(extra_names, 1):
                zf_out.writestr(
                    f"Stories/Story_{sname}.xml",
                    _unique_story_xml(big_expanded, f"CP{i}_"))
            # 假资源（STORED，零字节块）凑压缩体积
            est = os.path.getsize(dst)
            fake = max(0, target_bytes - est)
            chunk = b"\x00" * (8 * 1024 * 1024)
            idx = 0
            while fake > 0:
                n = min(len(chunk), fake)
                zf_out.writestr(zipfile.ZipInfo(f"Resources/fake_{idx}.bin"),
                                chunk[:n], compress_type=zipfile.ZIP_STORED)
                fake -= n
                idx += 1
    return dst


def _clean_chars_all(path: str) -> list[str]:
    """提取 IDML 全部非标点、非空白文字（跨所有 Story，与对齐规则一致）"""
    chars: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith("Stories/Story_"):
                continue
            xml = zf.read(name).decode("utf-8")
            for c in re.findall(r"<Content>(.*?)</Content>", xml, re.DOTALL):
                c = re.sub(r"<\?.*?\?>", "", c)
                for ch in c:
                    if (not inject._is_old_punct(ch)
                            and not inject._is_unicode_whitespace(ch)
                            and not inject._is_ws_for_compare(ch)):
                        chars.append(ch)
    return chars


def main() -> int:
    print("=" * 60)
    print(f"超大 IDML 压力测试: 目标 {TARGET_MB}MB, "
          f"Story 复制 {STORY_COPIES} 次, 文本放大 ×{TEXT_FACTOR}, "
          f"内存上限 {MEM_LIMIT_MB}MB")
    print("=" * 60)

    t0 = time.time()
    print("\n[1/4] 合成大 IDML...")
    stress_idml = build_stress_idml(TARGET_MB * 1024 * 1024, STORY_COPIES)
    size_mb = os.path.getsize(stress_idml) / 1024 / 1024
    print(f"  已生成: {size_mb:.0f} MB")

    print("\n[2/4] 生成句读结果（每 20 字直接插句号，覆盖槽内插入路径）...")
    stories = inject.extract_from_idml(stress_idml)
    total_chars = sum(len(p['chars']) for s in stories for p in s['paragraphs'])

    # 句号直接按字符间隔插入（不避让 Content slot 边界）——
    # 覆盖"句号落在多字 slot 内部"的重建路径（槽内偏移插入）。
    buf: list[str] = []
    count = 0
    for s in stories:
        # 与 validate_and_align 一致：跳过 <50 净字符的装饰性 Story
        story_clean = sum(
            1 for p in s['paragraphs'] for r in p['chars']
            if not r['is_punct'] and not r.get('is_special', False)
            and not inject._is_unicode_whitespace(r['char']))
        if story_clean < 50:
            continue
        for p in s['paragraphs']:
            for r in p['chars']:
                # 与真实流程一致（AGENTS.md 步骤 0 清除标点及空格）：
                # 用 _is_ws_for_compare 排除（含 U+3000 分字空格）
                if (r['is_punct'] or r.get('is_special', False)
                        or inject._is_ws_for_compare(r['char'])):
                    continue
                buf.append(r['char'])
                count += 1
                if count % 20 == 0:
                    buf.append('。')
                    count = 0
    result_text = ''.join(buf)
    result_path = os.path.join(OUT_DIR, "_stress_result.txt")
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write(result_text)
    print(f"  句读结果 {len(result_text)} 字符（源记录 {total_chars} 条）")
    del stories
    import gc
    gc.collect()

    print("\n[3/4] 运行完整回注流水线...")
    out_path = os.path.join(OUT_DIR, "_stress_out.idml")
    t1 = time.time()
    inject.process(stress_idml, result_path, out_path)
    process_sec = time.time() - t1
    print(f"  回注耗时 {process_sec:.1f}s")

    print("\n[4/4] 断言检查...")
    ok = True
    peak = _peak_rss_mb()
    print(f"  峰值 RSS: {peak:.0f} MB (上限 {MEM_LIMIT_MB} MB)")
    if peak < 0:
        print("  ✗ 内存测量失败")
        ok = False
    elif peak > MEM_LIMIT_MB:
        print(f"  ✗ 峰值内存超限")
        ok = False
    else:
        print("  ✓ 峰值内存有界")

    orig_chars = _clean_chars_all(stress_idml)
    out_chars = _clean_chars_all(out_path)
    if orig_chars == out_chars:
        print(f"  ✓ 输出文字零改动 ({len(orig_chars)} 字)")
    else:
        print(f"  ✗ 文字不一致: 输入 {len(orig_chars)} vs 输出 {len(out_chars)}")
        ok = False

    try:
        os.remove(stress_idml)
        os.remove(result_path)
        os.remove(out_path)
    except OSError:
        pass

    print(f"\n总耗时 {time.time() - t0:.1f}s")
    print(f"压力测试{'通过 ✓' if ok else '失败 ✗'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
