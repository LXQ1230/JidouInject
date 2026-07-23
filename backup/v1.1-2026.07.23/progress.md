# Progress Log: 佛经句读回注 IDML 工具

## 当前状态（2026-07-23 最终版）

### 目录结构

```
佛经句读回注IDML工具/
├── 一键批量处理.bat              ← 根目录快捷启动
├── CLAUDE.md
├── progress.md
│
├── code/                         # 脚本
│   ├── inject.py                 # 单文件注入
│   ├── inject.bat                # 单文件拖拽
│   ├── batch_inject.py           # 批量处理
│   ├── batch_inject.bat          # 批量一键启动
│   └── test_verify_inject.py     # 回归测试
│
├── source/                       # 原始文件（只读，不处理）
│   ├── 275/461/175 的 IDML + MD 源文件
│   ├── 定稿未改动/               # 原始 InDesign 文件
│   └── 导出IDML/                 # 导出的 IDML
│
├── pending/                      # 待处理（放文件到这里）
├── output/                       # 本轮处理结果
├── injected/                     # 所有注入结果汇总（永久保留）
├── done/                         # 已完成归档（按经本分目录）
│   ├── 275/
│   ├── 461/
│   └── 175/
│
└── backup/                       # 代码版本备份
    ├── v1.0-2026.07.22/
    └── v1.1-2026.07.23/
```

### 使用方式

| 场景 | 操作 |
|------|------|
| 单文件 | 拖拽 IDML+MD 到 `code/inject.bat`，或 `python code/inject.py --idml ... --result ...` |
| 批量处理 | 文件放入 `pending/`，双击 `一键批量处理.bat` |
| 回归测试 | `python code/test_verify_inject.py` |

### 功能完整性

| 功能 | 状态 | 说明 |
|------|------|------|
| IDML 解析 + 自检 | ✅ | 解析器与原始 XML 正则提取交叉验证 |
| 句读结果读取 + 段落边界检测 | ✅ | 空行→段落分割边界 |
| 逐字验证 + 字符级对齐 | ✅ | 忽略比对空白（含 U+3000） |
| 段落分割 | ✅ | WD 结果空行触发原始段落拆分 |
| XML 重建 + IDML 写回 | ✅ | CSR 拆分/合并，句号模板注入 |
| 六层输出验证 | ✅ | 结构→Br→字符，失败自动删除输出 |
| 批量处理 | ✅ | 自动配对 pending/ 中文件，逐对处理+归档 |
| 同名文件冲突检测 | ✅ | 处理前扫描，支持覆盖/跳过/重命名/逐个确认 |
| 通用化 | ✅ | 无硬编码 Story 名，扫描所有 Story 验证 |

### Br/Group 规则（最终版）

#### 无记录 CSR：A1→A2→A3→A4

| 优先级 | 条件 | 处理 |
|--------|------|------|
| **A1** | punct + trailing + 纯空白内容 + 有 Br | **保留 Br**（段落间分隔符） |
| **A2** | text + close-trailing + 原为空 + 有 Br | **保留 Br**（段落尾装饰） |
| **A3** | text + 分割副本 | **剥离 Br + Group** |
| **A4** | 其他所有情况 | **剥离 Br** |

close-trailing 判定：预扫描找到第一个"空+有Br"的 text CSR。

#### 有记录 CSR：B 规则

| 条件 | 处理 |
|------|------|
| 单 Content | 保留 prefix Br + suffix Br |
| 多 Content + 分割副本 | **剥离 Content 间 Br** |
| punct（有新句号） | 追加原 CSR 的 Br |

### 测试结果

| 测试 | 275 | 461 |
|------|-----|-----|
| 原文文字零改动 | ✅ 5684 | ✅ 9208 |
| Group ID 唯一 | ✅ 11 | ✅ 1 |
| 分割段落 leading Br | ✅ 0 | ✅ 0 |
| 关键段落空行 | ✅ 3/3 | — |
| 输出自检 | ✅ 6748 | ✅ 10725 |
| Br 统计 | 41→39 | 45→43 |

### 已知局限

1. **首字 prefix Br**：分割副本段首 prefix Br 无法区分"段间分隔"与"段内格式"，全部保留
2. **多 Content Br 剥离**：所有分割副本的多 Content CSR 的 Br 被剥离，正文内多 Content+Br 可能被误伤（当前数据未触发）
3. **活跃 CSR Group**：分割副本活跃区 Group 未剥离，极端情况下可能 ID 重复（未触发）

### 错误日志（完整，按时间倒序）

| 时间 | 错误 | 根因 | 修复 |
|------|------|------|------|
| 07-23 | C 规则全局剥离 prefix Br | 无法区分段间/段内语义 | 回退 C 规则 |
| 07-23 | "闻如\<Br/\>是。" 换行 | 多Content Br 在分割副本中保留 | B 规则：剥离 |
| 07-23 | 461 多余空行（红色句号） | punct trailing Br 无条件保留 | A1: ws 检查过滤旧标点 |
| 07-23 | close-trailing 固定 +3 窗口 | 尾饰前有多个无记录 CSR | 预扫描替代 |
| 07-23 | CSR 拆分 Group 重复 | clean_prefix 未剥离 Group | 非首部分剥离 Group |
| 07-23 | "胗言。"→"謨婆伽" 丢字 | 原段 leading Group 被无差别清除 | A3 仅分割副本 strip_groups |
| 07-23 | Para[4]→Para[5] 空行丢失 | 装饰空 CSR Br 被剥离 | A2: close-trailing KEEP |
| 07-23 | Para[7] 段首隐形字符 | 分割副本 Group ID 重复 | A3: strip_groups |
| 07-23 | Para[6]→Para[7] 缺空行 | CSR[29] Br 被全剥离 | A1: trailing punct ws KEEP |
| 07-23 | 分割段落顺序错误 | 追加到末尾 | position source+0.5 |
| 07-23 | 分割后字符重复 | 无记录 CSR 保留原文 | _clear_content_keep_br |
| 07-23 | 分割段落索引冲突 | 新 para_idx 与原有冲突 | max_orig+1 全局唯一 |
| 07-23 | 分割段落用错模板 | 直接用最后一段 | split_sources 映射 |
| 07-23 | WD结果空行被忽略 | extract_from_result 过滤换行 | 逐行解析 + 空行检测 |

### 历史会话

- **2026-07-23**：段落分割 + Br/Group 规则（A1-A4/B）+ 目录重组 + 批量处理 + 冲突检测
- **2026-07-22**：代码审查修复 + 全面测试 + 健壮性增强
- **2026-07-21**：项目初始化 + 5 核心函数 + 流水线建立
