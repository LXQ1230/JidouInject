#!/usr/bin/env python3
"""FIX-4/5/6 合成用例验证（临时脚本，验证后删除）。

FIX-4: 拆分复制 Self —— 带 Self CSR + 槽内句号 → 输出无重复 Self
FIX-5: 多 Content 空槽 replace 错位 —— 相同空 Content 按索引定位替换
FIX-6: 正文内嵌 ACE 指令 —— 无记录 CSR 的 ACE Content 保留
"""
import sys, re
sys.path.insert(0, 'code')
from inject import CharRecord, _rebuild_paragraph_xml

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name} {detail}")

def mk(ch, csr=0, slot=0, pos=0):
    return CharRecord(char=ch, is_punct=False, is_special=False,
                      story_idx=0, para_idx=0, csr_idx=csr,
                      content_slot=slot, slot_pos=pos)

def mkp(pos, csr=0, slot=0):
    return CharRecord(char='。', is_punct=True, is_special=False,
                      story_idx=0, para_idx=0, csr_idx=-1,
                      content_slot=-1, after_csr=csr, after_slot=slot,
                      after_pos=pos)

print("=== FIX-4: 拆分复制 Self ===")
psr4 = ('<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
        '<CharacterStyleRange Self="u100" AppliedCharacterStyle="CharacterStyle/$ID/NormalCharacterStyle">'
        '<Content>如是我聞一時</Content></CharacterStyleRange>'
        '</ParagraphStyleRange>')
recs4 = [mk('如'), mk('是'), mk('我'), mk('聞'), mkp(3), mk('一'), mk('時')]
out4 = _rebuild_paragraph_xml(psr4, recs4)
self_count = out4.count('Self="u100"')
check("Self 唯一（首段保留 1 次）", self_count == 1, f"实际 {self_count} 次")
chars4 = re.findall(r'<Content>(.*?)</Content>', out4)
text4 = ''.join(chars4)
check("文字零丢失+句号正确", text4 == '如是我聞。一時', f"实际: {text4}")
# 逐字符拆分（槽内插句号实现）：如|是|我|聞|。|一|時 = 7 个 CSR
csr_count = len(re.findall(r'<CharacterStyleRange', out4))
check("拆分 CSR 数（逐字符 7 个）", csr_count == 7, f"实际 {csr_count}")
# 拆分产生的中间 CSR（非首段）不得含 Self 属性
non_first = out4.split('Self="u100"', 1)[1]
check("中间/句号段无 Self", 'Self="' not in non_first, f"残留: {re.findall(r'Self=\"[^\"]*\"', non_first)}")

print("=== FIX-5: 多 Content 空槽按索引替换 ===")
psr5 = ('<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/NormalCharacterStyle">'
        '<Content></Content><Content>色聲香</Content><Content></Content></CharacterStyleRange>'
        '</ParagraphStyleRange>')
# 槽0空、槽1'色聲香'、槽2空；在槽1 '香' 后插句号，槽0/槽2 空保持
recs5 = [CharRecord(char='色', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=1, slot_pos=0),
         CharRecord(char='聲', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=1, slot_pos=1),
         CharRecord(char='香', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=1, slot_pos=2),
         CharRecord(char='。', is_punct=True, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=-1, content_slot=-1,
                    after_csr=0, after_slot=1, after_pos=2)]
out5 = _rebuild_paragraph_xml(psr5, recs5)
contents5 = re.findall(r'<Content>(.*?)</Content>', out5)
check("槽位文本正确（空/色聲香。/空）", contents5 == ['', '色聲香。', ''],
      f"实际: {contents5}")

print("=== FIX-6: 正文内嵌 ACE 指令保留 ===")
psr6 = ('<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/NormalCharacterStyle">'
        '<Content><?ACE 18?></Content><Content>正文文字</Content></CharacterStyleRange>'
        '</ParagraphStyleRange>')
# 只有 '正文文字' 有记录；ACE 的 Content 在同一个 CSR 中且该 CSR 有记录 →
# 测试场景2：ACE 在无记录 CSR（独立 CSR）
psr6b = ('<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
         '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/NormalCharacterStyle">'
         '<Content>正文文字</Content></CharacterStyleRange>'
         '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/NormalCharacterStyle">'
         '<Content><?ACE 18?></Content></CharacterStyleRange>'
         '</ParagraphStyleRange>')
recs6 = [CharRecord(char='正', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=0, slot_pos=0),
         CharRecord(char='文', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=0, slot_pos=1),
         CharRecord(char='文', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=0, slot_pos=2),
         CharRecord(char='字', is_punct=False, is_special=False, story_idx=0,
                    para_idx=0, csr_idx=0, content_slot=0, slot_pos=3)]
out6 = _rebuild_paragraph_xml(psr6b, recs6)
check("ACE Content 保留", '<?ACE 18?>' in out6, f"实际: {out6[:200]}")
contents6 = re.findall(r'<Content>(.*?)</Content>', out6)
check("ACE 与正文均保留", contents6 == ['正文文字', '<?ACE 18?>'],
      f"实际: {contents6}")

print(f"\n结果: 通过 {passed} 项, 失败 {failed} 项")
sys.exit(1 if failed else 0)
