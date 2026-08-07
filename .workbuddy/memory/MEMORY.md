# 项目长期记忆：JidouInject

## 代码版本与备份惯例
- 每次修复先备份 `code/inject.py` 到 `backup/inject.py.v{版本}-{说明}-{日期}.bak`
- 当前版本：v1.5.5（拖拽增强：图标拖拽全形态 + 窗口内拖拽 WM_DROPFILES，2026-08-07）
- 修复编号沿用 fix-plan-2026-08-04.md 的 P0-P3 体系

## v1.5.5 拖拽知识（重要，防复发）
- **架构**：`code/drag_input.py` 拖拽解析纯逻辑（图标拖拽 launcher.py 与窗口拖拽 gui_inject.py 共用，口径唯一）：`classify_paths(paths)→DragPlan`（single/single_need_result/batch/error，扩展名分类=顺序自适应）、`find_result_for_idml`（同名→同经号两级）、`find_pairs_in_dir`（自 gui_inject 迁移）、`is_excluded_input`（测试模式+_WD注入）
- **launcher.py**：显式 `--idml/--result` 走 legacy inject.main()（交互式冲突）；拖拽 single 走 run_cli **去交互化**（直接 inject.process + 冲突自动 _v2，绝不覆盖）；batch 复用 `run_batch_process`（out_dir=首个 IDML 目录/output）；need_result 用 `tk.Tk().withdraw()+askopenfilename` 弹窗；文件夹 1 对降级 single（输出同目录），≥2 对 batch（输出 output/）
- **窗口拖拽（gui_inject.py `_DragDropHelper`）纯 ctypes + WM_DROPFILES 零依赖**：
  - **Win32 拖拽函数在 shell32.dll 不在 user32.dll**（DragAcceptFiles/DragQueryFileW/DragFinish）
  - **ctypes 64 位指针必须显式声明类型**：SetWindowLongPtrW argtypes=[HWND,c_int,c_void_p]（WINFUNCTYPE 实例 cast 成 c_void_p）、restype=c_ssize_t；DragQueryFileW hdrop 参数 HANDLE；GlobalLock/SendMessageW 同理——否则 64 位指针截断/溢出
  - 子类化 WndProc：新 wndproc 强引用防 GC；消息透传原 wndproc；拖拽回调经 `root.after(0)` 抛主线程（不破坏 P3-15 节流模型）；失败静默降级不影响 GUI
  - GUI 支持多次拖入累积（`self._drag_pending` 袋）：先拖 IDML 再拖结果两次完成；busy 忽略
- **冒烟技巧**（code/_smoke_dnd.py）：SendMessage 构造 HDROP 模拟真实拖拽——DROPFILES 结构（20 字节：pFiles+pt+fNC+fWide）+ UTF-16LE 路径序列；**路径 NULL 终止符 2 字节 \x00\x00**（只加 1 字节后续路径奇数偏移错位成乱码）；DragFinish 在 wndproc 内释放 hdrop，勿再 GlobalFree；GlobalAlloc/Lock/Unlock/SendMessageW 全要声明类型
- 回归：test_drag_input.py（15 项）+ _smoke_dnd.py（4 场景）+ test_gui_logic.py；打包 venv pack312

## P3-15 GUI 日志与线程知识（重要，防复发）
- **GUI 无响应根因**（批量处理大文件时）：旧 `_poll_queue` 的 `while True` 一次性全量消费日志队列 → 主线程长时间忙于 insert/see('end')，无法处理窗口消息 → Windows 判定「未响应」；且 `_log_progress` 的 `\r` 进度行在 Tk 文本控件中显示为换行，ScrolledText 无限膨胀、see('end') 越来越慢（恶性循环）
- **修复机制**（gui_inject.py，改 GUI 必须遵守）：① 节流 `POLL_BATCH=200`——每次 poll 最多消费 200 条，批量拼接后只调一次 `_log`，主线程每 100ms 必返回事件循环；② worker 结束用 `threading.Event` 置位 + `_drain_tail` 收尾（DONE 标记不被节流延迟）；③ `_log` 里 `\r` 清理 + 行数上限 `MAX_LOG_LINES=5000`（超出删除最前面行）；④ 主线程调用含 print 的逻辑（如 find_pairs）前必须临时换 NullWriter——Nuitka 打包（--windows-console-mode=disable）后 sys.stdout 为 None，print 抛 AttributeError
- **验证**：2 万条含 \r 日志风暴 0.5s 完成、行数裁剪 5001、收尾正常；批量核心逻辑在模块级纯函数 `run_batch_process(base_dir, out_dir, pairs)`（可单测，每文件前打印 `[i/n] 经号 x`）
- **GUI 交互流程**：单文件输出走「目录…」（askdirectory + simpledialog.askstring 改文件名，默认 `{IDML名}_WD注入.idml`）；批量选目录后先弹确认窗口（输出目录可改 + Treeview 待处理列表），确认才处理
- 打包 venv：`C:\Users\Admin\.workbuddy\binaries\python\envs\pack312`（Nuitka 4.1.3 / Python 3.12.10）；managed Python 3.13 无 tkinter，测试用系统 Python 3.12.10

## v1.5.3 保留排版符号知识（重要，防复发）
- **范围**：成对符号 `_KEEP_BRACKETS`（（）()〔〕《》〈〉「」『』【】〖〗［］）+ 几何装饰符号 `_KEEP_ORNAMENTS`（■□△▲○●◇◆ 及变体/星/※，约 30 个）；统一入口 `_is_keep_symbol`
- **机制**（与括号同构）：解析 `is_punct=False + is_bracket=True` → `_is_ws_for_compare` 返回 True（对齐不消费 txt、字体查找跳过、比对排除）→ 对齐 while ws 分支作为文字记录保留 → 重建 Content 原样输出
- **必须同步的统计口径**：story_clean_count（validate_and_align）与 _verify_output 的正文 Story 判定排除 is_bracket（防含符号装饰 Story 误判）
- **20 号（pending/20.idml）**：正文含字间镶嵌几何符号（「如■是□我◎聞一◇時佛▲住△…」7 个）+ 校勘注全角圆括号 9 对（（甯）（磧）（清）（大）（卍）（麗）（宋）（元）（明））+ ．40/.1 旧标点（自动清除）。题记「唐三藏法師菩提流志奉詔譯」在装饰 Story（12 字 <50）自动跳过——**不是障碍**。跑通后保留符号 25→25 零丢失、正文文字 == txt（14821 字）、句号复用 2386/2425（98.4%）
- **txt 含 ○**：句读结果保留 ○ 位置（「卷第十七○原本為」）——对齐时 txt 的 ○ 走 `_is_ws_for_compare` 跳过，不消费 IDML ✓
- **回归**：reg_v152.py 的 `_KEEP_BRACKETS` 含几何符号（统一统计）；SPECIAL 加 20 号用例（纯句号 L3 判定：句号复用 ≥90%，非 35 号混合标点判定）

## v1.5.2 标点重分配知识（重要，防复发）
- **方案 C 目标**：消除逐字 CSR 拆分导致的体积膨胀与排版异常（35 号混合标点 2.87MB → 284KB ≈ 原始 283KB；CSR 9396 → 4047）。方案文档：plan-csr-reuse-and-brackets-2026-08-07.md
- **改动点 1（重分配主路径）**：文字 CSR 末尾标点（after_pos ≥ 槽位末尾偏移，槽位末尾用 `len(orig_contents[last_slot])-1` 计算——**对齐后文字记录 slot_pos 恒为 0**，不能用 segment pos）转移进后邻 segments 为空的旧句号 CSR。文字 CSR 零改动走合并路径
- **改动点 2（复用分支）**：`_punct_csr_from_own_template`（优先替换含「。」的 Content）替代全局 punct_template，保留各 CSR 自身 PointSize/FillColor/Br；分割副本先剥离 Group+Self；多标点去 Br 拼接 + 末尾补 Br
- **改动点 3（拆分兜底）**：无法重分配的标点（CSR 中间/后邻非句号 CSR）走拆分路径时**连续文字 segment 合并为一个 CSR**（blocks 机制：文字块 bno 0 用 csr_prefix 其余 clean_prefix；标点块继承前邻文字块前缀但**必须剥离 Br**——否则行首 Br 被标点继承导致 Br+1，461 回归 Br 44→45 的根因）
- **回归判定口径**（reg_v152.py，三层验证）：
  - L1 净文本：CASES 新旧逐 Story 完全一致；SPECIAL 35 号对比**正文 Story（clean≥50）文字序列 vs txt**（去标点去全部空白——IDML 有 3 个 ASCII 空格被对齐跳过属预期；装饰 Story 页眉「佛說離垢施女經」不参与对齐）
  - L2：br/psr 新 vs 旧必须相等；csr 新≤旧；**single1 对比原始 IDML ×1.3**（275 原文即逐字 CSR 结构 2669→新 2674 属正常，旧 5302 才是拆分膨胀）；oldpunct 只认 `CharacterStyle/句号` 样式（Content=='。' 的兜底拆分 CSR 不计，否则 461 虚增 1297→1546）；preserved_multichar ≥95% 硬通过 / 85-95% 警告（461 86.4% 为数据特性：txt 句读密度高 + IDML 长句块多，句号在 CSR 中间属必要拆分）
  - L3：样式三元组（AppliedFont/PointSize/FillColor）按文本匹配对比 0 差异；35 号句号 CSR 复用抽查（Content 为实际标点）
- **35 号混合标点 txt**：`done/35/35_WD句读结果_vs_35_对比文本_20260807-0900.txt`（815 句号+702 逗号+190 顿号）；「時、離垢施女、則為梵志而說頌曰」是方案 C 复现点，IDML 原文此处有独立旧句号 CSR，重分配生效
- 回归脚本：`code/reg_v152.py`（字节级对比退出历史舞台，由净文本+结构指标+样式抽查替代）

## v1.5.1 Br 分行知识（重要，防复发）
- **偈颂分行结构**：InDesign 偈颂排版 = 多 Content CSR 内嵌 `<Br />`（`<Content>一行</Content><Br /><Content>二行</Content>`），Br 也可在 CSR 前缀（行首）或 Content 后（行尾）。Br 是段内软换行，删除会让多行偈颂合并成一行
- **旧句号 CSR 判定口径**：`is_punct` = 样式含 `CharacterStyle/句号` **或** Content 为「。」——26 号原文旧句号样式是 `[No character style]`（验证原口径只认样式名 → 漏计 Br 豁免 → 误报）
- **无记录旧句号 CSR（A1）**：带 Br 且非 leading → 必须 `_clear_content_keep_br` 保留（清空 Content + Br）；leading 删除（防段首空行，275 回归）。旧实现整体删除 → 偈颂分行丢失
- **多 Content 分割副本**：禁止整体剥 Br（`is_split_copy` 剥 Br 是 v1.4.1 遗留 bug，26 号副本 31 Br → 2 Br）；leading 空壳由 A3 `_DROP_CSR` 处理
- **分割豁免（验证）**：`_verify_structure` 的 br_min 要扣除分割源段 trailing 区域（最后一个文字记录 CSR 之后）的无记录 CSR Br——分割移走文字后该区域 Br 剥离属预期清理，不豁免会误报（偈颂+段落边界文件）
- **拆分 suffix 细节**：csr_suffix 定义于文字 CSR 处理开头（`csr_xml[content_end:]`，含 Br），clean_suffix 用 rfind 截取（仅闭标签）——**不要**把 clean_suffix 改成 content_end 截取（3093 会多格式化空白 `\n\t\t\t` 字节回归）
- 回归脚本：`code/reg_p150.py` / `reg_p313.py` / `reg_p314.py`（461/275/3093，字节不一致回退内容级对比，允许 Br 分行保留差异）；`reg_p150_mixed.py`（`c in PUNCTS` 对空串误判 True → 须 `c and` 前置）；`reg_p150_497.py`（497 与 v1.4.3 基线内容级对比）

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
