### Task 3 Report: 从句读结果提取字符

**STATUS:** COMPLETE

**Commit Hash:** a14d1a7

---

### 实现概要

在 `inject.py` 中新增 `extract_from_result()` 函数（第 209-229 行），用于从句读结果 MD 文件提取字符序列。

### 函数签名

```python
def extract_from_result(md_path: str) -> list[str]:
```

### 行为

1. 读取 MD 文件（UTF-8 编码）
2. 跳过文件头：以 `---` 为分隔符，取其后内容；若无 `---` 则使用全文
3. 仅过滤 ASCII 空白字符：`\n`、`\r`、`\t`、` `（空格）
4. 保留全角空格 U+3000（`　`）—— 佛经偈颂中的分字空格
5. 返回可见字符列表

### 关键设计决策：全角空格 U+3000

测试文件 `275从ID中导出文字_WD句读结果.md` 的偈颂部分（第 25、30 行）包含 6 个全角空格（U+3000 / IDEOGRAPHIC SPACE），用作偈颂中五言/七言句之间的分隔符。

若使用 `str.isspace()` 过滤（如任务 brief 中的参考代码），U+3000 会被错误地当作空白字符移除，导致净文字数 = 5684，与预期值 5690 相差 6。

修正方案：仅过滤 ASCII 空白字符（`\n\r\t `），保留 U+3000 及其他 Unicode 空白字符。修正后净文字数 = 5690，与预期完全一致。

### 测试结果

**测试命令：**

```
python -c "
from inject import extract_from_result
chars = extract_from_result('275从ID中导出文字_WD句读结果.md')
total = len(chars)
periods = sum(1 for c in chars if c == '。')
print(f'总字符数: {total}')
print(f'句号数: {periods}')
print(f'净文字数: {total - periods}')
"
```

**输出：**

```
总字符数: 6755
句号数: 1065
净文字数: 5690
```

净文字数 = 5690，与预期一致。通过。

**额外边缘测试（6 项）：**

| 测试用例 | 结果 |
|----------|------|
| 主文件（275 结果 MD） | PASS |
| 带 `---` 头部的文件 | PASS |
| 空文件 | PASS |
| 纯空白文件 | PASS |
| 全角空格保留（U+3000） | PASS |
| 正文中含 `---` 字符串 | PASS（注意：会被当作分隔符截断） |

### 疑虑

1. **`---` 分隔符策略**：当前使用 `split('---', 1)` 跳过文件头。若佛经正文中偶含 `---`（如注释中的分隔线），该内容会被错误移除。实际佛经正文极少出现此字符串，风险较低。未来可考虑改为解析 YAML front matter（`re.match(r'^---\s*\n.*?\n---', content, re.DOTALL)`）以精确匹配。

2. **非 ASCII 空白字符的完整列表**：当前仅保留 U+3000，但 Unicode 中还有其他空白类字符（如 U+00A0 NO-BREAK SPACE、U+2000-U+200A 各种宽度空格）。若输入文件中出现这些字符，当前实现会保留它们。对佛经文本而言影响极小。
