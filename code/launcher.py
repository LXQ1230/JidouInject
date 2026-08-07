#!/usr/bin/env python3
"""IDML 句读回注工具 — 统一入口（图形界面 / 拖拽命令行 双模式）。

用法：
    双击运行           → 打开图形界面（GUI）
    拖入 2 个文件       → 命令行模式直接回注（第 1 个为 IDML，第 2 个为句读结果）

设计说明（Nuitka windowed 打包）：
- 打包为 GUI 子系统 exe（无黑窗），双击时直接进入 tkinter 界面；
- 拖拽场景下通过 AllocConsole 动态创建控制台窗口显示处理进度，
  处理结束按回车关闭，保证使用者能看到结果。
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


def _is_existing_file(p: str) -> bool:
    return bool(p) and os.path.isfile(p)


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


def run_cli(idml_path: str, result_path: str) -> int:
    """拖拽模式：复用 inject.main() 的完整校验与处理逻辑。"""
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


def main() -> int:
    args = sys.argv[1:]

    # 拖拽 ≥2 个文件 → 命令行回注（取前两个：IDML + 句读结果）
    if len(args) >= 2 and _is_existing_file(args[0]) and _is_existing_file(args[1]):
        _alloc_console()
        return run_cli(args[0], args[1])

    # 只拖入 1 个文件 → 提示并退出
    if len(args) == 1 and _is_existing_file(args[0]):
        _alloc_console()
        print("错误：请同时拖入两个文件。\n"
              "第 1 个：IDML 文件；第 2 个：句读结果（.md / .txt）。")
        _wait_enter("\n按回车键退出...")
        return 1

    # 无参数 → 图形界面
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
