#!/usr/bin/env python3
"""IDML 句读回注工具 — 统一入口（图形界面 / 拖拽命令行 双模式）。

用法：
    双击运行           → 打开图形界面（GUI）
    拖入文件/文件夹     → 命令行模式直接回注（见 drag_input.classify_paths 识别规则）
    --idml x --result y → 命令行模式（老用法，保留交互式冲突处理）

设计说明（Nuitka windowed 打包）：
- 打包为 GUI 子系统 exe（无黑窗），双击时直接进入 tkinter 界面；
- 拖拽场景下通过 AllocConsole 动态创建控制台窗口显示处理进度，
  处理结束按回车关闭，保证使用者能看到结果。
- 拖拽回注（run_cli）为去交互设计：输出冲突自动 _v2 重命名，绝不覆盖。
"""

import os
import sys
import time
import traceback

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


def _log_fallback(msg: str) -> None:
    """GUI/无控制台环境下把关键信息写入日志文件（诊断兜底，绝不抛错）。"""
    try:
        log_path = os.path.join(os.environ.get('TEMP', '.'),
                                'jd_inject_error.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _alloc_console() -> None:
    """windowed 模式下动态创建控制台窗口并重定向标准流（拖拽/命令行使用）。"""
    # 测试/CI 环境开关：保留现有 stdout/stderr 便于捕获输出
    if os.environ.get('JIDOU_NO_CONSOLE') == '1':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        if not kernel32.GetConsoleWindow():
            kernel32.AllocConsole()
        # CONOUT$/CONIN$ 直接指定 UTF-8，避免 GBK 编码错误与中文乱码
        sys.stdout = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
        sys.stderr = open('CONOUT$', 'w', encoding='utf-8', errors='replace')
        sys.stdin = open('CONIN$', 'r', encoding='utf-8', errors='replace')
    except Exception:
        # 非 Windows 或失败时静默降级（print 输出将被丢弃，不影响主流程）
        pass


def _wait_enter(prompt: str = "按回车键关闭窗口...") -> None:
    """等待回车；非交互/无效 stdin 时静默跳过。"""
    try:
        input(prompt)
    except (EOFError, OSError):
        pass


def _extract_cli_pair(args: list[str]) -> tuple[str, str] | None:
    """识别 --idml/--result 显式参数对（老命令行用法）。

    仅当两个参数都存在时返回；文件存在性由 inject.main() 自行校验。
    """
    idml = result = None
    i = 0
    while i < len(args):
        if args[i] == '--idml' and i + 1 < len(args):
            idml = args[i + 1]
            i += 2
        elif args[i] == '--result' and i + 1 < len(args):
            result = args[i + 1]
            i += 2
        else:
            i += 1
    return (idml, result) if idml and result else None


def run_cli_legacy(idml_path: str, result_path: str) -> int:
    """显式参数模式：走 inject.main() 完整校验（含交互式冲突处理）。"""
    import inject

    sys.argv = [sys.argv[0], '--idml', idml_path, '--result', result_path]
    code = 0
    try:
        inject.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        print(f"\n未预期的错误: {e}")
        traceback.print_exc()
        code = 1

    _wait_enter("\n处理结束，按回车键关闭窗口...")
    return code


def run_cli(idml_path: str, result_path: str) -> int:
    """拖拽单对回注（去交互）：校验 + 冲突自动 _v2 重命名 + inject.process()。

    与批量处理口径一致：输出文件绝不覆盖，已存在则自动加 _v2 后缀。
    """
    import inject
    import gui_inject

    err = gui_inject.check_idml_valid(idml_path)
    if err:
        print(err)
        _wait_enter()
        return 1
    if not os.path.isfile(result_path):
        print(f"错误: 句读结果文件不存在:\n{result_path}")
        _wait_enter()
        return 1

    out_path = os.path.splitext(idml_path)[0] + "_WD注入.idml"
    if os.path.exists(out_path):
        resolved = inject._resolve_output_path(out_path, 'rename_v2')
        if not resolved:
            print("错误: 无法生成输出路径（输出文件冲突）。")
            _wait_enter()
            return 1
        print(f"输出文件已存在，自动重命名: {os.path.basename(resolved)}")
        out_path = resolved

    print(f"输入 IDML: {idml_path}")
    print(f"句读结果: {result_path}")
    print(f"输出文件: {out_path}\n")

    try:
        inject.process(idml_path, result_path, out_path)
    except Exception as e:
        print(f"\n处理失败: {e}")
        traceback.print_exc()
        _wait_enter()
        return 1

    _wait_enter("\n处理结束，按回车键关闭窗口...")
    return 0


def run_batch_cli(plan) -> int:
    """拖拽批量回注：复用 gui_inject.run_batch_process（自动 _v2，零交互）。"""
    import gui_inject

    pairs = plan.pairs
    base_dir = plan.base_dir or os.path.dirname(pairs[0][0])
    out_dir = os.path.join(base_dir, "output")
    results = gui_inject.run_batch_process(base_dir, out_dir, pairs)
    ok = sum(1 for _, s, _ in results if s == "成功")
    _wait_enter("\n批量处理结束，按回车键关闭窗口...")
    return 0 if ok else 1


def _pick_result_dialog(idml_hint: str | None) -> str | None:
    """弹窗选择句读结果文件（拖拽缺结果时兜底）；取消返回 None。"""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="选择句读结果文件",
            filetypes=[("文本文件", "*.md *.txt"), ("所有文件", "*.*")],
            initialdir=os.path.dirname(idml_hint) if idml_hint else None)
        root.destroy()
        return path or None
    except Exception:
        return None


def run_drag(paths: list[str]) -> int:
    """拖拽入口：classify_paths 分流（single / need_result / batch / error）。"""
    from drag_input import classify_paths

    plan = classify_paths(paths)
    for m in plan.messages:
        print(m)

    if plan.mode == 'single':
        print(f"\n输入 IDML: {plan.idml}\n句读结果: {plan.result}")
        return run_cli(plan.idml, plan.result)

    if plan.mode == 'single_need_result':
        print(f"\n输入 IDML: {plan.idml}\n未找到对应句读结果，请手动选择。")
        result = _pick_result_dialog(plan.idml)
        if not result:
            print("已取消。")
            _wait_enter("\n按回车键退出...")
            return 1
        print(f"句读结果: {result}\n")
        return run_cli(plan.idml, result)

    if plan.mode == 'batch':
        print(f"待处理 {len(plan.pairs)} 对。\n")
        return run_batch_cli(plan)

    # error
    print("错误: 拖入内容无法处理。")
    _wait_enter("\n按回车键退出...")
    return 1


def main() -> int:
    args = sys.argv[1:]

    # 1) 显式 --idml/--result 参数（老命令行用法，保留交互式冲突处理）
    cli_pair = _extract_cli_pair(args)
    if cli_pair:
        _alloc_console()
        return run_cli_legacy(*cli_pair)

    # 2) 拖拽路径模式（文件或文件夹，任意数量与顺序）
    paths = [a for a in args if os.path.exists(a)]
    if paths:
        _alloc_console()
        return run_drag(paths)

    # 3) 有参数但均非有效路径 → 提示
    if args:
        _alloc_console()
        print("错误: 无法识别的参数。\n"
              "请将 IDML 文件、句读结果文件或文件夹拖到本程序上；\n"
              "或使用命令行参数 --idml <文件> --result <文件>。")
        _wait_enter("\n按回车键退出...")
        return 1

    # 4) 无参数 → 图形界面
    try:
        _log_fallback("GUI 启动中")
        import gui_inject
        return gui_inject.run()
    except Exception as e:
        _log_fallback("GUI 启动失败:\n" + traceback.format_exc())
        _alloc_console()
        print(f"无法启动图形界面: {e}")
        traceback.print_exc()
        _wait_enter("\n按回车键退出...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
