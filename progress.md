# Progress Log: 佛经句读回注 IDML 工具

## 当前状态（2026-07-24）

### 仓库信息

| 项目 | 详情 |
|------|------|
| GitHub | https://github.com/LXQ1230/JidouInject |
| 默认分支 | `main` |
| 当前分支 | `dev` |
| 未推送 | 是（本次会话暂不同步到 GitHub） |

### 本次会话变更（2026-07-24 下午）

1. **恢复 IDML/indd 文件**：30 个文件从 `b8172b8` 恢复到原位置（source/、injected/、done/、backup/）
2. **批量配对规则重写**：从"前缀匹配"改为"按经号匹配"
   - `_extract_number()` — 用正则 `^(\d+)` 提取文件名开头经号
   - `find_pairs()` — 按经号分组 IDML/MD/TXT，同号配对
   - 放宽 IDML 识别：`*导出.idml` → `*.idml`
   - 放宽 MD 识别：不再要求前缀一致
   - 新增 TXT 支持：`*句读结果.txt` 与 `*句读结果.md` 同等对待
   - `archive()` 源文件匹配：`f.startswith()` → `_extract_number() == name`（防 175 误匹配 1750）
3. **旧标点集修正**：`_OLD_PUNCT_CHARS` 中移除校勘标注标记
   - 移除 `〔〕`（龟壳括号）— 大藏经校勘标注（如 `〔云〕` 表校订补充）
   - 移除 `〖〗`（白透镜框括号）— 与 `〔〕` 同属校勘标记
4. **Br 保留规则新增 A3.5**：文字 CSR 之间的空+Br CSR → 保留
   - 解决 `如來妙色身` 前换行被剥离问题（散文体→偈颂体的排版换行）
5. **batch_inject.py 防御修复**：`find_pairs()` 排除 `_WD注入.idml` 文件
   - 防止上一轮注入输出被当作原始 IDML 再次配对
6. **字体+U+3000 句号抑制**：思源宋体/仿宋/楷体后跟 U+3000 时，WD 结果中的 `。` 替换为 `　`
   - 保留偈颂/目录分行分字排版原样
   - `_extract_font_from_csr()` — 从 CSR XML 提取 AppliedFont
   - `_should_suppress_punct()` — 对齐阶段判断是否抑制句号
   - `_verify_output()` — 验证逻辑调整为忽略 unicode_whitespace（保留 U+3000）

### 批量处理配对规则（最新版）

| 维度 | 规则 |
|------|------|
| IDML 文件 | `*.idml`（文件名以经号开头） |
| 句读结果 | `*句读结果.md` 或 `*句读结果.txt`（文件名以经号开头） |
| 配对方式 | 按经号（文件名开头数字）匹配，相同经号即为一对 |
| 多文件冲突 | 同经号多个文件 → 用第一个，打印警告 |
| 缺配对 | 打印警告后跳过 |

### 单文件 vs 批量格式支持

| 格式 | 单文件 `inject.py` | 批量 `batch_inject.py` |
|------|:--:|:--:|
| MD | ✅ | ✅ |
| TXT | ✅ | ✅（刚添加） |
| 开发分支 | `dev` |
| SSH | ED25519，走 443 端口 |

### 目录结构

```
JidouInject/
├── 一键批量处理.bat              ← 根目录快捷启动
├── CLAUDE.md                     ← 项目说明 + 句读规则
├── README.md
├── progress.md                   ← 本文件
├── issues-checklist.md           ← 剩余问题清单（17 项）
├── findings.md                   ← 技术发现与决策
├── task_plan.md                  ← 实现计划
│
├── code/                         # 核心脚本
│   ├── inject.py                 # 单文件注入（1600 行，30 函数）
│   ├── inject.bat                # 单文件拖拽包装器
│   ├── batch_inject.py           # 批量处理（212 行）
│   ├── batch_inject.bat          # 批量一键启动
│   └── test_verify_inject.py     # 回归测试（299 行）
│
├── source/                       # 原始文件（只读，不处理）
│   ├── 175/275/461 的 IDML + MD 源文件
│   ├── 定稿未改动/               # 原始 InDesign 文件
│   └── 导出IDML/                 # 导出的 IDML
│
├── pending/                      # 待处理（放文件到这里）
├── output/                       # 本轮处理结果
├── injected/                     # 所有注入结果汇总（永久保留）
├── done/                         # 已完成归档（按经本分目录）
│
├── backup/                       # 代码版本备份
│   ├── v1.0-2026.07.22/
│   └── v1.1-2026.07.23/
│
└── .gitignore                    # 排除: *.idml, *.indd, __pycache__,
                                  #   output/, pending/, injected/, done/, backup/
```

### 使用方式

| 场景 | 操作 |
|------|------|
| 单文件 | 拖拽 IDML+MD 到 `code/inject.bat`，或 `python -X utf8 code/inject.py --idml ... --result ...` |
| 批量处理 | 文件放入 `pending/`，双击 `一键批量处理.bat` |
| 回归测试 | `python -X utf8 code/test_verify_inject.py` |

> **Windows 注意**: 需加 `-X utf8` 标志或设置 `PYTHONIOENCODING=utf-8`，否则 Unicode 符号会触发 GBK 编码错误。

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

#### 无记录 CSR：A1→A2→A3→A3.5→A4

| 优先级 | 条件 | 处理 |
|--------|------|------|
| **A1** | punct + trailing + 纯空白内容 + 有 Br | **保留 Br**（段落间分隔符） |
| **A2** | text + close-trailing + 原为空 + 有 Br | **保留 Br**（段落尾装饰） |
| **A3** | text + 分割副本 | **剥离 Br + Group** |
| **A3.5** | text + 中间 + 纯空白 + 有 Br | **保留 Br**（文字区域间换行，如偈颂分行） |
| **A4** | 其他所有情况 | **剥离 Br** |

close-trailing 判定：预扫描找到第一个"空+有Br"的 text CSR。

#### 有记录 CSR：B 规则

| 条件 | 处理 |
|------|------|
| 单 Content | 保留 prefix Br + suffix Br |
| 多 Content + 分割副本 | **剥离 Content 间 Br** |
| punct（有新句号） | 追加原 CSR 的 Br |

### 测试结果（2026-07-24 下午）

| 测试 | 275 | 461 | 3093 |
|------|-----|-----|------|
| 原文文字零改动 | ✅ 5684 字 | ✅ 9208 字 | ✅ 5284 字 |
| Group ID 唯一 | ✅ 11 | ✅ 1 | - |
| 分割段落 leading Br | ✅ 0 | ✅ 0（42 段落） | - |
| 关键段落空行 | ✅ 3/3 | — | - |
| 输出自检 | ✅ 6754 字符 | ✅ 10725 字符 | ✅ 6270 字符 |
| Br 统计 | 41→39 | 45→43 | 68→68 |
| 校勘标记保留 | — | — | ✅ `〔云〕` |
| 偈颂分行 Br | — | — | ✅ 中间 Br 保留 |
| 字体U+3000抑制。 | — | — | ✅ 思源宋体/仿宋 |

> 2026-07-24 下午验证：三个测试用例全部通过。新增 A3.5 规则修复偈颂分行 Br；`〔〕``〖〗` 从旧标点集移除；思源宋体/仿宋/楷体后 U+3000 间隔保留原排版。

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

- **2026-07-24**：第二轮项目检查 + 项目清理 + GitHub 推送
  - 项目检查：5/12 旧问题已解决，发现 10 项新问题
  - 立即清理：删除临时文件、完善 `.gitignore`、移除 30 个二进制文件追踪（439 files, -105072 行）
  - 分支管理：`master` → `main`，设 `main` 为默认分支
  - GitHub：配置 SSH（ED25519, 443 端口），推送 `dev` + `main`
  - 剩余问题清单保存至 `issues-checklist.md`（17 项）
- **2026-07-23**：段落分割 + Br/Group 规则（A1-A4/B）+ 目录重组 + 批量处理 + 冲突检测
- **2026-07-22**：代码审查修复 + 全面测试 + 健壮性增强
- **2026-07-21**：项目初始化 + 5 核心函数 + 流水线建立
