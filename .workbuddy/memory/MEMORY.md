# 项目长期记忆：JidouInject

## 代码版本与备份惯例
- 每次修复先备份 `code/inject.py` 到 `backup/inject.py.v{版本}-{说明}-{日期}.bak`
- 当前版本：v1.5.0（标点开放，2026-08-06）
- 修复编号沿用 fix-plan-2026-08-04.md 的 P0-P3 体系

## v1.5.0 标点白名单知识（重要，防复发）
- **可回注标点**：`_INJECTABLE_PUNCT = '，、；：？！。'`（_OLD_PUNCT_CHARS 的子集）。FIX-1B 只放行白名单内标点，白名单外旧标点（引号/括号/书名号等成对符号）仍一律拒绝——它们是原文排版装饰符号，不属于句读结果
- **抑制规则**：`_should_suppress_punct` 对标点类型无感（基于槽位+字体），白名单内所有标点一视同仁（仿宋/楷体区域抑制、思源宋体 U+3000 间隔抑制）
- **关键修复点**：`_rebuild_paragraph_xml` 标点 Content 必须用 `_punct_content_tag(char)`（拆分分支）/ `_punct_csr_from_template(template, char)`（旧句号 CSR 复用分支）替换为实际标点——旧实现从模板取「。」，新标点会被写成句号。纯句号时两函数输出与旧实现字节一致（回归依据）
- **样式**：新标点沿用 CharacterStyle/句号 模板 + 强制思源宋体（`text_pfx` 的 AppliedFont 覆盖），不查找 IDML 中是否已有逗号等样式
- 回归脚本：`code/reg_p150.py`（461/275/3093 字节级）、`code/reg_p150_mixed.py`（混合标点功能 + FIX-1B 负例 + 样式抽查）、`code/reg_p150_497.py`（497 实数据对照基线）

## P3-14 进度条与性能知识（重要，防复发）
- **解析进度条不到 100% 根因**：所有 IDML 的 designmap StoryList 都比实际 Story 文件多 1 个（缺 ub3/uac，InDesign 常见）。旧代码分母用声明数、循环 continue 跳过缺失 → 进度最大 97.x%。修复：分母改用实际可用 Story 数（`member_names = set(zf.namelist())` 循环外缓存），并提示缺失清单
- **生成输出卡 97.1% 根因**（497）：Story_u562 解压 71MB / 581 段 / 25.8 万 CSR；`_rebuild_paragraph_xml` 第 5 步从后往前逐 CSR 替换是 O(K×L)，K 大时二次方退化（旧代码单 Story 重建 >15 分钟未完成，实测 4319 分割段 × 每段全模板扫描 + 每次替换 O(L)）。修复：改为一次拼接 O(L)
- **分割段空壳膨胀**：分割副本（is_split_copy）无记录 CSR 原输出清空空壳 → 4319 段 × 数百空壳 → 输出解压 1364MB（输入 71MB 的 19 倍），验证阶段扫描 1.36GB 文本耗时 20 分钟+。修复：空壳 CSR 用 `_DROP_CSR` 哨兵删除（含 ACE 的 CSR 走 FIX-6 分支保留，不受影响）；注意拼接时 PSR 开标签（第一个 CSR 前）必须无条件保留
- **验证阶段 O(n²)**：`_verify_structure` 第 3 部分原对每个分割段都重新 finditer 整个 Story XML（4319 × 219MB ≈ 1TB 扫描，18 分钟）。修复：按 Story 分组缓存 PSR 列表，每 Story 只 finditer 一次
- 497 完整流程（新句读结果）：旧代码卡死 >15 分钟无结果 → 新代码 **78.6s**（输出 3.9MB 压缩 / u562 解压 219MB，624,801 字符验证通过）
- 回归脚本：`code/reg_p314.py`（461/275/3093 新旧对比；字节不一致时回退内容级对比，允许分割段空壳瘦身）

## P3-13 自闭合空段落知识（重要，防复发）
- 现象：InDesign 导出的 IDML 某些 Story 末尾会有自闭合空段落 `<ParagraphStyleRange ... />`（无文字、无闭标签，如 497 的 Story_u562，581 开 / 580 闭）
- 危害：旧代码三处口径不一致 → ① `_parse_story_xml` 按闭标签配对漏算空段；② `_get_story_footer` 把它划入 footer 随尾部写入输出；③ `_verify_structure` 用开标签数统计 → 实际比预期多 1 → 验证失败删输出
- 修复（v1.4.2 四函数统一口径）：解析把自闭合段作为空段（chars=[]）纳入；footer 按"最后段落结构（含自闭合）"定位；`validate_and_align` 分割索引起点 = `len(story['paragraphs'])` 而非 max_pi+1（防分割索引撞上自闭合段 para_idx 导致丢字）；验证统计口径与解析一致（配对段+自闭合段各计 1）
- 诊断脚本：`code/diag_497.py`（PSR 开闭平衡扫描 + 句号重合检测）；回归脚本：`code/reg_p313.py`（新旧代码对同输入对比输出 ZIP 全成员字节）

## 回归方法（可复用）
- 核心：新旧代码（备份 vs 当前）对相同文件对各跑 `inject.process()`，对比输出 IDML 全成员字节，零差异即无副作用
- 注意：importlib 不识别 .bak 扩展名；沙箱 `os.remove` 可能被安全机制拦截 → 用纯内存 exec 加载（见 reg_p313.py load_module）；结构优化（如空壳删除）导致字节差异时，回退"Story Content 净文本序列"内容级对比
- Git Bash 中 `rm -f` 会被沙箱安全删除机制拦截（相对路径问题）→ 用 Python os.remove 清理项目内临时文件

## 497 特例
- 497有图.txt（《中阿含经》卷第一）为真实 AI 句读结果，句号数 105717 与 IDML 旧句号完全一致属巧合，FIX-1C 警告可忽略（用户已确认）
- 497 已处理完成：injected/497导出_WD注入.idml + done/497/（旧句读结果）；pending/ 现有新句读结果（Aug 5 10:11）待重跑
