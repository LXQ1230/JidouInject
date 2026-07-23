# Progress Log: IDML 句读回注工具

## 当前状态（2026-07-23 最终版）

### 功能完整性

| 功能 | 状态 | 说明 |
|------|------|------|
| IDML 解析 + 自检 | ✓ | 解析器与原始 XML 正则提取交叉验证 |
| 句读结果读取 + 段落边界检测 | ✓ | 空行→段落分割边界 |
| 逐字验证 + 字符级对齐 | ✓ | 忽略比对空白（含 U+3000） |
| 段落分割 | ✓ | WD 结果空行触发原始段落拆分 |
| XML 重建 + IDML 写回 | ✓ | CSR 拆分/合并，句号模板注入 |
| 六层输出验证 | ✓ | 结构→Br→字符，任意失败删除输出 |
| 自动化回归测试 | ✓ | test_verify_inject.py 覆盖 275 + 461 |

### inject.py 架构

```
main()
 └─ process()
     ├─ [1] extract_from_idml()          → stories
     │     └─ _verify_extraction()       自检：解析器 vs 正则
     ├─ [2] extract_from_result()         → {chars, para_breaks}
     ├─ [3] validate_and_align()          → {grouped, split_sources}
     │     └─ 逐字比对 + 段落边界触发
     ├─ [4] generate_idml()               → 写入 ZIP
     │     └─ _rebuild_paragraph_xml()    每个段落独立重建
     │         ├─ close-trailing 预扫描   替代固定 +3 窗口
     │         ├─ 无记录 CSR 四层规则     A1→A2→A3→A4
     │         ├─ 有记录 CSR              B: 多Content+分割副本剥离Br
     │         ├─ 文字 CSR 拆分/重建      csr_prefix/suffix 处理
     │         ├─ 句号 CSR 注入           punct_template + Br 追加
     │         └─ 清除函数
     │             ├─ _clear_content_keep_br()   保留 Br
     │             └─ _clear_content_strip_br()  剥离 Br + 可选 Group
     └─ [5] 多层验证
         ├─ _verify_structure()           Group ID 唯一、Br 范围、段落数
         ├─ _verify_br_count()            Br 统计报告（扫描所有 Story）
         └─ _verify_output()             重新提取 → 逐字比对 → 失败删文件
```

### Br/Group 规则（最终版）

#### 无记录 CSR：A1→A2→A3→A4 四层优先级

| 优先级 | 条件 | 处理 |
|--------|------|------|
| **A1** | punct + trailing + 纯空白内容 + 有 Br | **保留 Br**（段落间分隔符） |
| **A2** | text + close-trailing + 原为空 + 有 Br | **保留 Br**（段落尾装饰） |
| **A3** | text + 分割副本 | **剥离 Br + Group** |
| **A4** | 其他所有情况 | **剥离 Br** |

close-trailing 判定：预扫描 max_text_idx 之后，找到第一个"空+有Br"的 text CSR，标记为紧邻；遇到曾有文字内容的 CSR 则停止。

#### 有记录 CSR：B 规则

| 条件 | 处理 |
|------|------|
| 单 Content | 保留 prefix Br + suffix Br |
| 多 Content + 分割副本 | **剥离 Content 间 Br**（节标题格式不适用） |
| 多 Content + 原段落 | 保留 Content 间 Br |
| punct（有新句号） | 追加原 CSR 的 Br |

#### 分割副本 vs 原段落

| 维度 | 原段落 | 分割副本 |
|------|--------|---------|
| Group 元素 | **保留** | A3 清除区剥离，活跃区保留 |
| 尾随 punct 分隔符 | A1 保留 Br | A1 保留 Br（额外 strip_groups） |
| 尾随文本装饰 | A2 保留 Br | A2 保留 Br（额外 strip_groups） |
| 多 Content 间 Br | 保留 | **剥离** |
| 首字 CSR prefix Br | 保留 | 保留（无法区分段间/段内） |

### 275 段落结构（最终）

```
Para[0] [5297c] 22Br trail=1 | 如是我聞一時。佛在舎衞國...
Para[1] [23c]   1Br         | 若以色見我 ...
Para[2] [702c]  4Br  trail=1 | 湏菩提。汝若作是念...
Para[3] [23c]   1Br         | 一切有為法 ...
Para[4] [54c]   1Br  trail=1 | 佛說是經巳。...信受奉行。
                                  ↓ 1空行 (Para[4]trail + Para[5]lead)
Para[5] [12c]   3Br         | 金剛般若波羅蜜經。胗言。
Para[6] [41c]   2Br  trail=1 | 謨婆伽拔帝。...莎婆訶。
                                  ↓ 1空行 (2 Br = 1空行)
Para[7] [592c]  2Br  trail=1 | 御製金剛般若波羅蜜經序。...
                                  ↓ 1空行 (trail装饰Br)
Para[8] [10c]   1Br         | 永樂九年五月初一日。
```

### 461 段落结构（最终）

43 个段落（25 原段 + 42 分割副本 - 1 重叠），Br 45→43。

- 仅 2 段有多 Content Br 被剥离（P[40] "佛說七䖏三觀經"、P[41] "聞如是"）
- 空行问题已解决（红色句号 punct Br 通过 A1 的 ws 检查自动剥离）
- prefix Br（段首换行）保留原样（语义无法自动区分）

### 测试结果

| 测试 | 275 | 461 |
|------|-----|-----|
| 原文文字零改动 | ✓ 5684 | ✓ 9208 |
| Group ID 唯一 | ✓ 11 | ✓ 1 |
| 分割段落 leading Br | ✓ 0 | ✓ 0 |
| 关键段落空行 | ✓ 3/3 | — |
| 输出自检 | ✓ 6748 | ✓ 10725 |
| Br 统计 | 41→39 | 45→43 |

### 文件清单

| 文件 | 用途 |
|------|------|
| `inject.py` | 主工具（含六层验证 + A1-A4/B 规则） |
| `inject.bat` | Windows 拖拽包装器 |
| `test_verify_inject.py` | 自动化回归测试（275+461） |
| `progress.md` | 本文件 |
| `CLAUDE.md` | 项目说明 + 句读规则 |
| `备份/v1.0-2026.07.22/` | 段落分割功能前版本 |
| `备份/v1.1-2026.07.23/` | 当前版本副本 |

### 已知局限

1. **首字 prefix Br**：分割副本的段首 prefix Br 无法自动区分"段间分隔"与"段内格式"，全部保留。461 中少量段首出现多余空行（如 P[10] "佛便說"、P[40] "佛說七䖏三觀經"）。
2. **多 Content Br 剥离**：对所有分割副本的多 Content CSR 剥离 Br。当前数据中仅节标题使用多 Content+Br，安全；若将来出现正文内的多 Content+Br 会被误伤。
3. **活跃 CSR Group**：分割副本活跃内容区的 Group 元素当前保留，若原段同一 Group 也在活跃区，会产生 ID 重复（当前数据未触发）。

### 错误日志（完整）

| 时间 | 错误 | 根因 | 修复 |
|------|------|------|------|
| 07-23 | WD结果空行被忽略 | extract_from_result 过滤换行 | 逐行解析 + 空行检测 |
| 07-23 | 分割段落用错模板 | 直接用最后一段 | split_sources 映射找源段落 |
| 07-23 | 分割段落索引冲突 | 新 para_idx 与原有冲突 | max_orig+1 全局唯一 |
| 07-23 | 分割后字符重复 | 无记录 CSR 保留原文 | _clear_content_keep_br 清空 |
| 07-23 | 分割段落顺序错误 | 追加到末尾 | position source+0.5 排序 |
| 07-23 | Para[6]→Para[7] 缺空行 | CSR[29] Br 被全剥离 | A1: trailing punct ws KeEP |
| 07-23 | Para[7] 段首隐形字符 | 分割副本 Group ID 重复 | A3: is_split_copy strip_groups |
| 07-23 | Para[4]→Para[5] 空行丢失 | 装饰空 CSR Br 被剥离 | A2: close-trailing empty KEEP |
| 07-23 | "胗言。"→"謨婆伽" 丢字 | 原段 leading Group 被清除 | A3 仅分割副本 strip_groups |
| 07-23 | 461 多余空行（红色句号） | punct trailing Br 无条件保留 | A1: ws 检查过滤旧标点 |
| 07-23 | CSR 拆分 Group 重复 | clean_prefix 未剥离 Group | 拆分时对非首部分剥离 Group |
| 07-23 | "聞如\<Br/\>是。" 同行断开 | 多Content Br 在分割副本中保留 | B: 分割副本剥离 Content 间 Br |
| 07-23 | close-trailing 固定 +3 窗口 | 尾饰前有多个无记录 CSR | 预扫描替代固定窗口 |
| 07-23 | prefix Br 全局剥离失败 | 无法区分段间/段内语义 | 回退，保留 prefix Br |

### 历史会话

- **2026-07-23**：段落分割 + Br/Group 规则重构（A1-A4/B）+ close-trailing 预扫描
- **2026-07-22**：代码审查修复 + 全面测试 + 健壮性增强
- **2026-07-21**：项目初始化 + 5 核心函数 + 流水线建立
