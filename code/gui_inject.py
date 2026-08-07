#!/usr/bin/env python3
"""IDML 句读回注工具 — 图形界面（tkinter，纯标准库，无第三方依赖）。

由 launcher.py 无参数启动时调用。提供两种使用方式：
  1. 单文件回注：选择 IDML + 句读结果文件（输出路径可选），一键处理。
  2. 批量处理：选择文件夹，自动按经号配对 .idml 与 .md/.txt，
     逐个回注，输出到「所选目录/output/」子目录（已存在自动 _v2 重命名，
     绝不覆盖原文件）。

核心处理复用 inject.process()，通过重定向 stdout/stderr 到线程安全队列，
在主线程轮询刷新日志区，保证 Tk 界面线程安全。
"""

import io
import os
import queue
import re
import sys
import threading
import time
import traceback
import zipfile
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import inject  # noqa: E402  （同目录核心库）

APP_TITLE = "IDML 句读回注工具 v1.5.3"

# 测试/演练文件模式：批量配对时必须排除，防止把测试产物当正式输入
_TEST_PATTERNS: tuple[str, ...] = ('_old_test', '_test')


# ─────────────────────────── 纯逻辑（不依赖 Tk，可单测） ───────────────────────────

def _extract_number(filename: str) -> str | None:
    """从文件名中提取开头的经号（数字）。"""
    m = re.match(r'^(\d+)', filename)
    return m.group(1) if m else None


def _is_excluded_test_file(f: str) -> bool:
    """判断文件名是否属于测试/演练产物（*_old_test* / *_test*）。"""
    return any(p in f for p in _TEST_PATTERNS)


def find_pairs_in_dir(base_dir: str) -> list[tuple[str, str, str]]:
    """按经号配对 IDML 与句读结果（参数化版，参考 batch_inject.find_pairs）。

    规则（与批处理脚本保持一致）：
    - IDML：*.idml（排除 _WD注入 输出与测试文件）
    - 句读结果：*.md / *.txt（凡放入即视为结果，排除 _WD注入 与测试文件）
    - 配对：文件名开头数字（经号）相同即为一对；多文件时 IDML 含「导出」优先，
      结果按文件名排序取第一个。

    Returns:
        [(idml绝对路径, 结果绝对路径, 经号), ...]
    """
    if not os.path.isdir(base_dir):
        raise FileNotFoundError(f"目录不存在: {base_dir}")

    all_files = os.listdir(base_dir)
    idml_by_number: dict[str, list[str]] = {}
    md_by_number: dict[str, list[str]] = {}

    for f in all_files:
        if f.endswith('.idml') and '_WD注入' not in f \
                and not _is_excluded_test_file(f):
            num = _extract_number(f)
            if num is None:
                print(f"警告: {f} 文件名无经号，跳过")
                continue
            idml_by_number.setdefault(num, []).append(f)

    for f in all_files:
        if (f.endswith('.md') or f.endswith('.txt')) \
                and '_WD注入' not in f \
                and not _is_excluded_test_file(f):
            num = _extract_number(f)
            if num is None:
                print(f"警告: {f} 文件名无经号，跳过")
                continue
            md_by_number.setdefault(num, []).append(f)

    pairs: list[tuple[str, str, str]] = []
    for num in sorted(idml_by_number):
        idml_list = idml_by_number[num]
        md_list = md_by_number.get(num, [])

        if not md_list:
            print(f"警告: 经号 {num} 找不到对应句读结果，跳过")
            continue

        if len(idml_list) > 1:
            pref = [f for f in idml_list if '导出' in f]
            idml_chosen = (pref or sorted(idml_list))[0]
            print(f"警告: 经号 {num} 有多个 IDML 文件 ({idml_list})，"
                  f"优先选择: {idml_chosen}")
        else:
            idml_chosen = idml_list[0]

        if len(md_list) > 1:
            md_chosen = sorted(md_list)[0]
            print(f"警告: 经号 {num} 有多个候选结果文件 ({md_list})，"
                  f"优先选择: {md_chosen}")
        else:
            md_chosen = md_list[0]

        pairs.append((
            os.path.join(base_dir, idml_chosen),
            os.path.join(base_dir, md_chosen),
            num,
        ))

    return pairs


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

        self._build_ui()
        self._log(
            "欢迎使用 IDML 句读回注工具\n"
            "────────────────────────────────────────────\n"
            "使用方式一（拖拽）：把 IDML 文件与句读结果文件同时拖到本程序\n"
            "  图标上，自动进入命令行回注模式。\n"
            "使用方式二（界面）：下方选择文件后点「开始回注」；\n"
            "  或点「批量处理…」选择文件夹自动配对处理。\n"
            "────────────────────────────────────────────\n"
        )

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
        ttk.Button(top, text="浏览…", width=8,
                   command=self._pick_output).grid(row=2, column=2, pady=(6, 0))
        ttk.Label(top, text="（留空 = 与 IDML 同目录生成“XXX_WD注入.idml”）",
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

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="选择输出 IDML 路径",
            defaultextension=".idml",
            filetypes=[("IDML 文件", "*.idml")])
        if path:
            self.output_var.set(path)

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
        self._log(f"批量处理目录: {base}\n")
        self._run_worker(lambda: self._batch_worker(base))

    def _batch_worker(self, base_dir: str) -> None:
        pairs = find_pairs_in_dir(base_dir)
        if not pairs:
            raise ValueError(
                "该目录下没有找到可处理的文件对。\n"
                "请确认：文件名以经号数字开头（如 497导出.idml + 497句读结果.md），\n"
                "且同经号同时存在 .idml 与 .md/.txt 句读结果。")

        out_dir = os.path.join(base_dir, "output")
        os.makedirs(out_dir, exist_ok=True)
        print(f"找到 {len(pairs)} 个待处理文件对，输出目录: {out_dir}\n")

        results: list[tuple[str, str, float]] = []
        for idml, md, num in pairs:
            print(f"\n[{num}] {os.path.basename(idml)} + {os.path.basename(md)}")
            out_path = os.path.join(out_dir, f"{num}导出_WD注入.idml")
            if os.path.exists(out_path):
                resolved = inject._resolve_output_path(out_path, 'rename_v2')
                if not resolved:
                    print(f"  跳过（无法生成输出路径）")
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

    # ── 后台任务执行与日志刷新 ──
    def _run_worker(self, target) -> None:
        self.busy = True
        self._set_busy(True)
        self.status_var.set("处理中…")
        q: queue.Queue = queue.Queue()

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

        threading.Thread(target=run, daemon=True).start()
        self._poll_queue(q)

    def _poll_queue(self, q: queue.Queue) -> None:
        try:
            while True:
                item = q.get_nowait()
                if isinstance(item, tuple) and item[0] in ("__DONE__", "__ERROR__"):
                    self._finish_worker(item)
                    return
                self._log(item)
        except queue.Empty:
            pass
        self.root.after(100, lambda: self._poll_queue(q))

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
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text)
        self.log_text.see('end')
        self.log_text.configure(state='disabled')


def run() -> int:
    """启动 GUI（供 launcher.py 调用）。"""
    root = tk.Tk()
    InjectApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run())
