# 拖拽增强方案 v2（完善版）：exe 图标拖拽 + GUI 窗口内拖拽

日期：2026-08-07（v1 于 11:52 产出，v2 于 12:00 完善）
涉及版本：v1.5.4 → v1.5.5
状态：待确认

---

## 一、需求汇总（已确认）

| 维度 | 需求 |
|------|------|
| 拖拽形态 | ① exe 图标拖拽（增强现有 launcher.py）② GUI 窗口内拖拽（新增）|
| 内容形态 | ① 2 个文件顺序自适应 ② 只拖 1 个 IDML 自动找结果 ③ 批量多对文件 ④ 整个文件夹 |

---

## 二、代码现状核查结论（v2 新增，方案依据）

| 项目 | 现状 | 对方案的影响 |
|------|------|-------------|
| `inject.main()` 冲突处理 | `resolve_conflicts` 是 **input() 交互式**（A/S/R/C 按键选择，无 TTY 时默认跳过）| 拖拽 CLI 场景体验差 → run_cli 必须去交互化 |
| `run_batch_process(base_dir, out_dir, pairs)` | out_dir **必填**，`os.makedirs` 直接建；输出命名固定 `{经号}导出_WD注入.idml`；冲突自动 `_v2` 重命名 | CLI 批量需给默认 out_dir；复用其自动重命名口径 |
| `find_pairs_in_dir(base_dir)` | 目录内按经号配对；排除 `*_WD注入`/`_old_test`/`_test`；多 IDML 含「导出」优先 | 散文件多对不能直接用（无目录）→ drag_input 需自建配对规则 |
| GUI 输入区 | `idml_var`/`result_var`/`output_var` 三个 Entry + 浏览按钮；批量确认窗 `_show_batch_confirm(base_dir, pairs)` 已具备 | 窗口拖拽 single → 填前两个框；batch → 填目录并弹确认窗 |
| `launcher.py` 入口 | 任意非文件 argv 静默进 GUI；`--idml` 等显式参数未识别 | 需补显式参数兼容（老命令行用法）|
| P3-15 线程模型 | 批量 worker + 队列节流，主线程 100ms 轮询 | WM_DROPFILES 回调必须经 `after(0)` 抛主线程，不破坏模型 |

---

## 三、总体架构

```
                     ┌──────────────────────────────┐
                     │ drag_input.py（新增，纯逻辑）  │
                     │ classify_paths(paths)→DragPlan │
                     │ find_result_for_idml(idml)    │
                     └───────────┬──────────────────┘
               ┌─────────────────┼──────────────────┐
               ▼                 ▼                  ▼
   launcher.py（图标拖拽）   gui_inject.py（窗口内）  build_exe.bat（打包）
   single → run_cli(去交互)  WM_DROPFILES 桥接       版本 → 1.5.5
   batch  → run_batch       handle_dropped_paths    零新依赖
   --idml 显式参数 → CLI     （可单测）
```

三条设计原则（v2 强化）：
1. **解析纯逻辑独立**：`drag_input.py` 无 GUI/无 IO 依赖，图标拖拽与窗口拖拽共用，口径唯一、可单测。
2. **行为一致化**：所有非交互路径（图标拖拽 single/批量、窗口批量）的输出冲突一律**自动 `_v2` 重命名**，绝不覆盖原文件——与 `run_batch_process` 现有口径对齐，废弃 `inject.main()` 的交互分支。
3. **窗口拖拽零依赖**：纯 ctypes + WM_DROPFILES，规避 tkinterdnd2 的 tkdnd 二进制在 Nuitka onefile 下的打包风险。

---

## 四、drag_input.py — 拖拽输入解析（新文件，纯逻辑）

### 4.1 数据结构

```python
@dataclass
class DragPlan:
    mode: Literal['single', 'single_need_result', 'batch', 'error']
    idml: str | None                 # single 系列：IDML 绝对路径
    result: str | None               # single 系列：结果绝对路径（need_result 时为 None）
    pairs: list[tuple[str, str, str]] | None  # batch：[(idml, result, 经号), ...]
    base_dir: str | None             # batch：公共目录（取首个 IDML 所在目录，供默认 out_dir）
    messages: list[str]              # 警告/提示（不阻断）
```

### 4.2 识别流程 `classify_paths(paths)`

**阶段一：清洗与分类**
- 绝对路径化、去重、忽略不存在路径
- 扩展名分类：`.idml` / 结果文件（`.md`/`.txt`）/ 目录 / **无效类型**（其他扩展名 → 忽略并警告）
- 排除输入：文件名含 `_WD注入`、`_old_test`、`_test`（与 `gui_inject._TEST_PATTERNS` 口径一致，防测试产物误当输入）

**阶段二：分支解析**

| 输入组合 | mode | 行为 |
|---------|------|------|
| 含目录 | batch | 每个目录 `find_pairs_in_dir` 配对并合并；目录无配对 → 警告条目 |
| 恰好 1 IDML + 0 结果 | single_need_result | `find_result_for_idml` 自动查找；找到 → 降级 single；找不到 → 保持 need_result |
| 1 IDML + ≥1 结果 | single | 结果取排序第一 |
| ≥1 结果 + 0 IDML | error | 提示缺少 IDML（列出结果清单）|
| 多 IDML（+ 可选多结果）| batch | **配对规则见 4.3** |
| 全部无效/空 | error | 提示拖入内容无效 |

**阶段三：顺序自适应** — 全程基于扩展名分类，与拖拽顺序无关。

### 4.3 散文件多对配对规则（v2 补全，GUI 批量窗口复用）

拖入的 IDML 集合 I、结果集合 R（不含目录场景）：
1. 对每个 `idml ∈ I`，取其经号 n，在 R 中找同经号结果（多个取排序第一）→ 配对
2. 未配对的 idml → `find_result_for_idml(idml)` 在其**所在目录**补找
3. 仍未配对的 idml → 警告并跳过（batch 中不含它）
4. 未使用的 R → 警告（提示可能拖错/缺对应 IDML）
5. 配对结果 ≥2 对 → batch；1 对 → single（统一走 single 流程）

### 4.4 自动查找结果 `find_result_for_idml(idml)`（两级优先）

1. 同目录、同 basename（去扩展名）的 `.md`/`.txt`（最精确）
2. 同目录下、同开头经号的结果文件（复用 find_pairs_in_dir 配对结果，取排序第一）
3. 找不到 → None

---

## 五、launcher.py 增强（图标拖拽 + 命令行兼容）

### 5.1 入口分流（v2 补显式参数兼容）

```
argv 解析：
├─ 含 --idml / --result 显式参数（老命令行用法）→ AllocConsole → inject.main()（原逻辑，
│    交互式冲突处理仅在输出已存在时触发，命令行场景可接受）→ 回车关闭
├─ 纯路径 ≥1（拖拽场景）→ classify_paths(paths)
│   ├─ single              → AllocConsole → run_cli(idml, result)
│   ├─ single_need_result  → AllocConsole → tkinter 弹窗选结果 → run_cli / 取消退出
│   ├─ batch               → AllocConsole → run_batch_process(base_dir, out_dir, pairs)
│   │                         out_dir 默认 = 首个 IDML 所在目录/output（与 GUI 批量语义一致）
│   │                         打印计划摘要 + [i/n] 进度 + 汇总 → 回车关闭
│   └─ error               → AllocConsole → 打印 messages → 回车关闭
└─ 无参数 → GUI（不变）
```

### 5.2 run_cli 去交互化（v2 关键变更）

- **改**：不再构造 `sys.argv` 调 `inject.main()`；改为直接调 `inject.process(idml, result, output)`。
- 输出路径：默认 `{IDML名}_WD注入.idml`（与 GUI 单文件一致）；已存在 → 自动 `_v2` 重命名（复用 `inject._resolve_output_path`）。
- **行为变更说明**：当前 v1.5.4 拖拽 2 文件走 `inject.main()`，输出冲突时控制台交互选择 A/S/R/C；v1.5.5 起自动重命名、零交互。`--idml` 显式参数路径保留交互式（命令行场景用户可控）。
- 校验前置复用 `gui_inject.check_idml_valid`（zip 有效性）+ 结果文件存在性。

### 5.3 need_result 弹窗细节

- `AllocConsole` 后创建隐藏 root：`tk.Tk().withdraw()` → `askopenfilename(filetypes=[("文本文件", "*.md *.txt")])`
- 取消 → 打印提示退出；选中 → run_cli

---

## 六、gui_inject.py 增强（窗口内拖拽）

### 6.1 技术实现（纯 ctypes + WM_DROPFILES）

`_DragDropHelper` 类（gui_inject.py 内新增，约 100 行）：
1. `attach(root)`：`hwnd = root.winfo_id()` → `DragAcceptFiles(hwnd, True)` → `SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_proc)` 子类化
2. 新 WndProc：收到 `WM_DROPFILES`（0x233）→ `DragQueryFileW` 枚举全部路径 → `DragFinish(hdrop)` → 收集路径列表 → **`root.after(0, lambda: app.handle_dropped_paths(paths))`**（抛主线程，不在 wndproc 内碰 Tk）
3. 其余消息（含 WM_NCDESTROY）透传原 WndProc
4. 防 GC：new_proc 强引用存 helper 实例；卸载时 `DragAcceptFiles(hwnd, False)` 还原（可选，进程退出即回收）
5. **失败静默降级**：`SetWindowLongPtr` 失败/非 Windows → 打印警告，GUI 其余功能不受影响
6. 编码：全程 `DragQueryFileW`（宽字符），中文路径无乱码问题

**取舍说明**：WM_DROPFILES 是"释放即回调"机制，**无拖入时预览反馈**（DragEnter 高亮需 OLE IDropTarget，复杂度显著提升）。v1.5.5 接受无预览，以零依赖换取打包可靠性；后续如需预览可再升级 IDropTarget 方案。

### 6.2 交互逻辑 `handle_dropped_paths(paths)`（v2 补多次拖入累积）

```
busy（处理中）→ 忽略 + 日志提示
非 busy：
  pending 袋（self._drag_pending: list[str]）合并本次 paths
  → classify_paths(合并后)
  ├─ single            → 填 idml_var + result_var（output_var 留空=默认），清空 pending，
  │                      日志/status 提示「已从拖拽载入」，不自动执行
  ├─ single_need_result → 填 idml_var，保留 pending（等下一次拖结果），
  │                      日志提示「请再拖入句读结果，或点击浏览选择」
  ├─ batch             → base_dir 填「公共目录或首个 IDML 目录」，
  │                      弹 _show_batch_confirm（复用现有确认窗），清空 pending
  └─ error             → messagebox 提示 messages；pending 保留（可继续补拖）
```

**多次拖入累积**（v2 新增）：先拖 IDML、再拖结果（分两次）→ 第二次「只有结果」先与 pending 中 IDML 合并解析 → 成功配对。支持自然补拖，无需清空重来。

### 6.3 可测性（v2 新增）

- `handle_dropped_paths(paths)` 是独立方法，单测直接调用（模拟释放），绕开真实 OLE 拖拽
- WM_DROPFILES 仅做「系统消息 → paths」桥接，本身逻辑不进入单测（exe 实测覆盖）

---

## 七、build_exe.bat 与文档更新

- `--product-version`、`--file-description` → 1.5.5；`gui_inject.py` APP_TITLE 同步
- 无新增依赖、无新增 include（WM_DROPFILES 纯 ctypes）
- `docs/打包版使用说明.md`：新增「拖拽使用」章节（图标拖拽 4 形态 + 窗口内拖拽 + 注意事项）

---

## 八、测试计划

### 8.1 纯逻辑单测（`code/test_drag_input.py`，新建）
- 2 文件乱序（结果在前）→ single 正确配对
- 1 IDML（同目录同名/同经号结果）→ single 自动找到
- 1 IDML（无结果）→ single_need_result
- 1 结果 → error
- 多对散文件（含经号错配、多结果、多 IDML）→ 配对规则正确
- 文件夹（含 `*_WD注入`/测试产物）→ 排除正确
- 混合（文件夹 + 散文件 + 无效类型）→ 分类正确
- 空/无效路径 → error

### 8.2 GUI 集成单测（Tk 环境，沿用 test_gui_logic.py 模式）
- `handle_dropped_paths`：single 填表 / need_result 保留 pending / 二次拖入补结果 / batch 弹确认 / busy 忽略 / error 提示

### 8.3 实测（源码运行 + 打包后 exe）
- 图标拖拽：1 个 / 2 个乱序 / 多对 / 文件夹（用 275/461 测试文件）
- 窗口拖拽：GUI 内同 4 形态（含分两次拖）
- `--idml/--result` 显式参数：回归可用
- 双击 exe → GUI 正常；输出已存在 → 自动 _v2 不覆盖

### 8.4 回归
- 不修改 `inject.py` 核心逻辑（run_cli 只改 launcher.py）→ reg_v152.py 不受影响
- 双击 GUI、拖 2 文件 CLI 两条既有路径行为回归

---

## 九、实施步骤（确认后执行）

1. 备份 `launcher.py`、`gui_inject.py` 至 `backup/`（.bak 命名惯例）
2. 新建 `code/drag_input.py` + `code/test_drag_input.py` → 单测通过
3. 改 `launcher.py`：显式参数识别 + classify 分流 + run_cli 去交互 + batch/need_result 路径
4. 改 `gui_inject.py`：`_DragDropHelper` + `handle_dropped_paths` + pending 累积
5. 更新版本号（gui_inject.py / build_exe.bat / 使用说明文档）→ Nuitka 重新打包
6. 8.2/8.3 测试 → 交付

---

## 十、风险与对策

| 风险 | 对策 |
|------|------|
| WndProc 子类化影响 Tk 消息 | 全部透传原 WndProc；回调强引用防 GC；失败静默降级（拖拽不可用 ≠ GUI 不可用）|
| WM_DROPFILES 无拖入预览 | 接受取舍（v1.5.5），后续可升级 IDropTarget |
| 散文件配对歧义（同经号多结果）| 固定取排序第一 + 警告提示，与 find_pairs_in_dir 口径一致 |
| 多次拖入累积状态误用 | pending 仅在同一次会话内、成对即清空；busy 时忽略拖入 |
| 打包后 ctypes 不可用 | 纯 Win32 API 无动态链接问题；onefile 解压后行为不变（实测验证）|
