# -*- coding: utf-8 -*-
"""验证假设：A) 旧句号CSR(Content='。')被整体删除丢Br；
B) 拆分时 csr_suffix 从 rfind('</CharacterStyleRange>') 截取丢 Content 后 Br。"""
import sys, os, re, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

IDML = r"D:/Desktop/JidouInject/pending/26-A.idml"
CSR_RE = re.compile(
    r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)',
    re.DOTALL)
PSR_RE = re.compile(
    r'<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>'
    r'|<ParagraphStyleRange[^>]*?/>', re.DOTALL)

with zipfile.ZipFile(IDML, 'r') as zf:
    in_xml = zf.read('Stories/Story_u15de.xml').decode('utf-8')
psrs = list(PSR_RE.finditer(in_xml))

# --- PSR[1] 的带 Br 文字 CSR 结构 ---
print("===== PSR[1] 带 Br 的 CSR 结构（Br 在 prefix 还是 suffix）=====")
for ci, m in enumerate(CSR_RE.finditer(psrs[1].group(0))):
    x = m.group(0)
    if '<Br' not in x:
        continue
    cs = x.find('<Content>')
    ce = x.rfind('</Content>') + len('</Content>')
    prefix_br = x[:cs].count('<Br />') + x[:cs].count('<Br/>')
    suffix_br = x[ce:].count('<Br />') + x[ce:].count('<Br/>')
    inner = x[cs:ce]
    contents = re.findall(r'<Content>(.*?)</Content>', x, re.DOTALL)
    prev = (contents[0][:15] if contents else '(无)')
    print(f"  CSR[{ci}] 前缀Br={prefix_br} 后缀Br={suffix_br} 文本={prev!r}")

# --- PSR[0] 旧句号 CSR 的样式 ---
print("\n===== PSR[0] 带 Br 且 Content='。' 的 CSR 样式 =====")
for ci, m in enumerate(CSR_RE.finditer(psrs[0].group(0))):
    x = m.group(0)
    if '<Br' not in x:
        continue
    contents = re.findall(r'<Content>(.*?)</Content>', x, re.DOTALL)
    if contents and contents[0].strip() == '。':
        head = x[:300].replace('\n', ' ')
        print(f"  CSR[{ci}]: {head}")
