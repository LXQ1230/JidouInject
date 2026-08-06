# -*- coding: utf-8 -*-
"""诊断 497 段落数不一致（预期 581 vs 实际 582）。"""
import re
import sys
import zipfile
import os

sys.stdout.reconfigure(encoding='utf-8')

IDML = r"D:\Desktop\JidouInject\pending\497有图.idml"
TXT = r"D:\Desktop\JidouInject\pending\497有图.txt"

print("=" * 70)
print("诊断 1: 每个 Story 的 PSR 开标签数 vs 完整配对段数")
print("=" * 70)
mismatch_total = 0
with zipfile.ZipFile(IDML) as zf:
    for name in sorted(zf.namelist()):
        if not name.startswith('Stories/Story_'):
            continue
        xml = zf.read(name).decode('utf-8')
        opens = len(re.findall(r'<ParagraphStyleRange[^>]*>', xml))
        pairs = len(re.findall(
            r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>',
            xml, re.DOTALL))
        if opens != pairs:
            mismatch_total += 1
            print(f"  [{name}] opens={opens} pairs={pairs} 差异={opens-pairs}")
            # 定位多出的开标签位置
            starts = [m.start() for m in re.finditer(r'<ParagraphStyleRange', xml)]
            ends = [m.end() for m in re.finditer(r'</ParagraphStyleRange>', xml)]
            if len(starts) > len(ends):
                print(f"    → 开标签 {len(starts)} 个，闭标签 {len(ends)} 个")
                for i, s in enumerate(starts):
                    ctx = xml[s:s+200].replace('\n', '\\n')
                    print(f"      open[{i}] @{s}: {ctx[:150]}")
            if len(ends) > len(starts):
                print(f"    → 闭标签 {len(ends)} 个，开标签 {len(starts)} 个")
                for i, e in enumerate(ends):
                    ctx = xml[max(0,e-200):e].replace('\n', '\\n')
                    print(f"      end[{i}] @{e}: ...{ctx[-150:]}")
if mismatch_total == 0:
    print("  所有 Story 开标签数 = 配对段数（无异常）")

print()
print("=" * 70)
print("诊断 2: txt 是否原文（句号数对比）")
print("=" * 70)
with open(TXT, 'r', encoding='utf-8-sig') as f:
    txt_content = f.read()
txt_dots = txt_content.count('。')
# IDML 旧句号数
with zipfile.ZipFile(IDML) as zf:
    all_xml = ''
    for name in zf.namelist():
        if name.startswith('Stories/Story_'):
            all_xml += zf.read(name).decode('utf-8')
# 从 Content 中提取旧句号（仿 _verify_extraction）
contents = re.findall(r'<Content>(.*?)</Content>', all_xml, re.DOTALL)
raw_text = re.sub(r'<\?.*?\?>', '', ''.join(contents))
raw_text = raw_text.replace('&#x3002;', '。').replace('&amp;', '&')
idml_dots = raw_text.count('。')
print(f"  txt 句号数:   {txt_dots}")
print(f"  IDML 旧句号数: {idml_dots}")
print(f"  差异: {abs(txt_dots - idml_dots)}（{'<5%，疑似原文' if idml_dots and abs(txt_dots-idml_dots)/idml_dots < 0.05 else '>=5%'}）")

print()
print("=" * 70)
print("诊断 3: txt 中非句号旧标点统计")
print("=" * 70)
punct_set = {}
for ch in txt_content:
    if re.match(r'[，、；：！？「」『』（）《》〈〉,.;:!?()\"\'\[\]【】]', ch):
        punct_set[ch] = punct_set.get(ch, 0) + 1
if punct_set:
    for ch, n in sorted(punct_set.items()):
        print(f"  {ch}: {n}")
else:
    print("  无非句号标点（仅文字 + 。）")

print()
print("=" * 70)
print("诊断 4: txt 头部 300 字符（判断是否句读结果文件头）")
print("=" * 70)
print(repr(txt_content[:300]))

print()
print("=" * 70)
print("诊断 5: txt 空行数（段落边界）")
print("=" * 70)
blank_lines = sum(1 for ln in txt_content.split('\n') if ln.strip() == '')
print(f"  空行数: {blank_lines}")
