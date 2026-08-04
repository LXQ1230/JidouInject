# JidouInject 深度审查报告

- **审查日期**: 2026-08-04
- **审查对象**: 佛经句读回注项目（inject.py / batch_inject.py / idml_utils.py / 测试 / 批处理 / 文档）
- **审查方法**: 全量代码精读 + 文档交叉核对 + 运行时实证（275/461 回归、30MB 压力测试、合成用例、IDML 结构探针）
- **结论统计**: P1 严重 8 项 / P2 中等 10 项 / P3 轻微 9 项 / 已验证防线 6 项

---

## 一、总体评价

**核心引擎（inject.py 注入流水线）质量良好**：三层验证链（提取自检 → 结构验证 → 输出字符验证）实证有效——275/461 回归全通过、30MB 压力测试输出 340,081 字符逐字一致、story 空洞（3093 ub3）与实体编码（0080）两个历史 bug 已正确修复。

**主要问题集中在三处**：
1. **版本管理失效**（git 未提交 v2.0 改造成果 + backup/v2.0 实为旧版）——最新成果无任何版本保护；
2. **batch_inject.py 批量编排逻辑缺陷**（配对过宽、重命名归档丢失、冲突未覆盖、异常中断）；
3. **代码分裂**（idml_utils.py 是带已修复 bug 的旧版死代码，与 inject.py 双份漂移）。

未发现命令注入、路径遍历、XXE 等安全漏洞（无 shell 调用、XML 以正则处理、输入为信任文件）。

---

## 二、P1 严重问题（8 项）

### P1-1 版本管理失效：v2.0 改造成果未提交，backup/v2.0 是旧版
- **位置**: git 仓库 / `backup/v2.0-2026.08.04/inject.py`
- **证据**: `git log` 最新提交为 33fa16a（法藏大宋抑制）；`code/inject.py` 含 CharRecord dataclass、流式写回、槽内插句号、内存统计等 v2.0 新特性，但**均未提交**。`backup/v2.0-2026.08.04/inject.py` MD5(162c71b2a6) ≠ code/inject.py MD5(c54614f6ca)，经 diff 确认 backup/v2.0 是**改造前的旧版**（无 CharRecord/ctypes/time），命名严重误导。
- **影响**: 一旦执行 `git checkout`/`reset --hard`/分支切换，当前最新成果（数小时工作）直接丢失且无法恢复；误信 backup/v2.0 恢复则回退到旧版。`git status` 显示 code/inject.py、code/test_verify_inject.py 有未提交修改，source/、done/ 有删除（175/275 句读结果文件）。
- **建议**: ① 立即 `git add -A && git commit` 保护工作区；② backup 目录重命名语义改为「版本快照 + 日期 + 内容描述」（如 `v2.0-slot-inject-2026.08.04`），删除误导性 v2.0 目录或补正确快照；③ 建立"改完即备份/提交"约定。

### P1-2 batch 配对规则过宽，可能错误配对
- **位置**: `code/batch_inject.py` `find_pairs()`（第 66-73 行）
- **证据**: MD/TXT 识别条件为 `(f.endswith(".md") or f.endswith(".txt")) and "_WD注入" not in f`，不校验"句读结果"字样（progress.md 记录这是 07-31 故意放宽）。实证：根目录 `275导出.txt` 前 5000 字含旧标点 791 个——若被配对会触发字数验证失败（安全拦截，但阻塞流程）；**若句读结果文件恰为无标点文本（如误放导出原文的变体），会"验证通过"并注入一个零句号结果，导致旧标点全清且无新句号**。此外 `275_old_test.idml`（经号 275）会与 `275导出.txt` 竞争配对。
- **影响**: 错误配对 → 流程阻塞或（理论）静默数据损坏。
- **建议**: ① 恢复"句读结果"字样强校验（`"句读结果" in f`），或至少排除 `导出.txt`/`_old_test`/`_test` 模式；② 同经号多文件时要求唯一或人工确认，禁止"取第一个"。

### P1-3 batch 归档：输出重命名后 injected/done 静默丢失
- **位置**: `code/batch_inject.py` `main()` 第 229-231 行 + `archive()` 第 140-141 行
- **证据**: output 冲突选择 `rename_v2` 时 `out_path` 变为 `xxx_v2.idml`，但 `archive()` 用固定名 `{name}导出_WD注入.idml` 查找 → 文件不存在 → 打印警告后 return → **injected/ 与 done/ 归档静默失败，且 pending 源文件也不移动**。用户看到"✓"但实际未归档。
- **建议**: 将实际写入的 out_path 传给 archive()；归档前校验文件存在并报错。

### P1-4 batch 归档冲突未收集 + archive 异常无捕获，可整批崩溃
- **位置**: `collect_conflicts()`（第 99-117 行）只收集输出/injected/done 输出文件，**未收集 pending 源文件的目标路径**；`archive()`（第 158-163 行）用 `decisions.get(dst, 'overwrite')` 默认覆盖
- **证据**: 第二次运行同一经号时，pending 源文件目标在 done/ 已存在 → 默认 overwrite → `shutil.move` 在 Windows 下目标存在时抛 `FileExistsError`（或覆盖旧归档）→ archive 无 try/except → **整个批量中断，后续文件对全部不处理，无汇总输出**。
- **建议**: ① collect_conflicts 纳入源文件目标路径；② archive() 内 try/except，单文件归档失败只记入结果表不中断；③ move 前对目标做存在性决策（skip/rename）。

### P1-5 idml_utils.py 是带已修复 bug 的旧版死代码
- **位置**: `code/idml_utils.py`（1695 行）vs `code/inject.py`（2073 行），MD5 均不同
- **证据**: ① `extract_from_idml()` 用 `enumerate(story_order)` 带空洞 story_idx——正是 inject.py 第 551-553 行注释点名的"stories[story_idx] 越界被静默跳过重建"bug（3093 实证存在 ub3 空洞）；② 无 `slot_pos`/`after_pos`（槽内插句号能力缺失）；③ `_write_stories_to_idml` 全量读 ZIP 到内存（非流式）；④ `last_slot` 为 4 元组。progress.md/findings.md 仍将其描述为"可复用模块"。
- **影响**: 误用会产出旧行为（含空洞 bug）；双份 1600+ 行重复代码必然继续漂移。
- **建议**: 删除 idml_utils.py，或重构为 `from inject import *` 的薄兼容层；更新文档。

### P1-6 正文 Story 内的 ACE 指令（`<?ACE N?>`）可能静默丢失
- **位置**: `inject.py` 对齐循环（is_special 记录不进入 `idml_clean_indices`）→ `_rebuild_paragraph_xml` 第 1069-1070 行（`all_records` 排除 is_special）→ 所在 CSR 走"无记录"分支被 `_clear_content_*` 清空
- **证据**: 275/461/3093/0080 的 `<?ACE 18?>` 均位于装饰性 Story（净字 <50，整段原样输出），**当前样本未触发丢失**；但代码路径上：若正文段落内嵌 ACE 指令 CSR 且同段其他 CSR 有记录 → 该 CSR 被清空，且 `_verify_extraction`（第 646 行）与 `_verify_output`（第 1948 行）双双排除 is_special → **验证链对此类丢失不设防**。inject.py 注释声称"为特殊标记也生成模板"（意图保留），与重建行为矛盾。
- **建议**: ① 重建时对 is_special 记录原样保留其 Content（不参与对齐但保留）；② 输出验证加入 is_special 完整性核对；③ 用 0080 全流程实测正文是否内嵌 ACE。

### P1-7 CSR 拆分复制 Self，依赖数据源格式（换导出器即失效）
- **位置**: `_rebuild_paragraph_xml()` 拆分分支（第 1304-1308 行 `clean_prefix` 仅剥离 Br/Group，不剥离 `Self` 属性）
- **证据**: 合成用例实证：`<CharacterStyleRange Self="c1">` 内含 8 字 + 槽内句号 → 拆分输出 **9 个相同 Self="c1" 的 CSR**；`_verify_structure` 检查 #1 会拦截（安全失败）。当前 275/461/3093/0080 的 CSR 均不带 Self（Self 仅在 Story/Group/Polygon/TextFrame 上）→ 未触发。**但换 InDesign 版本/导出设置后 CSR 带 Self 即 100% 失败**。
- **建议**: 拆分时对非首段前缀做 `Self` 剥离或唯一化（如追加 `_n` 后缀）。

### P1-8 多 Content CSR 空槽 replace 错位（潜在）
- **位置**: `_rebuild_paragraph_xml()` 多 Content 分支第 1278-1280 行 `parts_xml.replace(old_ctag, new_ctag, 1)`
- **证据**: `old_ctag = f'<Content>{orig_contents[oi]}</Content>'`——多个空 Content 的 old_ctag 完全相同（`<Content></Content>`），顺序 replace 会错位匹配。当前样本多 Content CSR 均无空槽（461 的 2 个、0080 的 4 个均无）→ 未触发。
- **建议**: 按 Content 索引定位替换（用 `find` + 位置切片，而非 replace 文本匹配）。

---

## 三、P2 中等问题（10 项）

| # | 位置 | 问题 | 影响 |
|---|------|------|------|
| P2-1 | `code/inject.bat` | 无 `-X utf8`（batch_inject.bat 有）| 进度条 `█`/`─` 在非 UTF-8 控制台/重定向时 UnicodeEncodeError 崩溃 |
| P2-2 | `batch_inject.py find_pairs` | 同经号多文件"取第一个"依赖 `os.listdir` 顺序（非确定性）| 0080.idml 与 0080-ABC.idml 并存时可能选错文件 |
| P2-3 | `inject.py _should_suppress_punct` 规则 A | `_get_prev/_get_next_non_ws_font` 跨 story/段落边界取字体，无 story/para 校验 | 跨 story 边界句号可能被误抑制（静默少句号） |
| P2-4 | `test_verify_inject.py` | 硬编码 `Story_u15de.xml`；`os.remove` 失败被容忍 | 测试只覆盖主 story；清理失败 → 根目录残留 `*_test.idml`（当前已残留 275/461 两个） |
| P2-5 | `inject.py _verify_structure` 检查 #3 | 注释"简化：遍历所有段落"——检查全部段落而非仅分割段落 | 正常段落的装饰性 leading Br 被误报 → 输出被删（假失败） |
| P2-6 | `batch_inject.py archive` | move 覆盖旧归档无备份（第二次运行同经号） | done/ 旧归档被静默覆盖 |
| P2-7 | `inject.py extract_from_result` | `content.split('---', 1)` 遇正文含 `---` 即截断 | 低概率正文截断 → 验证失败（安全但阻塞） |
| P2-8 | `inject.py validate_and_align` | `_MIN_CLEAN_CHARS_PER_STORY = 50` 魔法数字 | 超短正文 Story（<50 净字）被跳过 → 该 Story 无句号且验证可能漏检 |
| P2-9 | 文档 | progress.md 称"六层验证"（实际三层：结构→Br→字符）；findings.md 称 inject.py ~700 行（实际 2073）；README 命令与 inject.bat 不符；目录结构图漏 idml_utils.py/batch_inject.py | 文档误导排查方向 |
| P2-10 | 内存 | 30MB IDML → 峰值 729MB（`_read_story_xmls` 输入输出各全量解压一次 + extract 全量驻留） | 100MB+ 大经书峰值可达数 GB，有 OOM 风险 |

---

## 四、P3 轻微问题（9 项）

1. `CLAUDE.md` 与 `AGENTS.md` 内容完全重复（均 9915 字节）——双份维护必然漂移。
2. `AGENTS.md` 句读规则编号跳号（29 后直接 31，无规则 30）。
3. `_stream_write_idml()` 与 `generate_idml()` 内置流式逻辑重复；`test_zip_stream.py` 测的是 `_stream_write_idml`（生产路径未被该测试直接覆盖）。
4. `_verify_br_count` 的 `br_cleared_text` 可为负值（输出 Br 多于输入-清除），打印误导。
5. `resolve_conflicts()` 的 `input()` 在无 TTY 环境（CI/计划任务）抛 EOFError。
6. `batch_inject.py process_one` 吞异常无 traceback，调试困难。
7. 根目录散落 `0080.txt`/`175导出.txt` 等 5 个未跟踪 txt + 双版本 0080 idml + git 删除的 source 文件——工作区混乱。
8. 进度条 `\r` 重定向到日志文件时产生控制字符垃圾。
9. issues-checklist.md 的 17 项遗留（类型注解、logging、requirements.txt、CI、模块拆分等）多数未办。

---

## 五、实证记录（本次审查执行）

| 验证项 | 结果 |
|--------|------|
| 275 综合回归（test_verify_inject） | ✅ 5684 字零改动、Group ID 唯一、输出验证通过 |
| 461 综合回归（test_verify_inject） | ✅ 9208 字零改动、42 分割段落无 leading Br、10725 字符验证通过 |
| 30MB 压力测试（槽内插句号每 20 字） | ✅ 55.5s、峰值 729MB、输出 340,081 字符逐字一致、文字零改动 322,358 字 |
| story 空洞场景（3093 designmap 25 项缺 ub3） | ✅ inject.py 按实际索引定位（修复生效） |
| ACE 指令现状 | 275/461/3093 各 6 次、0080 各 4 次，均在装饰 Story，当前不丢失 |
| CSR Self 分布 | 275/461/0080 的 CSR 均无 Self（仅 Story/Group/Polygon/TextFrame 有） |
| 多 Content CSR | 461 有 2 个、0080 有 4 个，均无空槽 |
| 根目录 txt 标点含量 | 0080/175/275/461 导出 txt 前 5000 字分别含旧标点 251/614/791/618 个 |
| 合成拆分测试 | ⚠️ CSR 带 Self 时拆分产出 9 个重复 Self（P1-7 依据） |

---

## 六、已验证有效的防线（保留）

1. **三层验证链**：提取自检（正则交叉验证）→ 结构验证（Self 唯一/Br 下限/分割段落 leading Br/段落数）→ 输出字符验证（失败自动删输出）。
2. **流式 ZIP 写回**：保留 mimetype STORED、压缩方式、成员顺序、时间戳（test_zip_stream 实证）。
3. **story_idx 空洞修复**（inject.py 注释 + 3093 实证）。
4. **HTML 实体解码**（0080 `&#xfdc4f;` → U+FDC4F，修复记录于 progress.md）。
5. **原子替换 + 异常清理**（`.tmp` 中间文件，失败自动删除）。
6. **冲突检测交互**（覆盖/跳过/重命名/逐个确认）。

---

## 七、修复路线图（按优先级）

**立即（1 天内）**
1. `git add -A && git commit`——保护 v2.0 改造成果；修正 backup 命名误导。
2. batch_inject：配对加"句读结果"字样校验 + archive 传入实际 out_path + collect_conflicts 纳入源文件 + archive try/except。

**短期（1 周内）**
3. 删除或薄兼容化 idml_utils.py；inject.bat 加 `-X utf8`。
4. ACE 正文保留 + 输出验证加 is_special 核对；CSR 拆分 Self 唯一化；空槽 replace 改为索引定位。
5. `_should_suppress_punct` 规则 A 加 story/para 边界校验。

**中期**
6. 测试去硬编码（按 designmap 定位主 Story）、补 0080 全流程用例、补 InDesign 打开兼容性验证。
7. 文档同步（六层→三层、行数、目录结构、README 命令）。

**长期**
8. issues-checklist 遗留项：模块拆分、logging、CI、pyproject。

---

# 附：第二轮深挖（2026-08-04 15:00-15:20）

在第一轮基础上追加运行时实证（0080 全流程、错误配对、边界输入、497 大经书结构），**发现 1 项 P0 级静默数据错误**，并修正 2 项首轮假设。

## 新增 P0：错误配对静默注入"原文旧标点"（已实证）

- **实证**：`inject.process(source/0080.idml, 0080.txt, ...)` —— 用根目录含 251 个原标点的导出原文 `0080.txt` 当句读结果 → **全流程通过**（"验证通过: 2929 字一致"），输出正文 Story_u336 的 249 个句号全部来自**原文排版标点**（断句如 `是我。一時。佛住南`，处处短断），与正确 AI 句读（247 句号，`一時佛住` 不断）**位置完全不同**，验证链完全放行。
- **根因链**：`extract_from_result()` 只过滤 tab/空格，**保留所有旧标点**；`result_compare_chars` 只排除 `。`；而佛经导出 txt 的旧标点恰好以 `。` 为主 → 过滤后与 IDML 净文字逐字一致 → 验证自洽通过。
- **影响面**：根目录现成存在 `0080.txt`/`175导出.txt`/`275导出.txt`/`461导出.txt` 4 个此类危险文件；batch 配对规则（P1-2）恰不校验"句读结果"字样 → 任一文件被放入 pending 即触发静默错误注入。
- **修复建议（三层）**：
  1. **batch 层（首要）**：`find_pairs()` 恢复"句读结果"字样强校验，排除 `*导出.txt` 模式；
  2. **工具层**：`extract_from_result()` 检测结果文件是否含 `_OLD_PUNCT_CHARS` 中除 `。` 外的字符 → 报错拒绝（顿号/逗号残留即非纯句读结果）；
  3. **流程层**：在输出头部对比"结果句号位置与 IDML 原句号位置重合度"，重合度异常高时警告"疑似以原文当结果"。

## 新增 P2（实证确认）

- **正文含 `---` 截断**：`extract_from_result` 的 `split('---', 1)` 只切头部；正文 `---` 被保留为 3 个 `-` 字符进入比对 → 验证失败（安全）或（IDML 含 `-` 时）静默注入。句读结果格式约定需排除 Markdown 分隔线。
- **段首句号**：结果以 `。` 开头时插入 `(0,0,0,0,0)`——若 story 0 为被跳过的装饰 Story，句号被注入装饰 Story 且验证放行（低概率）。
- **497有图.idml（2.4MB，待处理大经书）**：单 Story_u15de 达 **73MB XML / 25.7 万 Content / 63 万字符记录**，StoryList 39 项缺 uac（空洞）；预估完整注入峰值内存 1-1.5GB，**处理前需先压测**。
- **归档缺口**：`done/175`、`done/275` 目录已不存在（git 索引记录删除）；`source/175从ID中导出文字_WD句读结果.md` 缺失 → 175 暂无法重处理；`injected/` 无 275/175 产出 → **275/175 的注入归档已丢失**。
- **461 双句读结果**：`461从ID中导出文字_WD句读结果.md`（07-23）与 `461导出_WD句读结果.md`（07-30）并存且大小不同——测试用旧版，版本分裂。

## 首轮假设修正（实证推翻/降级）

| 原判断 | 实证结论 |
|--------|---------|
| P1-6 正文 ACE 会丢失 | 0080 全流程实证：ACE 输入 4 → 输出 4 保留（ACE 均在装饰 Story）。**正文内嵌场景仍未覆盖**，维持潜在风险，降级 P2 |
| Br 模板可能泄漏 Br | 拆分分支仅取模板 `<Content>` 部分，`_verify_structure` 只查下限仍是防御缺口，但当前无泄漏路径 → 降级 P3 |
| 句号位置错位验证不设防 | 全局序列验证**能**抓句号顺序错位；仅"段落归属边界错位"（分割位置）验证不到 → 降级 P3 |

## 第二轮新增实证记录

| 验证项 | 结果 |
|--------|------|
| 0080 全流程（实体编码+多 Content CSR） | ✅ 1.2s / 49MB / 2929 字一致 / Br 72→72 / 句号 249→247（2 个被字体抑制） |
| 错误配对（0080.txt 当结果） | ❌ **静默通过，注入原排版标点**（P0） |
| 正文含 `---` | ❌ 截断 + `-` 字符残留（P2） |
| BOM+CRLF / 首尾空行 / 连续句号 | ✅ 行为正确 |
| 497 结构 | Story_u15de 73MB / 25.7 万 Content / 缺 uac |
| bat 编码 | UTF-8 无 BOM，inject.bat 中文注释在 GBK 控制台乱码显示（无害） |

---

# 附二：第三轮深挖（2026-08-04 15:16-15:30）

聚焦：输出 XML 合法性、实体编码形态、batch 全流程实测、抑制逻辑边界。**实证坐实 P1-3/P1-4，新增 1 项 P2，排除 1 项嫌疑。**

## 实证结论

| 验证项 | 结果 |
|--------|------|
| **输出 XML well-formed**（275/0080 全部 Story 经 ElementTree 严格解析） | ✅ 通过——InDesign 可打开的必要条件满足 |
| **0080 增补平面字符形态** | 输入 548 个 `&#x…;` 实体 → 正文重建输出 **543 个裸字符**（unescape 后 `_xml_escape` 不转义 → 以 UTF-8 裸字符写入），装饰 Story 保留实体原样；XML 合法、无字符丢失，但输出编码风格与原文件不一致，InDesign 兼容性未实证 → **P2** |
| **html.unescape 非法实体** | `&#x110000;`/`&#0;`/`&#xd800;` → 静默替换为 U+FFFD（不崩溃）；输入损坏时字符被静默替换且验证自洽 → **P3** |
| **last_slot U+3000 污染嫌疑** | **排除**：合成用例（72 字段落）确认「两字间有 U+3000 即抑制」符合规则字面，含句号在空格后场景 |
| **Br 统计负数**（P3-4） | 实证：275 输入 41 → 输出 39，"清空文字 CSR 清除 **-1**"（`in_br - 旧句号清除 - out_br` 可为负，打印误导） |
| **batch 全流程首次运行** | ✅ 完整：配对 → 注入（5684 字一致）→ 归档（done/275 三文件 + injected）→ 汇总 |
| **batch 二次运行 + R 全重命名** | ❌ **崩溃**：`archive()` 移动 pending 源文件时 `FileExistsError`（目标冲突未收集进 decisions → 默认 overwrite → shutil.move 目标已存在）→ 整批中断，**P1-4 坐实** |
| **P1-3（rename 归档旧文件）** | **坐实**：R 模式下 `archive()` 按旧名 `{name}导出_WD注入.idml` 查找 output → 归档的是**上一轮旧产物**，本轮 `_v2` 真实输出从未进入 injected/done |

## 新增 P2：`--output` 可覆盖源 IDML

`inject.py --output X.idml` 与输入同路径时，`main()` 冲突检测允许用户选"覆盖"→ **原始 IDML 被覆盖**。单文件模式应强制禁止 `--output == --idml`。

## 补充说明

- 本沙箱环境删除操作被安全机制拦截（回收站不可用），`output/` 残留 12 个 `_` 前缀测试产物（约 65MB，gitignore 已排除该目录），**建议手动清理**。
- batch 二次运行崩溃的 `shutil.move` 路径在真实 Windows 下表现为"静默覆盖 done/ 旧源文件"（copy+unlink 成功），本沙箱因 unlink 被拦截而崩溃——两种环境行为均异常，修复方向一致：源文件目标冲突纳入决策 + 归档前校验。

---

# 附三：第四轮深挖（2026-08-04 15:22-15:35）

聚焦：样式名依赖、死代码、双版本句读、段首句号、多经书全流程。**P2-10 坐实，新增多项实证。**

## 实证结论

| 验证项 | 结果 |
|--------|------|
| **35 全流程** | ✅ 10035 字一致 / 11650 字符（1002 句号）/ Br 161→161 完美 |
| **3093 全流程**（偈颂分行+字体抑制） | ✅ 5284 字一致 / 6237 字符（921 句号）/ Br 68→68 完美 |
| **累计 5 本经书全流程**（275/461/0080/35/3093） | ✅ 全部通过——工具核心真实样本高度稳定 |
| **句号样式名硬编码** `CharacterStyle/句号` | 全部 6 个 IDML 样本均用此名（0080 另有 `小句号`，但子串匹配不误判）；新经书若用不同样式名 → 句号样式静默丢失（P3） |
| **死代码** | `_remove_empty_punct_csrs`、`_insert_punct_csrs`、`_stream_write_idml` **仅定义未引用**（约 100 行） |
| **461 双句读版本** | 旧版(07-23) 10725 字符/1517 句号 vs 新版(07-30) 10753/1545；断句风格不同（`聞如是一時。` vs `聞如是。一時。`）；**test_verify 引用旧版，与最新句读脱节** |
| **段首句号（P2-10 坐实）** | 构造 `。` 开头结果 → 句号落入**净字 0 的装饰 Story u6fb**，验证链放行 |
| **MD 头部结构** | 所有经书句读结果文件**均无 `---` 头部**（直接正文）——AGENTS.md"头部统计信息"规范未执行；`split('---',1)` 为防御代码，正文含 `---` 才触发截断（P2-7） |

## 新增/升级

- **P2-10 从"潜在"升为"实证坐实"**：句读结果以 `。` 开头 → 装饰 Story 被注入无意义句号且验证通过。修复：段首句号应归属第一个"参与对齐的 story"，而非硬编码 (0,0,0,0,0)。
- **P2（流程）461 双版本**：需确认最终交付版本，测试改用一致版本。
- **P3 死代码 3 函数**：与 `generate_idml` 内置逻辑重复，建议删除。
- **P3 文档脱节**：AGENTS.md 输出规范（统计信息头部）与实际文件不符。

---

*本报告基于 2026-08-04 工作区快照。所有"未触发"结论均以当前 5 个样本（275/461/3093/0080/35）为前提，新增经书应重跑回归确认。*
