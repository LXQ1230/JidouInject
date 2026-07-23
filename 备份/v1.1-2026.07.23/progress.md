# Progress Log: IDML 句读回注工具

## 当前状态（2026-07-23 最终版）

### 功能完整性

| 功能 | 状态 | 说明 |
|------|------|------|
| IDML 解析 + 自检 | ✓ | 解析器与原始 XML 正则提取交叉验证 |
| 句读结果读取 + 段落边界检测 | ✓ | 空行→段落分割边界 |
| 逐字验证 + 字符级对齐 | ✓ | 忽略比对空白（含 U+3000），5684/9208 字一致 |
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
     │         ├─ leading/trailing 区分   min_text_idx / max_text_idx
     │         ├─ 文字 CSR 拆分/重建      csr_prefix/suffix 处理
     │         ├─ 句号 CSR 注入           punct_template + Br 追加
     │         └─ 清除逻辑
     │             ├─ _clear_content_keep_br()    trailing punct (保留 Br)
     │             └─ _clear_content_strip_br()   leading + trailing text (剥离 Br)
     └─ [5] 多层验证
         ├─ _verify_structure()           Group ID 唯一、Br 范围、段落数
         ├─ _verify_br_count()            Br 统计报告
         └─ _verify_output()             重新提取 → 逐字比对 → 失败删文件
```

### 关键辅助函数

| 函数 | 参数 | 用途 |
|------|------|------|
| `_clear_content_keep_br(csr_xml, strip_groups=False)` | strip_groups | trailing 清除：保留 Br，可选清除 Group |
| `_clear_content_strip_br(csr_xml, strip_groups=False)` | strip_groups | leading 清除：剥离 Br，可选清除 Group |
| `_rebuild_paragraph_xml(xml, records, tmpl, is_split_copy=False)` | is_split_copy | 段落重建：副本清除 Group |

### 段落分割规则

| CSR 位置 | CSR 类型 | Br 处理 | Group 处理 |
|----------|---------|---------|-----------|
| leading（< min_text_idx） | 全部 | 剥离 | 副本剥离，原段保留 |
| mid（min~max） | 全部 | 保留 | 保留 |
| trailing（> max_text_idx） | PUNCT | **保留**（分隔符） | 副本剥离，原段保留 |
| trailing（> max_text_idx） | TEXT（原有内容） | 剥离 | 副本剥离，原段保留 |
| trailing（> max_text_idx） | TEXT（原为空） | **保留**（装饰性） | 副本剥离，原段保留 |

### 最终 275 段落结构

```
Para[0]: [5297c] 如是我聞一時。佛在舎衞國...而說偈言。
Para[1]: [23c]   若以色見我　以音聲求我　是人行邪道　不能見如来
Para[2]: [702c]  湏菩提。汝若作是念...如如不動。何以故。
Para[3]: [23c]   一切有為法　如夢幻泡影　如露亦如電　應作如是觀
Para[4]: [54c]   佛說是經巳...皆大歡喜。信受奉行。     [trailing=1Br]
Para[5]: [12c]   金剛般若波羅蜜經。胗言。             [leading=1Br]
Para[6]: [41c]   謨婆伽拔帝。喇壤。...莎婆訶。         [trailing=2Br]
Para[7]: [592c]  御製金剛般若波羅蜜經序。據永樂...    [leading=0Br, 0Groups]
Para[8]: [10c]   永樂九年五月初一日。
```

空行关系：
- Para[4]→Para[5]：Para[4] trailing Br + Para[5] leading Br → 1 空行
- Para[6]→Para[7]：Para[6] 2 trailing Br → 1 空行，Para[7] 段首干净

### 测试结果

| 测试 | 验证项 | 275 | 461 |
|------|--------|-----|-----|
| L1 解析自检 | 字符遗漏 | ✓ | ✓ |
| L2 对齐验证 | 字数一致 | 5684 | 9208 |
| L3 结构完整性 | Group ID 唯一 | 11 唯一 | 1 唯一 |
| L3 结构完整性 | 段落数一致 | ✓ | ✓ |
| L3 结构完整性 | 分割段落 leading Br | 0 | 0 |
| L4 Br 统计 | 输入→输出 | 40→38 | 44→55 |
| L5 输出自检 | 逐字一致 | 6748 | 10725 |
| test_verify | 外部测试 5 项 | ✓ | ✓ |

### 文件清单

| 文件 | 用途 |
|------|------|
| `inject.py` | 主工具（含六层验证） |
| `inject.bat` | Windows 拖拽包装器 |
| `test_verify_inject.py` | 自动化回归测试（275+461） |
| `275导出_WD注入.idml` | 275 输出文件 |
| `progress.md` | 本文件 |

---

## 错误日志（完整）

| 时间 | 错误 | 根因 | 修复 |
|------|------|------|------|
| 07-23 | Para[6]→Para[7] 缺少空行 | CSR[29] Br 被 `_clear_content_keep_br` 全剥离 | trailing punct 保留 Br |
| 07-23 | Para[7] 段首隐形字符 | 分割副本 Group ID 重复 | `is_split_copy` → `strip_groups=True` |
| 07-23 | Para[4]→Para[5] 空行丢失 | 装饰性空 CSR Br 被剥离 | `orig_had_content` 检查保留装饰 Br |
| 07-23 | "胗言。"→"謨婆伽" 丢失字 | 原始 Para[6] leading Group 被无差别清除 | `is_split_copy=False` 保留原始 Group |
| 07-23 | CSR 拆分 Group 重复 | `clean_prefix` 未剥离 Group | 拆分时对非首部分剥离 Group |
| 07-23 | WD结果空行被忽略 | extract_from_result 过滤换行 | 逐行解析 + 空行检测 |
| 07-23 | 分割段落用错模板 | 直接用最后一段 | split_sources 映射找源段落 |
| 07-23 | 分割段落索引冲突 | 新 para_idx 与原有冲突 | max_orig+1 全局唯一 |
| 07-23 | 分割后字符重复 | 无记录 CSR 保留原文 | _clear_content_keep_br 清空 |
| 07-23 | 分割段落顺序错误 | 追加到末尾 | position source+0.5 排序 |

---

## 历史会话摘要

### 2026-07-23（本次）
- 段落分割功能：empty line → paragraph split
- Br leading/trailing 区分 + 装饰性 Br 保留
- Group ID 重复修复（is_split_copy + clean_prefix）
- 六层验证体系建立
- 自动化测试套件创建

### 2026-07-22
- 代码审查修复（防御性守卫 + 警告）
- 全面测试（275 全通过，461 数据版本不一致）
- 健壮性增强（文件校验 + 错误信息）
- Task 6-9 完成

### 2026-07-21
- 项目初始化：inject.py 骨架 + 5 核心函数
- 提取→验证→对齐→重建→验证 流水线建立
- Task 1-5 完成
