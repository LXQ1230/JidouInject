#!/usr/bin/env python3
"""WM_DROPFILES 高保真冒烟：SendMessage 构造真实 HDROP 模拟窗口拖拽。

覆盖链路：SendMessage(WM_DROPFILES) → 子类化 WndProc → DragQueryFileW
→ root.after(0) → handle_dropped_paths → classify_paths 分流。
（仅 Windows + 有 tkinter 环境可运行；真实 OLE 拖拽的最终人工验收另行执行。）

场景：
1. 两个文件乱序拖入 → single 自动配对填表
2a. 只拖 IDML（无结果）→ need_result 保留 pending
2b. 再拖结果文件 → 与 pending 合并 → single 填表
3. 拖入文件夹 → 批量确认窗口弹出
4. busy 状态下拖入 → 忽略
"""
import ctypes
import os
import sys
import tempfile
from ctypes import wintypes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import gui_inject as g  # noqa: E402

GMEM_MOVEABLE = 0x0002
GMEM_ZEROINIT = 0x0040
WM_DROPFILES = 0x0233


class DROPFILES(ctypes.Structure):
    _fields_ = [
        ("pFiles", ctypes.c_uint32),   # 文件列表偏移
        ("pt", ctypes.c_long * 2),     # POINT
        ("fNC", ctypes.c_int32),       # 非客户区
        ("fWide", ctypes.c_int32),     # 1 = Unicode 路径
    ]


def build_hdrop(paths):
    """构造 HDROP（DROPFILES 头 + UTF-16 路径序列），返回句柄。"""
    kernel32 = ctypes.windll.kernel32
    # 显式声明类型，防止 64 位句柄/指针被默认 c_int 截断或溢出
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    payload = b"".join(
        p.encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
    size = ctypes.sizeof(DROPFILES) + len(payload)
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, size)
    ptr = kernel32.GlobalLock(h)
    if not ptr:
        raise RuntimeError("GlobalLock 失败")
    df = DROPFILES()
    df.pFiles = ctypes.sizeof(DROPFILES)
    df.fWide = 1
    ctypes.memmove(ptr, ctypes.byref(df), ctypes.sizeof(df))
    ctypes.memmove(ctypes.c_void_p(ptr + df.pFiles), payload, len(payload))
    kernel32.GlobalUnlock(h)
    return h


def send_drop(helper, paths):
    """向已注册拖拽的窗口发送 WM_DROPFILES（同步；DragFinish 由 wndproc 内执行释放）。"""
    user32 = ctypes.windll.user32
    # 声明类型防 64 位句柄溢出（wParam 接收 HDROP 指针）
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [
        wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    h = build_hdrop(paths)
    user32.SendMessageW(helper._hwnd, WM_DROPFILES, h, 0)


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="jd_smoke_")
    idml = os.path.join(tmp, "555导出.idml")
    res = os.path.join(tmp, "555句读结果.md")
    idml2 = os.path.join(tmp, "666导出.idml")   # 无结果 → need_result 场景
    res2 = os.path.join(tmp, "666句读结果.md")   # 场景 2b 前创建
    with open(idml, "w", encoding="utf-8") as f:
        f.write("")
    with open(res, "w", encoding="utf-8") as f:
        f.write("")
    with open(idml2, "w", encoding="utf-8") as f:
        f.write("")

    root = g.tk.Tk()
    app = g.InjectApp(root)
    results: dict[str, bool] = {}

    if app._drag_helper._hwnd is None:
        print("  [前置] 拖拽初始化失败，冒烟中止")
        root.destroy()
        return 1

    def check_single():
        # 场景 1：乱序拖入（结果在前、IDML 在后）
        send_drop(app._drag_helper, [res, idml])
        root.after(300, check_single2)

    def check_single2():
        ok = (app.idml_var.get() == idml and app.result_var.get() == res
              and not app._drag_pending)
        print("  [场景1] 乱序拖入 → single 填表:", "OK" if ok else "FAIL")
        results["s1"] = ok
        app.idml_var.set("")
        app.result_var.set("")
        app._drag_pending.clear()
        # 场景 2a：拖入无结果的 IDML（666 目录内无对应结果）
        send_drop(app._drag_helper, [idml2])
        root.after(300, check_need)

    def check_need():
        ok = (app.idml_var.get() == idml2 and app.result_var.get() == ""
              and len(app._drag_pending) == 1)
        print("  [场景2a] 只拖无结果 IDML → need_result 保留:", "OK" if ok else "FAIL")
        results["s2a"] = ok
        # 场景 2b：创建 666 结果文件后补拖 → 与 pending 合并
        with open(res2, "w", encoding="utf-8") as f:
            f.write("")
        send_drop(app._drag_helper, [res2])
        root.after(300, check_merge)

    def check_merge():
        ok = (app.idml_var.get() == idml2 and app.result_var.get() == res2
              and not app._drag_pending)
        print("  [场景2b] 补拖结果 → 合并载入:", "OK" if ok else "FAIL")
        results["s2b"] = ok
        # 场景 3：拖入文件夹（此时含 555、666 两对）→ 批量确认窗
        app._drag_pending.clear()
        send_drop(app._drag_helper, [tmp])
        root.after(400, check_batch)

    def check_batch():
        dlgs = [w for w in root.winfo_children()
                if isinstance(w, g.tk.Toplevel)]
        ok = bool(dlgs)
        print("  [场景3] 拖文件夹(2对) → 批量确认窗:", "OK" if ok else "FAIL")
        results["s3"] = ok
        for d in dlgs:
            d.destroy()
        # 场景 4：busy 忽略
        app.idml_var.set("")
        app.busy = True
        send_drop(app._drag_helper, [idml, res])
        root.after(300, check_busy)

    def check_busy():
        ok = app.idml_var.get() == ""  # busy 时表单未被修改
        print("  [场景4] busy 忽略拖入:", "OK" if ok else "FAIL")
        results["s4"] = ok
        root.quit()

    root.after(200, check_single)
    root.after(8000, root.quit)  # 兜底超时
    root.mainloop()
    root.destroy()

    failed = [k for k, v in results.items() if not v]
    if failed or not results:
        print("\n冒烟失败:", failed or "无任何场景执行")
        return 1
    print("\n全部冒烟通过 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
