# IDML 句读结果回注工具 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将句读结果 MD 中的文字和「。」注入回 IDML，排版样式原封不动。

**Architecture:** 单文件 Python 脚本。解析 IDML 的 Story XML → 提取每个字的样式 → 与句读结果对齐 → 生成新 IDML。

**Tech Stack:** Python 3，仅标准库（zipfile, xml.etree.ElementTree, argparse, re, shutil）

## Global Constraints

- IDML 的 XML 结构、段落边界、样式属性全部保留
- 句读结果只贡献字符序列（含「。」），忽略其中换行空格
- 新增「。」使用 IDML 中已有的 `CharacterStyle/句号` 样式
- `<?ACE?>` 等 XML 加工指令原封不动保留
- 字数验证不通过则报错中止，不产生输出文件

---

## File Structure

| 文件 | 职责 |
|------|------|
| `inject.py` | 主脚本：全部逻辑 + CLI |
| `inject.bat` | Windows 拖拽包装器 |

---

### Task 1: 项目初始化

**Files:**
- Create: `inject.py`
- Create: `inject.bat`

**Produces:** 可运行的空脚本骨架 + 拖拽批处理

- [ ] **Step 1: 创建 inject.py 骨架**

```python
#!/usr/bin/env python3
"""
IDML 句读结果回注工具
将 _WD句读结果.md 中的文字和「。」注入回 IDML，排版样式原封不动。

用法:
    python inject.py --idml 275导出.idml --result 275从ID中导出文字_WD句读结果.md
    或拖拽两个文件到 inject.bat 上
"""

import sys
import os
import re
import argparse
import shutil
import tempfile
import zipfile
from xml.etree import ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description="IDML 句读结果回注工具")
    parser.add_argument("--idml", required=True, help="原始 IDML 文件路径")
    parser.add_argument("--result", required=True, help="句读结果 MD 文件路径")
    parser.add_argument("--output", help="输出 IDML 路径（默认自动生成）")
    args = parser.parse_args()

    if args.output is None:
        base = os.path.splitext(args.idml)[0]
        args.output = f"{base}_WD注入.idml"

    print(f"输入 IDML: {args.idml}")
    print(f"句读结果: {args.result}")
    print(f"输出文件: {args.output}")

    process(args.idml, args.result, args.output)


def process(idml_path, result_path, output_path):
    """主处理流程"""
    # Step 1: 从 IDML 提取字符记录
    stories = extract_from_idml(idml_path)
    # Step 2: 从句读结果提取字符
    result_chars = extract_from_result(result_path)
    # Step 3: 验证并对齐
    new_stories = validate_and_align(stories, result_chars)
    # Step 4: 生成新 IDML
    generate_idml(idml_path, new_stories, output_path)
    print(f"完成！输出: {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 创建 inject.bat 拖拽包装器**

```batch
@echo off
REM 接受拖拽：第一个文件是 IDML，第二个是句读结果 MD
python "%~dp0inject.py" --idml "%~1" --result "%~2"
pause
```

- [ ] **Step 3: 验证脚本可运行**

```bash
python inject.py --help
```

Expected: 显示帮助信息，提示需要 --idml 和 --result 参数。

---

### Task 2: 从 IDML 提取字符和样式

**Files:**
- Modify: `inject.py`

**Produces:** `extract_from_idml()` 函数，返回 stories 结构

- [ ] **Step 1: 实现 extract_from_idml()**

```python
def extract_from_idml(idml_path):
    """
    从 IDML 中提取所有文字及其样式信息。
    
    返回: stories — 列表，每个元素是一个 story 的段落列表
          stories[story_index] = [paragraph, ...]
          paragraph = {
              'opening_tags': str,    # <ParagraphStyleRange ...> 及 <Properties> 等
              'chars': [char_record, ...],
              'closing_tag': str,     # </ParagraphStyleRange>
          }
          char_record = {
              'char': str,            # 单个字符
              'is_punct': bool,       # 是否旧标点（句号样式）
              'style': str,           # CharacterStyleRange 的 XML 模板
              'story_idx': int,       # 所属 Story 索引
              'para_idx': int,        # 所属段落索引（在该 Story 内）
          }
    """
    stories = []
    
    with zipfile.ZipFile(idml_path, 'r') as zf:
        # 读取 designmap.xml 获取 Story 顺序
        designmap = zf.read('designmap.xml').decode('utf-8')
        story_order = _parse_story_order(designmap)
        
        # 读取每个 Story XML
        for story_idx, story_name in enumerate(story_order):
            story_path = f'Stories/{story_name}.xml'
            if story_path not in zf.namelist():
                continue
            
            story_xml = zf.read(story_path).decode('utf-8')
            paragraphs = _parse_story_xml(story_xml, story_idx)
            stories.append({
                'name': story_name,
                'path': story_path,
                'xml_header': _get_story_header(story_xml),
                'xml_footer': _get_story_footer(story_xml),
                'paragraphs': paragraphs,
            })
    
    return stories


def _parse_story_order(designmap_xml):
    """从 designmap.xml 提取 StoryList 属性中的 Story 顺序"""
    match = re.search(r'StoryList="([^"]*)"', designmap_xml)
    if match:
        return match.group(1).split()
    return []


def _parse_story_xml(story_xml, story_idx):
    """
    解析一个 Story XML，返回该 story 中的所有段落。
    """
    paragraphs = []
    
    pattern = r'(<ParagraphStyleRange[^>]*>.*?</ParagraphStyleRange>)'
    for para_idx, match in enumerate(re.finditer(pattern, story_xml, re.DOTALL)):
        psr_xml = match.group(1)
        chars = _parse_paragraph_style_range(psr_xml, story_idx, para_idx)
        paragraphs.append({'chars': chars, 'raw_xml': psr_xml})
    
    return paragraphs


def _parse_paragraph_style_range(psr_xml, story_idx, para_idx):
    """
    从 ParagraphStyleRange XML 中提取所有字符记录。
    每个记录标记其所属的 story 和 paragraph，用于后续按段落重建。
    """
    chars = []
    
    csr_pattern = r'<CharacterStyleRange([^>]*?)(?:>(.*?)</CharacterStyleRange>|/>)'
    
    for match in re.finditer(csr_pattern, psr_xml, re.DOTALL):
        attrs_str = match.group(1)
        inner = match.group(2) if match.group(2) else ''
        
        is_punct = 'CharacterStyle/句号' in attrs_str or 'CharacterStyle/句号' in inner
        
        content_match = re.search(r'<Content>(.*?)</Content>', inner, re.DOTALL)
        if content_match:
            content_text = content_match.group(1)
        else:
            continue
        
        # 特殊加工指令（如 <?ACE 18?>）
        if re.match(r'<\?ACE\s', content_text):
            chars.append({
                'char': content_text,
                'is_punct': False,
                'is_special': True,
                'style': None,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
            continue
        
        # 生成样式模板
        if content_match:
            style_template = (
                match.group(0)[:content_match.start()] + 
                '{content}' + 
                match.group(0)[content_match.end():]
            )
        else:
            style_template = match.group(0)
        
        for ch in content_text:
            chars.append({
                'char': ch,
                'is_punct': is_punct,
                'is_special': False,
                'style': style_template,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
    
    return chars


def _get_story_header(story_xml):
    """提取 Story XML 从开头到第一个 ParagraphStyleRange 之前的内容"""
    match = re.search(r'<ParagraphStyleRange', story_xml)
    if match:
        return story_xml[:match.start()]
    return story_xml


def _get_story_footer(story_xml):
    """提取 Story XML 最后一个 ParagraphStyleRange 之后的内容"""
    match = None
    for m in re.finditer(r'</ParagraphStyleRange>', story_xml):
        match = m
    if match:
        return story_xml[match.end():]
    return ''
```

- [ ] **Step 2: 单元测试 — 用 275 号 IDML 验证提取**

```bash
python -c "
from inject import extract_from_idml
stories = extract_from_idml('275导出.idml')
total_chars = 0
total_punct = 0
for s in stories:
    for p in s['paragraphs']:
        for c in p['chars']:
            total_chars += 1
            if c['is_punct']:
                total_punct += 1
print(f'总字符记录数: {total_chars}')
print(f'其中旧标点数: {total_punct}')
# 预期: 总字符数 ≈ 6736（含标点原文字数）
"
```

Expected: 输出总字符数和旧标点数，数字合理（接近设计文档中的统计）。

---

### Task 3: 从句读结果提取字符

**Files:**
- Modify: `inject.py`

**Produces:** `extract_from_result()` 函数

- [ ] **Step 1: 实现 extract_from_result()**

```python
def extract_from_result(md_path):
    """
    从句读结果 MD 文件提取字符序列。
    - 跳过文件头注释（从第一个 --- 之后开始）
    - 忽略所有换行、空格等空白字符
    - 仅提取可见字符（含「。」）
    
    返回: 字符列表，如 ['如', '是', '我', '聞', '。', '一', '時', '。', ...]
    """
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 跳过文件头（# 标题 到 第一个 --- 之间的内容）
    # 找到第一个 --- 分隔线后的内容
    parts = content.split('---', 1)
    if len(parts) > 1:
        body = parts[1]
    else:
        body = content
    
    # 提取所有非空白字符
    chars = []
    for ch in body:
        if not ch.isspace():
            chars.append(ch)
    
    return chars
```

- [ ] **Step 2: 测试提取**

```bash
python -c "
from inject import extract_from_result
chars = extract_from_result('275从ID中导出文字_WD句读结果.md')
total = len(chars)
periods = sum(1 for c in chars if c == '。')
print(f'总字符数: {total}')
print(f'句号数: {periods}')
print(f'净文字数: {total - periods}')
# 预期: 净文字数 = 5690（清除标点后的原文字数）
"
```

Expected: 净文字数 = 5690（与结果文件头部标注一致）

---

### Task 4: 验证与对齐

**Files:**
- Modify: `inject.py`

**Produces:** `validate_and_align()` 函数

- [ ] **Step 1: 实现 validate_and_align()**

```python
def validate_and_align(stories, result_chars):
    """
    验证 IDML 净文字与句读结果净文字一致，然后执行字符级对齐。
    
    核心逻辑：
    - IDML 的每个非标点字符在句读结果中必有对应
    - 句读结果中新增的「。」插入在对应位置，归属上一字符的段落
    - 对齐后的每个 new_record 都标记了所属的 (story_idx, para_idx)
    
    返回: new_stories，结构为 {story_idx: {para_idx: [records]}}
    """
    # 扁平化所有 IDML 字符记录
    all_idml_records = []
    for story in stories:
        for para in story['paragraphs']:
            for rec in para['chars']:
                all_idml_records.append(rec)
    
    # 提取 IDML 净文字（跳过旧标点和特殊标记）
    idml_clean_indices = []
    for i, rec in enumerate(all_idml_records):
        if not rec['is_punct'] and not rec.get('is_special', False):
            idml_clean_indices.append(i)
    
    idml_clean_chars = [all_idml_records[i]['char'] for i in idml_clean_indices]
    result_clean_chars = [c for c in result_chars if c != '。']
    
    # 验证
    idml_clean_str = ''.join(idml_clean_chars)
    result_clean_str = ''.join(result_clean_chars)
    
    if idml_clean_str != result_clean_str:
        # 找到第一个差异位置
        for i, (a, b) in enumerate(zip(idml_clean_str, result_clean_str)):
            if a != b:
                ctx = max(0, i - 20)
                raise ValueError(
                    f"字数验证失败！\n"
                    f"IDML 净文字数: {len(idml_clean_str)}\n"
                    f"句读结果净文字数: {len(result_clean_str)}\n"
                    f"第一个差异在位置 {i}:\n"
                    f"  IDML: ...{idml_clean_str[ctx:i+20]}...\n"
                    f"  结果: ...{result_clean_str[ctx:i+20]}...\n"
                    f"  IDML 字符: '{a}' (U+{ord(a):04X})\n"
                    f"  结果字符: '{b}' (U+{ord(b):04X})"
                )
        raise ValueError(
            f"字数验证失败！IDML: {len(idml_clean_str)} 字, 结果: {len(result_clean_str)} 字"
        )
    
    print(f"验证通过: {len(idml_clean_str)} 字一致")
    
    # 对齐: 遍历句读结果，每个字符映射到对应的段落
    clean_idx = 0          # 在 idml_clean_indices 中的位置
    last_para = None       # 上一个字符的 (story_idx, para_idx)
    new_records = []
    punct_style = _find_punct_style(all_idml_records)
    
    for ch in result_chars:
        if ch == '。':
            # 新增句号：归属到上一个字符的段落
            story_idx, para_idx = last_para if last_para else (0, 0)
            new_records.append({
                'char': '。',
                'is_punct': True,
                'is_special': False,
                'style': punct_style,
                'story_idx': story_idx,
                'para_idx': para_idx,
            })
        else:
            # 普通文字：映射到对应 IDML 字符的样式和段落
            target_idx = idml_clean_indices[clean_idx]
            orig_rec = all_idml_records[target_idx]
            
            new_records.append({
                'char': ch,
                'is_punct': False,
                'is_special': False,
                'style': orig_rec['style'],
                'story_idx': orig_rec['story_idx'],
                'para_idx': orig_rec['para_idx'],
            })
            
            last_para = (orig_rec['story_idx'], orig_rec['para_idx'])
            clean_idx += 1
    
    # 按 (story_idx, para_idx) 分组
    grouped = {}  # {story_idx: {para_idx: [records]}}
    for rec in new_records:
        si = rec['story_idx']
        pi = rec['para_idx']
        if si not in grouped:
            grouped[si] = {}
        if pi not in grouped[si]:
            grouped[si][pi] = []
        grouped[si][pi].append(rec)
    
    punct_count = sum(1 for r in new_records if r['is_punct'])
    print(f"对齐完成: {len(new_records)} 个字符（含 {punct_count} 个句号）")
    
    return grouped


def _find_punct_style(all_records):
    """查找 IDML 中已有的句号样式模板"""
    for rec in all_records:
        if rec['is_punct'] and rec.get('style'):
            return rec['style']
    # 如果找不到，返回一个基础句号样式
    return None
```

- [ ] **Step 2: 测试验证逻辑 — 故意制造不匹配**

```bash
python -c "
from inject import extract_from_idml, extract_from_result, validate_and_align

stories = extract_from_idml('275导出.idml')
result_chars = extract_from_result('275从ID中导出文字_WD句读结果.md')

# 应该通过验证
grouped = validate_and_align(stories, result_chars)
total = sum(len(recs) for si in grouped for pi, recs in grouped[si].items())
print(f'275 验证通过，{total} 个字符记录')

# 测试错误检测: 修改 result_chars
bad_chars = result_chars[:10] + ['X'] + result_chars[11:]
try:
    validate_and_align(stories, bad_chars)
    print('ERROR: should have raised')
except ValueError as e:
    print(f'正确捕获错误: {str(e)[:80]}...')
"
```

Expected: 275 验证通过 + 错误被正确捕获

---

### Task 5: 生成输出 IDML

**Files:**
- Modify: `inject.py`

**Produces:** `generate_idml()` 函数

- [ ] **Step 1: 实现 generate_idml()**

```python
def generate_idml(idml_path, stories, grouped_records, output_path):
    """
    将新字符记录写回 IDML。
    grouped_records[story_idx][para_idx] = 该段落的新字符记录列表
    """
    shutil.copy2(idml_path, output_path)
    
    new_story_xmls = {}
    
    for story_idx, story in enumerate(stories):
        story_xml_parts = []
        for para_idx, para in enumerate(story['paragraphs']):
            para_records = grouped_records.get(story_idx, {}).get(para_idx, [])
            
            if para_records:
                new_psr_xml = _rebuild_paragraph_xml(para['raw_xml'], para_records)
            else:
                new_psr_xml = para['raw_xml']
            
            story_xml_parts.append(new_psr_xml)
        
        new_story_xmls[story['name']] = _rebuild_story_xml(
            story['xml_header'],
            story_xml_parts,
            story['xml_footer'],
        )
    
    _write_stories_to_idml(output_path, new_story_xmls)


def _rebuild_paragraph_xml(original_psr_xml, new_char_records):
    """
    用新的字符记录重建 ParagraphStyleRange 的 XML。
    连续的相同样式合并为一个 CharacterStyleRange。
    """
    if not new_char_records:
        return original_psr_xml
    
    # 提取 ParagraphStyleRange 的开始标签和结束标签
    # 找到第一个 CharacterStyleRange 之前和之后的部分
    first_csr = re.search(r'<CharacterStyleRange', original_psr_xml)
    
    if not first_csr:
        return original_psr_xml
    
    # PSR 的前缀（包括 <ParagraphStyleRange ...> <Properties> ... 等）
    prefix = original_psr_xml[:first_csr.start()]
    
    # PSR 的后缀
    last_csr_end = original_psr_xml.rfind('</CharacterStyleRange>')
    if last_csr_end >= 0:
        suffix_start = original_psr_xml.find('>', last_csr_end) + 1
        suffix = original_psr_xml[suffix_start:]
    else:
        suffix = '\n</ParagraphStyleRange>'
    
    # 生成新的 CharacterStyleRange 元素
    # 合并连续相同样式的字符
    csr_elements = []
    i = 0
    while i < len(new_char_records):
        rec = new_char_records[i]
        
        if rec.get('is_special', False):
            # 特殊标记，原样保留
            csr_elements.append(rec['char'])
            i += 1
            continue
        
        # 收集连续相同样式的字符
        chars_in_group = [rec['char']]
        j = i + 1
        while j < len(new_char_records):
            next_rec = new_char_records[j]
            if (next_rec.get('is_special', False) or 
                next_rec.get('style') != rec.get('style') or
                next_rec.get('is_punct') != rec.get('is_punct')):
                break
            chars_in_group.append(next_rec['char'])
            j += 1
        
        group_text = ''.join(chars_in_group)
        
        if rec.get('style'):
            # 使用样式模板生成 XML
            csr_xml = rec['style'].replace('{content}', _xml_escape(group_text))
            csr_elements.append(csr_xml)
        
        i = j
    
    return prefix + '\n'.join(csr_elements) + suffix


def _rebuild_story_xml(header, para_xmls, footer):
    """用重建的段落 XML 拼接完整的 Story XML"""
    return header + '\n'.join(para_xmls) + footer


def _write_stories_to_idml(idml_path, new_story_xmls):
    """将修改后的 Story XML 写回 IDML ZIP"""
    # 读取原始 ZIP
    with zipfile.ZipFile(idml_path, 'r') as zf:
        all_files = {}
        for name in zf.namelist():
            all_files[name] = zf.read(name)
    
    # 替换 Story XML
    for story_name, new_xml in new_story_xmls.items():
        story_path = f'Stories/{story_name}.xml'
        all_files[story_path] = new_xml.encode('utf-8')
    
    # 写回
    with zipfile.ZipFile(idml_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in all_files.items():
            zf.writestr(name, data)


def _xml_escape(text):
    """转义 XML 特殊字符"""
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')
    return text
```

- [ ] **Step 2: 更新 process() 函数串联完整流程**

```python
def process(idml_path, result_path, output_path):
    """主处理流程"""
    print("=" * 60)
    print("IDML 句读结果回注工具")
    print("=" * 60)
    
    # Step 1: 从 IDML 提取
    print("\n[1/4] 解析 IDML...")
    stories = extract_from_idml(idml_path)
    total_chars = sum(
        len(p['chars']) for s in stories for p in s['paragraphs']
    )
    print(f"  提取 {len(stories)} 个 Story, {total_chars} 个字符记录")
    
    # Step 2: 从句读结果提取
    print("\n[2/4] 读取句读结果...")
    result_chars = extract_from_result(result_path)
    punct_count = sum(1 for c in result_chars if c == '。')
    print(f"  提取 {len(result_chars)} 个字符（含 {punct_count} 个句号）")
    
    # Step 3: 验证并对齐
    print("\n[3/4] 验证并对齐...")
    grouped_records = validate_and_align(stories, result_chars)
    
    # Step 4: 生成输出
    print("\n[4/4] 生成输出 IDML...")
    generate_idml(idml_path, stories, grouped_records, output_path)
    
    print(f"\n{'=' * 60}")
    print(f"完成！输出文件: {output_path}")
    print(f"{'=' * 60}")
```

---

### Task 6: 用 275 号测试完整流程

**Files:**
- Modify: `inject.py`

- [ ] **Step 1: 运行完整流程**

```bash
python inject.py --idml "275导出.idml" --result "275从ID中导出文字_WD句读结果.md"
```

Expected: 生成 `275导出_WD注入.idml`，输出中显示验证通过

- [ ] **Step 2: 反向验证 — 解压输出 IDML 比对文字内容**

```bash
python -c "
from inject import extract_from_idml, extract_from_result

# 从输出 IDML 提取纯文字（去掉标点）
stories = extract_from_idml('275导出_WD注入.idml')
output_chars = []
for s in stories:
    for p in s['paragraphs']:
        for c in p['chars']:
            output_chars.append(c['char'])
output_text = ''.join(output_chars)

# 从句读结果提取
result_chars = extract_from_result('275从ID中导出文字_WD句读结果.md')
result_text = ''.join(result_chars)

print(f'输出 IDML 字符数: {len(output_text)}')
print(f'句读结果字符数: {len(result_text)}')
print(f'一致: {output_text == result_text}')

if output_text != result_text:
    for i, (a, b) in enumerate(zip(output_text, result_text)):
        if a != b:
            print(f'第一个差异在位置 {i}: output={a!r}, expected={b!r}')
            break
"
```

Expected: 输出一致。

- [ ] **Step 3: 段落实体验证 — 确认 ParagraphStyleRange 数量不变**

```bash
python -c "
import zipfile, re

def count_psr(idml_path):
    with zipfile.ZipFile(idml_path, 'r') as zf:
        count = 0
        for name in zf.namelist():
            if name.startswith('Stories/Story_'):
                xml = zf.read(name).decode('utf-8')
                count += len(re.findall(r'<ParagraphStyleRange[^>]*>', xml))
        return count

orig = count_psr('275导出.idml')
new = count_psr('275导出_WD注入.idml')
print(f'原始 IDML 段落数: {orig}')
print(f'输出 IDML 段落数: {new}')
print(f'一致: {orig == new}')
"
```

Expected: 段落数一致。

---

### Task 7: 修复与调试

**Files:**
- Modify: `inject.py`

这一步预留：在 Task 6 测试中发现的任何问题进行修复。常见可能问题：

1. **特殊字符（`<?ACE?>`）处理不正确** → 调整 `_parse_paragraph_style_range` 中的正则
2. **样式模板中包含 `{content}` 也匹配了 XML 属性中的花括号** → 仅替换 Content 元素内的文本
3. **Story 顺序与预期不符** → 检查 designmap.xml 解析逻辑
4. **段落重建后 XML 格式问题** → 调整缩进和换行

---

### Task 8: 用 461 号交叉验证

**Files:**
- Modify: `inject.py`

- [ ] **Step 1: 运行 461 号处理**

```bash
python inject.py --idml "461导出.idml" --result "461从ID中导出文字_WD句读结果.md" --output "461导出_WD注入.idml"
```

Expected: 验证通过，生成 `461导出_WD注入.idml`

- [ ] **Step 2: 反向验证**

```bash
python -c "
from inject import extract_from_idml, extract_from_result
stories = extract_from_idml('461导出_WD注入.idml')
output_chars = []
for s in stories:
    for p in s['paragraphs']:
        for c in p['chars']:
            output_chars.append(c['char'])
output_text = ''.join(output_chars)

result_chars = extract_from_result('461从ID中导出文字_WD句读结果.md')
result_text = ''.join(result_chars)

print(f'461 验证: {output_text == result_text}')
print(f'输出字符数: {len(output_text)}')
print(f'句读结果字符数: {len(result_text)}')
"
```

Expected: 输出一致。

---

### Task 9: 清理临时文件

- [ ] **Step 1: 删除测试产物并清理**

```bash
rm -rf _temp_idml_275 _temp_idml_461
# 根据最终代码质量决定是否保留测试用的注入 IDML
```
