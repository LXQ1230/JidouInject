#!/usr/bin/env python3
"""IDML 句读回注工具 — 图形界面（tkinter，纯标准库，无第三方依赖）。

由 launcher.py 无参数启动时调用。提供两种使用方式：
  1. 单文件回注：选择 IDML + 句读结果文件；输出通过「目录…」选择输出目录
     并修改文件名（默认「{IDML名}_WD注入.idml」），留空则与 IDML 同目录。
  2. 批量处理：选择文件夹后先显示待处理列表（可指定输出目录），
     确认后才逐个回注，输出文件「{经号}导出_WD注入.idml」，
     同名自动 _v2 重命名，绝不覆盖原文件。

核心处理复用 inject.process()，通过重定向 stdout/stderr 到线程安全队列，
在主线程轮询刷新日志区（节流消费 + 日志行数上限，防止批量处理时
UI 无响应），保证 Tk 界面线程安全。
"""

import io
import os
import queue
import sys
import threading
import time
import traceback
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import inject  # noqa: E402  （同目录核心库）
from drag_input import classify_paths, find_pairs_in_dir  # noqa: E402  （拖拽解析共用）

APP_TITLE = "IDML 句读回注工具 v1.5.5"

# 测试/演练文件模式：批量配对时必须排除，防止把测试产物当正式输入
# （口径统一于 drag_input.is_excluded_input）

# P3-15: GUI 无响应修复 — 日志消费节流与上限
# 根因：批量处理时 worker 线程持续产生日志，旧实现 _poll_queue 的
# while True 一次性全量消费 → 主线程长时间忙于 insert/see('end')，
# 无法处理窗口消息 → Windows 判定「未响应」；且 _log_progress 的
# \r 进度行在 Tk 文本控件中会显示为换行，日志区无限膨胀越滚越慢。
POLL_BATCH: int = 200      # 每次 poll 最多消费的日志条数（其余留给下轮）
MAX_LOG_LINES: int = 5000  # 日志区最大行数，超出删除最前面的行


# ─────────────────────────── 纯逻辑（不依赖 Tk，可单测） ───────────────────────────
# find_pairs_in_dir 等配对逻辑已迁移至 drag_input.py（两处拖拽共用，口径唯一）

def check_idml_valid(idml_path: str) -> str | None:
    """校验 IDML 文件有效性，返回错误消息（None 表示通过）。"""
    if not os.path.isfile(idml_path):
        return f"IDML 文件不存在:\n{idml_path}"
    try:
        with zipfile.ZipFile(idml_path, 'r') as zf:
            if 'designmap.xml' not in zf.namelist():
                return f"文件不是有效的 IDML（缺少 designmap.xml）:\n{idml_path}"
    except zipfile.BadZipFile:
        return f"文件不是有效的 ZIP/IDML 文件:\n{idml_path}"
    return None


def run_batch_process(base_dir: str, out_dir: str,
                      pairs: list[tuple[str, str, str]]) -> list[tuple[str, str, float]]:
    """批量回注核心逻辑（纯函数，print 输出走当前 stdout，可单测）。

    Args:
        base_dir: 输入目录（仅用于日志展示）
        out_dir: 输出目录（已由用户在确认窗口指定）
        pairs: [(idml绝对路径, 结果绝对路径, 经号), ...]

    Returns:
        [(经号, 状态, 耗时秒), ...]，状态 ∈ {成功, 失败, 跳过}
    """
    os.makedirs(out_dir, exist_ok=True)
    print(f"找到 {len(pairs)} 个待处理文件对，输出目录: {out_dir}\n")

    results: list[tuple[str, str, float]] = []
    for i, (idml, md, num) in enumerate(pairs, 1):
        print(f"\n[{i}/{len(pairs)}] 经号 {num}: "
              f"{os.path.basename(idml)} + {os.path.basename(md)}")
        out_path = os.path.join(out_dir, f"{num}导出_WD注入.idml")
        if os.path.exists(out_path):
            resolved = inject._resolve_output_path(out_path, 'rename_v2')
            if not resolved:
                print("  跳过（无法生成输出路径）")
                results.append((num, "跳过", 0.0))
                continue
            print(f"  输出已存在，自动重命名: {os.path.basename(resolved)}")
            out_path = resolved

        t0 = time.time()
        try:
            inject.process(idml, md, out_path)
            results.append((num, "成功", time.time() - t0))
        except Exception as e:
            print(f"  处理失败: {e}")
            results.append((num, "失败", 0.0))

    print("\n" + "=" * 60)
    print("批量处理完成\n")
    for num, st, sec in results:
        print(f"  {num}: {st}  ({sec:.1f}s)")
    ok = sum(1 for _, s, _ in results if s == "成功")
    print(f"\n成功 {ok}/{len(results)}  输出目录: {out_dir}")
    return results


# ─────────────────────────── stdout 重定向（线程安全） ───────────────────────────

class QueueWriter(io.TextIOBase):
    """把 print 输出转发到线程安全队列。

    isatty() 返回 False → inject._log_progress 自动退化为换行日志
    （GUI 中 \r 覆盖式进度条不适用）。
    """

    def __init__(self, q: queue.Queue):
        super().__init__()
        self._q = q

    @property
    def encoding(self) -> str:
        return 'utf-8'

    def isatty(self) -> bool:
        return False

    def write(self, s) -> int:
        if s:
            self._q.put(s)
        return len(s)

    def flush(self) -> None:
        pass


class NullWriter(io.TextIOBase):
    """静默丢弃输出的 writer。

    Nuitka 打包（--windows-console-mode=disable）后 sys.stdout 为 None，
    主线程里 print 会抛 AttributeError。配对逻辑内含 print 警告，
    在主线程调用前需临时替换 stdout 防止崩溃。
    """

    @property
    def encoding(self) -> str:
        return 'utf-8'

    def isatty(self) -> bool:
        return False

    def write(self, s) -> int:
        return len(s)

    def flush(self) -> None:
        pass


# ─────────────────────────── 应用主界面 ───────────────────────────

class InjectApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("800x600")
        root.minsize(700, 500)

        self.idml_var = tk.StringVar()
        self.result_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.busy = False
        self._drag_pending: list[str] = []   # 窗口拖拽累积袋（支持分次补拖）

        self._build_ui()
        self._log(
            "欢迎使用 IDML 句读回注工具\n"
            "────────────────────────────────────────────\n"
            "使用方式一（拖拽）：把 IDML 文件、句读结果文件或文件夹\n"
            "  拖到本窗口内（也可拖到 exe 图标上）自动识别并载入。\n"
            "  支持：两个文件（顺序不限）、单个 IDML 自动找结果、\n"
            "  多对文件、整个文件夹（按经号配对批量）。\n"
            "使用方式二（界面）：下方选择文件后点「开始回注」；\n"
            "  或点「批量处理…」选择文件夹，确认待处理列表后自动配对处理。\n"
            "────────────────────────────────────────────\n"
        )

        # 窗口内拖拽（纯 ctypes + WM_DROPFILES；失败静默降级，不影响使用）
        self._drag_helper = _DragDropHelper(self)

    # ── 界面构建 ──
    def _build_ui(self) -> None:
        pad = {'padx': 8, 'pady': 3}

        top = ttk.Frame(self.root)
        top.pack(fill='x', **pad)

        ttk.Label(top, text="IDML 文件").grid(row=0, column=0, sticky='w')
        ttk.Entry(top, textvariable=self.idml_var).grid(
            row=0, column=1, sticky='ew', padx=6)
        ttk.Button(top, text="浏览…", width=8,
                   command=self._pick_idml).grid(row=0, column=2)

        ttk.Label(top, text="句读结果").grid(row=1, column=0, sticky='w', pady=(6, 0))
        ttk.Entry(top, textvariable=self.result_var).grid(
            row=1, column=1, sticky='ew', padx=6, pady=(6, 0))
        ttk.Button(top, text="浏览…", width=8,
                   command=self._pick_result).grid(row=1, column=2, pady=(6, 0))

        ttk.Label(top, text="输出文件").grid(row=2, column=0, sticky='w', pady=(6, 0))
        ttk.Entry(top, textvariable=self.output_var).grid(
            row=2, column=1, sticky='ew', padx=6, pady=(6, 0))
        ttk.Button(top, text="目录…", width=8,
                   command=self._pick_output).grid(row=2, column=2, pady=(6, 0))
        ttk.Label(top,
                  text="「目录…」选择输出目录后可修改文件名；留空 = 与 IDML 同目录生成"
                  "“XXX_WD注入.idml”",
                  foreground='#888888').grid(
            row=3, column=1, sticky='w')

        top.columnconfigure(1, weight=1)

        ops = ttk.Frame(self.root)
        ops.pack(fill='x', **pad)
        self.btn_single = ttk.Button(ops, text="开始回注", command=self._start_single)
        self.btn_single.pack(side='left', padx=(0, 8))
        self.btn_batch = ttk.Button(ops, text="批量处理…", command=self._start_batch)
        self.btn_batch.pack(side='left', padx=8)
        ttk.Button(ops, text="打开输出目录",
                   command=self._open_output_dir).pack(side='left', padx=8)

        log_frame = ttk.LabelFrame(self.root, text="处理日志")
        log_frame.pack(fill='both', expand=True, **pad)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, state='disabled', wrap='char',
            font=('Consolas', 9), background='#fbfbfb', foreground='#1a1a1a')
        self.log_text.pack(fill='both', expand=True, padx=4, pady=4)

        status = ttk.Label(self.root, textvariable=self.status_var,
                           relief='sunken', anchor='w')
        status.pack(fill='x', side='bottom')

    # ── 文件选择 ──
    def _pick_idml(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 IDML 文件", filetypes=[("IDML 文件", "*.idml")])
        if path:
            self.idml_var.set(path)

    def _pick_result(self) -> None:
        path = filedialog.askopenfilename(
            title="选择句读结果文件",
            filetypes=[("文本文件", "*.md *.txt"), ("所有文件", "*.*")])
        if path:
            self.result_var.set(path)

    # ── 窗口拖拽（WM_DROPFILES → handle_dropped_paths） ──
    def handle_dropped_paths(self, paths: list[str]) -> None:
        """窗口内释放文件后的统一处理（供 _DragDropHelper 回调与单测直接调用）。

        支持多次拖入累积（pending 袋）：先拖 IDML、再拖结果可分两次完成；
        成对后自动清空。busy 时忽略拖入。
        """
        if self.busy:
            self._log("处理中，已忽略拖入的文件。\n")
            return

        self._drag_pending.extend(paths)
        try:
            plan = classify_paths(self._drag_pending)
        except Exception as e:
            self._log(f"拖拽内容解析失败: {e}\n")
            return

        for m in plan.messages:
            self._log(f"  {m}\n")

        if plan.mode == 'single':
            self.idml_var.set(plan.idml)
            self.result_var.set(plan.result)
            self._drag_pending.clear()
            self.status_var.set("已从拖拽载入（点「开始回注」执行）")
            self._log(f"\n已从拖拽载入：\n  IDML: {os.path.basename(plan.idml)}\n"
                      f"  句读结果: {os.path.basename(plan.result)}\n"
                      "请核对后点「开始回注」。\n")

        elif plan.mode == 'single_need_result':
            self.idml_var.set(plan.idml)
            self.status_var.set("请再拖入句读结果，或点「浏览…」选择")
            self._log(f"\n已载入 IDML: {os.path.basename(plan.idml)}\n"
                      "未找到对应句读结果。请再拖入句读结果文件，"
                      "或点「浏览…」手动选择。\n")

        elif plan.mode == 'batch':
            base_dir = plan.base_dir or os.path.dirname(plan.pairs[0][0])
            self._drag_pending.clear()
            self.status_var.set("拖入批量内容，请核对列表")
            self._show_batch_confirm(base_dir, plan.pairs)

        else:  # error
            self.status_var.set("拖入内容无法识别")
            self._log("拖入内容无法识别，请检查：\n")
            for m in plan.messages:
                self._log(f"  {m}\n")
            messagebox.showwarning(
                "拖入内容无法识别",
                "未能从拖入的内容识别出可处理的文件对。\n"
                "请拖入 IDML 文件（.idml）、句读结果（.md/.txt）或文件夹。\n\n"
                + "\n".join(plan.messages[:5]))

    def _pick_output(self) -> None:
        """选择输出目录；随后弹出文件名输入框（默认「{IDML名}_WD注入.idml」），
        不修改则使用默认名。Entry 仍可直接编辑完整路径。"""
        dlg = filedialog.askdirectory(title="选择输出目录（随后可修改文件名）")
        if not dlg:
            return

        default_name = "输出_WD注入.idml"
        idml = self.idml_var.get().strip()
        if idml and os.path.isfile(idml):
            default_name = os.path.splitext(os.path.basename(idml))[0] \
                + "_WD注入.idml"

        name = simpledialog.askstring(
            "输出文件名",
            f"输出目录:\n{dlg}\n\n"
            f"输出文件名（留空使用默认「{default_name}」）:",
            initialvalue=default_name,
            parent=self.root)
        if name is None:  # 用户取消
            return
        name = name.strip() or default_name
        if not name.lower().endswith('.idml'):
            name += '.idml'
        self.output_var.set(os.path.join(dlg, name))

    def _open_output_dir(self) -> None:
        dlg = filedialog.askdirectory(title="选择要打开的文件夹")
        if not dlg:
            return
        try:
            os.startfile(dlg)  # noqa: S606  （仅 Windows 打包环境）
        except Exception as e:
            self._log(f"无法打开文件夹: {e}\n")

    # ── 单文件回注 ──
    def _start_single(self) -> None:
        if self.busy:
            return
        idml = self.idml_var.get().strip()
        result = self.result_var.get().strip()
        output = self.output_var.get().strip() or None

        err = check_idml_valid(idml)
        if err:
            messagebox.showerror("错误", err)
            return
        if not os.path.isfile(result):
            messagebox.showerror("错误", f"句读结果文件不存在:\n{result}")
            return

        if output is None:
            output = os.path.splitext(idml)[0] + "_WD注入.idml"
        if os.path.abspath(output) == os.path.abspath(idml):
            messagebox.showerror("错误", "输出文件不能与 IDML 文件同路径（会覆盖源文件）")
            return

        if os.path.exists(output):
            choice = messagebox.askyesnocancel(
                "输出文件已存在",
                f"输出文件已存在:\n{output}\n\n"
                f"「是」= 覆盖；「否」= 自动重命名 _v2；「取消」= 中止")
            if choice is None:
                return
            if not choice:
                resolved = inject._resolve_output_path(output, 'rename_v2')
                if not resolved:
                    return
                self._log(f"输出文件已存在，自动重命名为: "
                          f"{os.path.basename(resolved)}\n")
                output = resolved

        self._log(f"输入 IDML: {idml}\n句读结果: {result}\n输出文件: {output}\n")
        self._run_worker(lambda: inject.process(idml, result, output))

    # ── 批量处理 ──
    def _start_batch(self) -> None:
        if self.busy:
            return
        base = filedialog.askdirectory(
            title="选择待处理文件夹（内含 IDML 与句读结果，文件名以经号开头）")
        if not base:
            return

        # 配对在主线程执行（很快）；find_pairs_in_dir 内部 print 警告，
        # 打包后 sys.stdout 可能为 None，临时替换为静默 writer 防崩溃。
        old_out = sys.stdout
        sys.stdout = NullWriter()
        try:
            pairs = find_pairs_in_dir(base)
        except Exception as e:
            sys.stdout = old_out
            messagebox.showerror("错误", str(e))
            return
        sys.stdout = old_out

        if not pairs:
            messagebox.showerror(
                "批量处理",
                "该目录下没有找到可处理的文件对。\n"
                "请确认：文件名以经号数字开头（如 497导出.idml + 497句读结果.md），\n"
                "且同经号同时存在 .idml 与 .md/.txt 句读结果。")
            return

        self._show_batch_confirm(base, pairs)

    def _show_batch_confirm(self, base_dir: str,
                            pairs: list[tuple[str, str, str]]) -> None:
        """待处理列表确认窗口：可改输出目录，确认后才开始处理。"""
        dlg = tk.Toplevel(self.root)
        dlg.title("批量处理确认")
        dlg.geometry("820x480")
        dlg.minsize(700, 400)
        dlg.transient(self.root)
        dlg.grab_set()

        # ── 输出设置区 ──
        out_frame = ttk.LabelFrame(dlg, text="输出设置")
        out_frame.pack(fill='x', padx=10, pady=(10, 4))
        out_var = tk.StringVar(value=os.path.join(base_dir, "output"))
        ttk.Label(out_frame, text="输出目录").grid(
            row=0, column=0, sticky='w', padx=6, pady=6)
        ttk.Entry(out_frame, textvariable=out_var).grid(
            row=0, column=1, sticky='ew', padx=6, pady=6)
        ttk.Button(out_frame, text="浏览…", width=8,
                   command=lambda: self._pick_batch_outdir(out_var)
                   ).grid(row=0, column=2, padx=6, pady=6)
        out_frame.columnconfigure(1, weight=1)
        ttk.Label(out_frame,
                  text="留空 = 输入目录下的 output 子目录；输出文件自动命名"
                  "「经号导出_WD注入.idml」，同名自动 _v2 重命名，绝不覆盖原文件。",
                  foreground='#888888').grid(
            row=1, column=1, columnspan=2, sticky='w', padx=6, pady=(0, 6))

        # ── 待处理列表区 ──
        list_frame = ttk.LabelFrame(
            dlg, text=f"待处理列表（{len(pairs)} 对，请核对后开始）")
        list_frame.pack(fill='both', expand=True, padx=10, pady=4)
        tree = ttk.Treeview(list_frame, columns=("num", "idml", "md", "out"),
                            show="headings", height=10)
        tree.heading("num", text="经号")
        tree.heading("idml", text="IDML 文件")
        tree.heading("md", text="句读结果")
        tree.heading("out", text="输出文件")
        tree.column("num", width=60, anchor='center', stretch=False)
        tree.column("idml", width=230)
        tree.column("md", width=230)
        tree.column("out", width=210)
        vsb = ttk.Scrollbar(list_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky='nsew', padx=(4, 0), pady=4)
        vsb.grid(row=0, column=1, sticky='ns', padx=(0, 4), pady=4)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        def _refresh_out_col() -> None:
            """输出目录变化时刷新「输出文件」列（含 _v2 冲突预览）。"""
            out_dir = out_var.get().strip() or os.path.join(base_dir, "output")
            for iid, (idml, md, num) in zip(tree.get_children(), pairs):
                p = os.path.join(out_dir, f"{num}导出_WD注入.idml")
                if os.path.exists(p):
                    p = inject._resolve_output_path(p, 'rename_v2') or p
                tree.item(iid, values=(
                    num, os.path.basename(idml), os.path.basename(md),
                    os.path.basename(p)))

        for idml, md, num in pairs:
            p = os.path.join(out_var.get(), f"{num}导出_WD注入.idml")
            if os.path.exists(p):
                p = inject._resolve_output_path(p, 'rename_v2') or p
            tree.insert("", "end", values=(
                num, os.path.basename(idml), os.path.basename(md),
                os.path.basename(p)))
        out_var.trace_add("write", lambda *_: _refresh_out_col())

        # ── 底部按钮 ──
        btns = ttk.Frame(dlg)
        btns.pack(fill='x', padx=10, pady=(4, 10))
        ttk.Button(btns, text="取消", width=10,
                   command=dlg.destroy).pack(side='left')
        ttk.Button(btns, text="开始处理", width=12,
                   command=lambda: self._confirm_batch(
                       dlg, base_dir, out_var.get().strip(), pairs)
                   ).pack(side='right')

    def _pick_batch_outdir(self, out_var: tk.StringVar) -> None:
        cur = out_var.get().strip()
        initial = cur if cur and os.path.isdir(cur) else None
        dlg = filedialog.askdirectory(title="选择输出目录", initialdir=initial)
        if dlg:
            out_var.set(dlg)

    def _confirm_batch(self, dlg, base_dir: str, out_dir: str,
                       pairs: list[tuple[str, str, str]]) -> None:
        out_dir = out_dir or os.path.join(base_dir, "output")
        dlg.destroy()
        self._log(f"批量处理目录: {base_dir}\n输出目录: {out_dir}\n")
        self._run_worker(lambda: run_batch_process(base_dir, out_dir, pairs))

    def _batch_worker(self, base_dir: str, out_dir: str,
                      pairs: list[tuple[str, str, str]]) -> None:
        """兼容旧调用签名（如外部测试直接调用）。"""
        run_batch_process(base_dir, out_dir, pairs)

    # ── 后台任务执行与日志刷新 ──
    def _run_worker(self, target) -> None:
        self.busy = True
        self._set_busy(True)
        self.status_var.set("处理中…")
        q: queue.Queue = queue.Queue()
        done_evt = threading.Event()  # worker 结束信号（防 DONE 被节流延迟）

        def run() -> None:
            old_out, old_err = sys.stdout, sys.stderr
            sys.stdout = QueueWriter(q)
            sys.stderr = QueueWriter(q)
            try:
                target()
                q.put(("__DONE__", None))
            except Exception:
                q.put(("__ERROR__", traceback.format_exc()))
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                done_evt.set()

        threading.Thread(target=run, daemon=True).start()
        self._poll_queue(q, done_evt)

    def _poll_queue(self, q: queue.Queue, done_evt: threading.Event) -> None:
        """节流消费日志队列（P3-15）。

        每次最多取 POLL_BATCH 条，且批量拼接后只调用一次 _log——
        保证主线程每 100ms 必然返回事件循环处理窗口消息，窗口保持响应。
        """
        batch: list[str] = []
        for _ in range(POLL_BATCH):
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and item[0] in ("__DONE__", "__ERROR__"):
                if batch:
                    self._log("".join(batch))
                self._drain_tail(q, item)
                return
            batch.append(item)
        if batch:
            self._log("".join(batch))

        if done_evt.is_set():
            # worker 已结束：清空剩余日志后收尾（DONE 一定已在队列中）
            self._drain_tail(q, None)
            return
        self.root.after(100, lambda: self._poll_queue(q, done_evt))

    def _drain_tail(self, q: queue.Queue, done_item) -> None:
        """收尾：一次性消费完剩余日志与完成标记。"""
        tail: list[str] = []
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and item[0] in ("__DONE__", "__ERROR__"):
                done_item = item
                break
            tail.append(item)
        if tail:
            self._log("".join(tail))
        if done_item is None:  # 极端兜底：事件置位但标记未入队
            done_item = ("__DONE__", None)
        self._finish_worker(done_item)

    def _finish_worker(self, item) -> None:
        if item[0] == "__ERROR__":
            self.status_var.set("处理失败")
            self._log("\n" + item[1])
            messagebox.showerror("处理失败", "处理过程中出现错误，详见日志区。")
        else:
            self.status_var.set("完成")
            self._log("\n处理完成。\n")
        self._set_busy(False)
        self.busy = False

    def _set_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        self.btn_single.configure(state=state)
        self.btn_batch.configure(state=state)
        self.root.configure(cursor='watch' if busy else '')

    # ── 日志 ──
    def _log(self, text: str) -> None:
        # \r 进度行在 Tk 文本控件中会显示为换行（P3-15），清理为普通行
        text = text.replace('\r', '')
        if not text:
            return
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text)
        # 日志区有界：超过 MAX_LOG_LINES 行删除最前面的行，防止 ScrolledText
        # 无限膨胀导致 insert/see('end') 越来越慢（无响应加剧因素）。
        line_count = int(self.log_text.index('end-1c').split('.')[0])
        if line_count > MAX_LOG_LINES:
            self.log_text.delete('1.0', f'{line_count - MAX_LOG_LINES}.0')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')


# ─────────────────────────── 窗口内拖拽（纯 ctypes + WM_DROPFILES） ───────────────────────────

class _DragDropHelper:
    """窗口内文件拖拽（Windows 原生 WM_DROPFILES，零第三方依赖）。

    实现：子类化 Tk 顶层窗口的 WndProc 接收 WM_DROPFILES 消息，
    用 DragQueryFileW（宽字符，中文路径无乱码）枚举全部释放路径，
    经 root.after(0, ...) 抛到 Tk 主线程后交给 app.handle_dropped_paths。

    取舍（方案 v1.5.5）：WM_DROPFILES 是「释放即回调」机制，拖入过程中
    无预览高亮（DragEnter 反馈需 OLE IDropTarget，复杂度高，留待后续）。

    失败策略：初始化异常/非 Windows 时静默降级（拖拽不可用不影响 GUI 其他功能）。
    """

    WM_DROPFILES = 0x0233
    GWLP_WNDPROC = -4

    def __init__(self, app) -> None:
        self.app = app
        self._hwnd = None
        self._old_wndproc = None
        self._new_wndproc = None  # 强引用防 GC（子类化回调必须存活）
        self._attach(app.root)

    def _attach(self, root) -> None:
        if os.name != 'nt':
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            raw_hwnd = root.winfo_id()
            if not raw_hwnd:
                return
            # 取顶层窗口句柄（winfo_id 返回 wrapper，GA_ROOT 兜底）
            user32.GetAncestor.restype = wintypes.HWND
            hwnd = user32.GetAncestor(raw_hwnd, 2) or raw_hwnd
            self._hwnd = hwnd

            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint,
                wintypes.WPARAM, wintypes.LPARAM)

            def _wndproc(h, msg, wp, lp):
                if msg == self.WM_DROPFILES:
                    paths = self._query_files(wp)
                    if paths:
                        root.after(0, lambda: self.app.handle_dropped_paths(paths))
                if self._old_wndproc is not None:
                    return self._old_wndproc(h, msg, wp, lp)
                return 0

            self._new_wndproc = WNDPROC(_wndproc)
            # SetWindowLongPtrW 必须显式声明类型（默认 c_int 会截断 64 位指针；
            # WINFUNCTYPE 实例需经 c_void_p 转换才能传参）
            user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
            user32.SetWindowLongPtrW.argtypes = [
                wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            old = user32.SetWindowLongPtrW(
                hwnd, self.GWLP_WNDPROC,
                ctypes.cast(self._new_wndproc, ctypes.c_void_p))
            if not old:
                self._new_wndproc = None
                return
            self._old_wndproc = ctypes.cast(old, WNDPROC)
            # 拖拽相关 Win32 函数位于 shell32.dll（DragAcceptFiles/DragQueryFile/DragFinish）
            shell32.DragAcceptFiles(hwnd, True)
        except Exception as e:  # noqa: BLE001  （降级：拖拽不可用不影响 GUI）
            self._hwnd = None
            self._old_wndproc = None
            self._new_wndproc = None
            print(f"[拖拽] 窗口拖拽初始化失败（不影响使用）: {e}")

    def _query_files(self, hdrop) -> list[str]:
        """枚举 HDROP 中的全部文件路径（宽字符）并释放资源。"""
        import ctypes
        from ctypes import wintypes

        shell32 = ctypes.windll.shell32
        # 声明类型防 64 位 HDROP 指针被默认 c_int 截断
        shell32.DragQueryFileW.restype = ctypes.c_uint
        shell32.DragQueryFileW.argtypes = [
            wintypes.HANDLE, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        shell32.DragFinish.argtypes = [wintypes.HANDLE]
        n = shell32.DragQueryFileW(hdrop, -1, None, 0)
        paths: list[str] = []
        for i in range(n):
            buf_len = shell32.DragQueryFileW(hdrop, i, None, 0)
            buf = ctypes.create_unicode_buffer(buf_len + 1)
            shell32.DragQueryFileW(hdrop, i, buf, buf_len + 1)
            paths.append(buf.value)
        shell32.DragFinish(hdrop)
        return paths


def run() -> int:
    """启动 GUI（供 launcher.py 调用）。"""
    root = tk.Tk()
    InjectApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
