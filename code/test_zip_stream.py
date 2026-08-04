#!/usr/bin/env python3
"""
test_zip_stream.py — 第 1 层（ZIP 按需读写）专项验证

验证 generate_idml 的流式写回：
1. 输出成员集合与输入一致
2. 成员顺序一致（mimetype 首位）
3. mimetype 保持 STORED（compress_type=0）
4. 未修改成员解压后逐字节一致
5. 修改的 Story 内容正确写入
6. 压缩方式逐成员保留
7. 真实样本 generate_idml 集成：文字零改动 + ZIP 结构正确

注：2026-08-04（P3-3）起测试改走 generate_idml（_stream_write_idml
独立函数已删除，其流式写回机制由 generate_idml 内联承担）。

用法:
    python code/test_zip_stream.py
"""

import sys
import os
import zipfile
import importlib.util

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CODE_DIR)
sys.path.insert(0, CODE_DIR)

import inject  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"    ✓ {name}" + (f": {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"    ✗ {name}" + (f": {detail}" if detail else ""))


def make_fake_idml(path: str) -> dict:
    """构造一个最小 IDML（mimetype STORED + designmap + 2 个 Story）"""
    story_a = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Story Self="u001"><ParagraphStyleRange Self="p1">'
               '<CharacterStyleRange Self="c1"><Content>阿彌陀佛</Content>'
               '</CharacterStyleRange></ParagraphStyleRange></Story>')
    story_b = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Story Self="u002"><ParagraphStyleRange Self="p2">'
               '<CharacterStyleRange Self="c2"><Content>南無觀世音菩薩</Content>'
               '</CharacterStyleRange></ParagraphStyleRange></Story>')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr(zipfile.ZipInfo('mimetype'), 'application/vnd.adobe.idml')
        # designmap 用真实 IDML 属性格式（StoryList="..."），
        # 否则 _parse_story_order 无法匹配导致 stories 解析为空
        zf.writestr('designmap.xml',
                    '<DesignMap><StoryList Self="u000" StoryList="u001 u002"/></DesignMap>')
        zf.writestr('Stories/Story_u001.xml', story_a)
        zf.writestr('Stories/Story_u002.xml', story_b)
    return {'u001': story_a, 'u002': story_b}


def test_stream_write_basic() -> None:
    """generate_idml 基本写回行为（替换单个 Story，其余流式拷贝）"""
    print("\n[1] generate_idml 基本行为")
    tmp_dir = os.path.join(PROJECT_ROOT, "output")
    os.makedirs(tmp_dir, exist_ok=True)
    src = os.path.join(tmp_dir, "_ztest_src.idml")
    dst = os.path.join(tmp_dir, "_ztest_dst.idml")
    originals = make_fake_idml(src)

    # 构造对齐记录：Story_u002（story_idx=1）重建为「南無觀世音菩薩。」
    stories = inject.extract_from_idml(src)
    records = []
    for i, ch in enumerate('南無觀世音菩薩'):
        records.append(inject.CharRecord(
            char=ch, is_punct=False, is_special=False,
            story_idx=1, para_idx=0, csr_idx=0, content_slot=0, slot_pos=i))
    records.append(inject.CharRecord(
        char='。', is_punct=True, is_special=False,
        story_idx=1, para_idx=0, csr_idx=-1, content_slot=-1,
        after_csr=0, after_slot=0, after_pos=5))
    grouped = {1: {0: records}}
    inject.generate_idml(src, stories, grouped, {}, dst)

    with zipfile.ZipFile(dst) as zf:
        names = zf.namelist()
        infos = zf.infolist()
        # 1. 成员集合一致
        check("成员集合一致", set(names) == {'mimetype', 'designmap.xml',
              'Stories/Story_u001.xml', 'Stories/Story_u002.xml'}, str(names))
        # 2. 成员顺序一致 + mimetype 首位
        check("mimetype 首位", names[0] == 'mimetype', names[0])
        # 3. mimetype STORED
        check("mimetype STORED", infos[0].compress_type == zipfile.ZIP_STORED,
              f"compress_type={infos[0].compress_type}")
        # 4. 未修改成员逐字节一致
        ok = zf.read('Stories/Story_u001.xml') == originals['u001'].encode('utf-8')
        check("未修改成员逐字节一致", ok)
        # 5. 修改的 Story 内容正确（v2.0 槽内插句号：逐字符拆分 + 句号）
        new_xml = zf.read('Stories/Story_u002.xml').decode('utf-8')
        contents = re.findall(r'<Content>(.*?)</Content>', new_xml)
        check("修改 Story 内容正确",
              contents == ['南', '無', '觀', '世', '音', '菩', '薩', '。'],
              new_xml[:120])
        # 6. 压缩方式逐成员保留
        ok = all(o.compress_type == n.compress_type
                 for o, n in zip(
                     zipfile.ZipFile(src).infolist(), infos))
        check("压缩方式逐成员保留", ok)

    for f in (src, dst):
        try:
            os.remove(f)
        except OSError:
            pass


def test_stream_idempotent() -> None:
    """空更新（grouped={}）→ 输出与输入完全等价（全量流式拷贝）"""
    print("\n[2] 空更新幂等性")
    tmp_dir = os.path.join(PROJECT_ROOT, "output")
    src = os.path.join(tmp_dir, "_ztest_src2.idml")
    dst = os.path.join(tmp_dir, "_ztest_dst2.idml")
    originals = make_fake_idml(src)
    stories = inject.extract_from_idml(src)
    inject.generate_idml(src, stories, {}, {}, dst)

    with zipfile.ZipFile(src) as zf1, zipfile.ZipFile(dst) as zf2:
        n1, n2 = zf1.namelist(), zf2.namelist()
        check("成员集合与顺序一致", n1 == n2)
        ok = all(zf1.read(n) == zf2.read(n) for n in n1)
        check("全部成员逐字节一致", ok)
    for f in (src, dst):
        try:
            os.remove(f)
        except OSError:
            pass


def test_generate_idml_real_sample() -> None:
    """真实样本 generate_idml 集成：文字零改动 + ZIP 结构正确"""
    print("\n[3] 真实样本 generate_idml 集成")
    idml_path = os.path.join(PROJECT_ROOT, "source", "3093偈颂测试.idml")
    result_path = os.path.join(PROJECT_ROOT, "source", "3093偈颂测试.txt")
    out_path = os.path.join(PROJECT_ROOT, "output", "_ztest_3093.idml")
    if not os.path.exists(idml_path) or not os.path.exists(result_path):
        check("3093 样本存在", False, "跳过")
        return

    stories = inject.extract_from_idml(idml_path)
    result_data = inject.extract_from_result(result_path)
    alignment = inject.validate_and_align(stories, result_data)
    inject.generate_idml(idml_path, stories, alignment['grouped'],
                         alignment['split_sources'], out_path)

    with zipfile.ZipFile(idml_path) as zf_in, zipfile.ZipFile(out_path) as zf_out:
        n_in, n_out = zf_in.namelist(), zf_out.namelist()
        check("成员集合一致", set(n_in) == set(n_out),
              f"{len(n_in)} vs {len(n_out)}")
        check("成员顺序一致", n_in == n_out)
        check("mimetype 首位且 STORED",
              n_out[0] == 'mimetype'
              and zf_out.infolist()[0].compress_type == zipfile.ZIP_STORED)
        # 未修改成员逐字节一致（跳过被替换的 Story）
        diffs = [n for n in n_in
                 if zf_in.read(n) != zf_out.read(n)
                 and not n.startswith('Stories/Story_')]
        check("非 Story 成员逐字节一致", not diffs, str(diffs)[:200])
        # 压缩方式逐成员保留
        ct_in = {zi.filename: zi.compress_type for zi in zf_in.infolist()}
        ct_out = {zi.filename: zi.compress_type for zi in zf_out.infolist()}
        check("压缩方式逐成员保留", ct_in == ct_out)

    # 文字零改动：输出 clean 字符与输入一致（用 inject 的内部逻辑）
    orig_chars = _clean_chars(idml_path)
    out_chars = _clean_chars(out_path)
    check("原文字符零改动", orig_chars == out_chars,
          f"{len(orig_chars)} 字")

    try:
        os.remove(out_path)
    except OSError:
        pass


def _clean_chars(path: str) -> list[str]:
    """提取 IDML 全部非标点、非空白文字（跨所有 Story）"""
    chars = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.startswith('Stories/Story_'):
                continue
            xml = zf.read(name).decode('utf-8')
            for c in re.findall(r'<Content>(.*?)</Content>', xml, re.DOTALL):
                c = re.sub(r'<\?.*?\?>', '', c)
                for ch in c:
                    if (not inject._is_old_punct(ch)
                            and not inject._is_unicode_whitespace(ch)
                            and not inject._is_ws_for_compare(ch)):
                        chars.append(ch)
    return chars


if __name__ == "__main__":
    import re
    print("=" * 60)
    print("ZIP 流式写回专项测试")
    print("=" * 60)
    test_stream_write_basic()
    test_stream_idempotent()
    test_generate_idml_real_sample()
    print(f"\n{'=' * 60}")
    print(f"通过 {PASS} 项, 失败 {FAIL} 项")
    sys.exit(1 if FAIL else 0)
