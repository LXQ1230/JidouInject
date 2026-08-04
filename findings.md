# Findings & Decisions: IDML 句读回注工具

## 需求
- 将 `_WD句读结果.md` 中的文字和「。」注入回 IDML 文件
- 保留原始 IDML 的所有排版样式（CharacterStyleRange、ParagraphStyleRange 等）
- 仅替换文字内容和新增句号，不改动其他任何 XML 结构
- 输出为有效 IDML（ZIP 格式），可在 InDesign 中正常打开

## 研究发现

### IDML 结构
- IDML 是 ZIP 压缩包，包含多个 XML 文件
- `designmap.xml` 包含 Story 列表和顺序（StoryList 属性）
- `Stories/Story_{name}.xml` 包含实际文字内容
- 文字嵌套在 ParagraphStyleRange → CharacterStyleRange → Content 中
- 段落末尾常有全角空格（U+3000）用于 IDML 布局留白

### 当前实现状态（Task 1-5 完成）
- `extract_from_idml()`: 解析 IDML ZIP，提取所有字符记录含样式模板
- `extract_from_result()`: 从句读结果 MD 提取字符序列
- `validate_and_align()`: 逐字验证 + 字符级对齐，按段落分组
- `generate_idml()`: 用新记录重建 XML，写回 ZIP
- 4 步流水线已验证通过（275 测试用例: 5690 字 + 1065 句号）

### Task Review 遗留问题
1. **MEDIUM**: `_rebuild_paragraph_xml()` 后缀提取中 `find('>', ...)` 返回 -1 时无防护
2. **LOW**: `_find_punct_style()` 返回 None 时静默跳过（无警告）

## 技术决策
| 决策 | 理由 |
|------|------|
| `{content}` 模板替换方案 | 统一提取和写回接口 |
| 连续相同样式合并 | 减少输出 XML 大小（1162 个多字符 CSR） |
| 装饰性 Story 保护（<50 净字跳过） | 避免页眉标题等被误判为正文；阈值已参数化（--min-clean，P2-8） |
| 流式 ZIP 写回（2026-08-04 起） | 未修改成员按原 ZipInfo 流式拷贝，内存 O(最大单个成员)，替代全量内存读取 |
| CharRecord slots dataclass（2026-08-04 起） | 字符记录内存 ~90-120B/条（dict 约 250-300B/条），大经书（497：63 万字符）内存减半 |
| 大经书内存释放（2026-08-04 起） | `generate_idml` 后 `del stories` + `gc.collect()`（P2-10）；497 压测前先跑 `bench_inject.py` |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 重复 process() 定义（已修复） | 删除旧版本（commit d663e93） |
| 特殊标记（ACE 指令）提取时无 style 模板 | 修复提取逻辑，为特殊标记也生成模板 |

## 资源
- `inject.py` — 主工具文件（2026-08-04 起 2100+ 行，含 8 层修复；`idml_utils.py` 旧版死代码已于同日删除，此为唯一实现）
- `batch_inject.py` — 批量处理（配对 + 冲突决策 + 归档）
- `test_verify_inject.py` — 核心回归（275 + 461，主 Story 动态定位）
- `test_zip_stream.py` — ZIP 流式写回 14 项测试
- `test_stress_idml.py` / `bench_inject.py` — 压力/性能测试
- `275导出.idml` + `275从ID中导出文字_WD句读结果.md` — 测试用例 1
- `461导出.idml` + `461从ID中导出文字_WD句读结果.md` — 测试用例 2
- `.superpowers/sdd/` — Task 1-5 简报和审查记录
