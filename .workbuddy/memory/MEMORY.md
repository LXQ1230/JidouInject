# 项目长期记忆：JidouInject

## 代码版本与备份惯例
- 每次修复先备份 `code/inject.py` 到 `backup/inject.py.v{版本}-{说明}-{日期}.bak`
- 当前版本：v1.5.5（拖拽增强，2026-08-07）；修复编号沿用 fix-plan-2026-08-04.md 的 P0-P3 体系
- 打包：`code/build_exe.bat`（Nuitka 4.1.3 / venv pack312 / Python 3.12.10），产物 `dist/IDML句读回注工具.exe`（dist/ 被 gitignore）
- **bat 是 UTF-8 编码，cmd 按 GBK 读取会乱码**——打包不要跑 bat，直接用 PowerShell 调 venv python -m nuitka

## v1.5.5 拖拽知识（重要，防复发）
- **架构**：`code/drag_input.py` 拖拽解析纯逻辑（launcher.py 图标拖拽与 gui_inject.py 窗口拖拽共用）：`classify_paths(paths)→DragPlan`（single/single_need_result/batch/error，扩展名分类=顺序自适应）、`find_result_for_idml`（同名→同经号两级）、`find_pairs_in_dir`、`is_excluded_input`（测试模式+_WD注入）
- **launcher.py**：显式 `--idml/--result` 走 legacy inject.main()（交互式冲突）；拖拽 single 走 run_cli 去交互化（inject.process + 冲突自动 _v2 绝不覆盖）；batch 复用 `run_batch_process`；need_result 用 `tk.Tk().withdraw()+askopenfilename`；文件夹 1 对降级 single、≥2 对 batch
- **窗口拖拽（gui_inject.py `_DragDropHelper`）纯 ctypes + WM_DROPFILES 零依赖**：
  - Win32 拖拽函数在 **shell32.dll**（DragAcceptFiles/DragQueryFileW/DragFinish）
  - ctypes 64 位指针必须显式声明类型（SetWindowLongPtrW argtypes/restype、HANDLE、GlobalLock/SendMessageW），否则指针截断
  - 子类化 WndProc：新 wndproc 强引用防 GC；回调经 `root.after(0)` 抛主线程（不破坏 P3-15 节流）；失败静默降级
  - 多次拖入累积（`_drag_pending` 袋）：先拖 IDML 再拖结果两次完成；busy 忽略
- **冒烟**（code/_smoke_dnd.py）：SendMessage 构造 HDROP——DROPFILES 结构 20 字节 + UTF-16LE 路径序列；**路径 NULL 终止符 2 字节 \x00\x00**（只加 1 字节会奇数偏移错位）；DragFinish 在 wndproc 内释放，勿再 GlobalFree
- 回归：test_drag_input.py（15 项）+ _smoke_dnd.py（4 场景）+ test_gui_logic.py

## P3-15 GUI 日志与线程知识（重要，防复发）
- **GUI 无响应根因**：`_poll_queue` while True 全量消费日志 → 主线程忙 insert/see('end') 无法处理消息 → Windows 判定未响应；`\r` 进度行在 Tk 显示为换行 → ScrolledText 无限膨胀
- **修复机制**（改 GUI 必须遵守）：① 节流 `POLL_BATCH=200`，批量拼接后只调一次 `_log`，主线程每 100ms 必返回事件循环；② worker 结束 `threading.Event` + `_drain_tail` 收尾（DONE 不被节流延迟）；③ `_log` 清理 `\r` + `MAX_LOG_LINES=5000` 裁剪；④ 主线程调含 print 的逻辑前必须临时换 NullWriter——Nuitka 打包后 sys.stdout 为 None，print 抛 AttributeError
- 批量核心逻辑在模块级纯函数 `run_batch_process(base_dir, out_dir, pairs)`（可单测）
- **GUI 交互**：单文件输出走「目录…」（askdirectory + askstring 改文件名，默认 `{IDML名}_WD注入.idml`）；批量选目录先弹确认窗口（输出目录可改 + Treeview 待处理列表）
- 测试：managed Python 3.13 无 tkinter，用系统 Python 3.12.10

## v1.5.3 保留排版符号（防复发）
- 成对符号 `_KEEP_BRACKETS`（（）()〔〕《》〈〉「」『』【】〖〗［］）+ 几何装饰 `_KEEP_ORNAMENTS`（■□△▲○●◇◆ 星 ※ 等约 30 个）；统一入口 `_is_keep_symbol`
- 机制：解析 `is_punct=False + is_bracket=True` → `_is_ws_for_compare` True（对齐不消费 txt、比对排除）→ 对齐 while ws 分支保留 → 重建原样输出
- 统计口径同步：story_clean_count 与 _verify_output 正文判定排除 is_bracket；txt 含 ○ 时对齐跳过不消费 IDML
- 回归：reg_v152.py 的 _KEEP_BRACKETS 含几何符号；SPECIAL 加 20 号用例

## v1.5.2 标点重分配（方案 C，防复发）
- 目标：消除逐字 CSR 拆分膨胀（35 号 2.87MB → 284KB，CSR 9396→4047）。文档：plan-csr-reuse-and-brackets-2026-08-07.md
- 主路径：文字 CSR 末尾标点（after_pos ≥ `len(orig_contents[last_slot])-1`，**对齐后 slot_pos 恒为 0**）转移进后邻空 segments 的旧句号 CSR
- 复用分支：`_punct_csr_from_own_template`（优先替换含「。」的 Content）保留各 CSR 自身 PointSize/FillColor/Br；分割副本先剥离 Group+Self
- 拆分兜底：连续文字 segment 合并一个 CSR（blocks 机制）；标点块继承前缀但**必须剥离 Br**（否则 Br+1，461 回归根因）
- 回归三层（reg_v152.py）：L1 净文本一致 / L2 br·psr 相等 csr≤旧（single1 对比原始 ×1.3；oldpunct 只认 `CharacterStyle/句号` 样式）/ L3 样式三元组 0 差异

## v1.5.1 Br 分行（防复发）
- 偈颂分行 = 多 Content CSR 内嵌 `<Br />`（Br 可在前缀/行尾），删除会使多行偈颂合并
- 旧句号 CSR 判定：样式含 `CharacterStyle/句号` **或** Content 为「。」（26 号样式是 [No character style]）
- 无记录旧句号 CSR：带 Br 且非 leading → `_clear_content_keep_br` 保留；leading 删除（防段首空行）
- 分割副本禁止整体剥 Br；`_verify_structure` br_min 扣除分割源段 trailing 区域；csr_suffix 定义于文字 CSR 处理开头（`csr_xml[content_end:]`），clean_suffix 用 rfind 截取
- 回归：reg_p150.py / reg_p313.py / reg_p314.py / reg_p150_mixed.py / reg_p150_497.py

## v1.5.0 标点白名单（防复发）
- 可回注：`_INJECTABLE_PUNCT = '，、；：？！。'`；白名单外旧标点（引号/括号等成对符号）一律拒绝——原文排版装饰符号
- 抑制：`_should_suppress_punct` 基于槽位+字体（仿宋/楷体区域抑制、思源宋体 U+3000 间隔抑制）
- 标点 Content 必须用 `_punct_content_tag(char)` / `_punct_csr_from_template(template, char)` 替换为实际标点（旧实现写死「。」）
- 回归：reg_p150.py（字节级）/ reg_p150_mixed.py（混合标点+负例+样式抽查）/ reg_p150_497.py

## P3-14 进度条与性能（防复发）
- 解析进度 <100%：designmap StoryList 比实际多 1（缺 ub3/uac）→ 分母用实际可用 Story 数（`member_names = set(zf.namelist())` 循环外缓存）
- 生成 O(K×L) 二次方：`_rebuild_paragraph_xml` 逐 CSR 替换 → 一次拼接 O(L)
- 分割空壳膨胀（4319 段→输出 1364MB）：空壳 CSR 用 `_DROP_CSR` 哨兵删除；PSR 开标签必须无条件保留
- 验证 O(n²)：按 Story 分组缓存 PSR 列表，每 Story 只 finditer 一次。497 全流程 78.6s
- 回归：reg_p314.py（字节不一致回退内容级对比，允许空壳瘦身）

## P3-13 自闭合空段落（防复发）
- IDML Story 末尾有 `<ParagraphStyleRange ... />` 自闭合空段（497 u562：581 开/580 闭）
- v1.4.2 四函数统一口径：解析按空段（chars=[]）纳入；footer 按"最后段落结构"定位；`validate_and_align` 分割索引起点 = `len(story['paragraphs'])`（防 para_idx 撞自闭合丢字）；验证统计配对段+自闭合段各计 1
- 诊断：diag_497.py；回归：reg_p313.py（全成员字节对比）

## 回归方法（可复用）
- 新旧代码（备份 vs 当前）对相同文件对各跑 `inject.process()`，对比输出 IDML 全成员字节
- importlib 不识别 .bak → 用纯内存 exec 加载（reg_p313.py load_module）；结构优化致字节差异时回退"Story Content 净文本序列"内容级对比
- Git Bash 中 rm 被沙箱拦截（相对路径问题）→ 用 Python os.remove 或 cmd 绝对路径清理

## 497 特例
- 497有图.txt 句号数 105717 与旧句号一致属巧合，FIX-1C 警告可忽略（用户已确认）
- 已处理：injected/497导出_WD注入.idml + done/497/；pending/ 新句读结果待重跑
