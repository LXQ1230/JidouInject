#!/usr/bin/env python3
"""CLI 拖拽模式集成测试：subprocess 调用 launcher.py 模拟拖入 2 个文件。"""
import os
import shutil
import subprocess
import sys
import tempfile

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CODE_DIR)
PY = r"C:\Users\Admin\.workbuddy\binaries\python\envs\pack312\Scripts\python.exe"


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="jd_cli_test_", dir=ROOT)
    try:
        idml_src = os.path.join(ROOT, "275_old_test.idml")
        md_src = os.path.join(ROOT, "done", "275", "275从ID中导出文字_WD句读结果.md")
        idml = os.path.join(tmp, "275_old_test.idml")
        md = os.path.join(tmp, "275结果.md")
        shutil.copy2(idml_src, idml)
        shutil.copy2(md_src, md)

        print(f"[测试] 拖拽模式: {os.path.basename(idml)} + {os.path.basename(md)}")
        env = dict(os.environ)
        # JIDOU_NO_CONSOLE=1: 沙箱测试环境跳过 AllocConsole（保留管道输出捕获）
        env["JIDOU_NO_CONSOLE"] = "1"
        # 无 TTY 环境，input() 将收到 EOF → 正常跳过
        proc = subprocess.run(
            [PY, os.path.join(CODE_DIR, "launcher.py"), idml, md],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
            stdin=subprocess.DEVNULL, env=env)
        print("--- stdout（尾部 3000 字符） ---")
        print(proc.stdout[-3000:])
        print("--- stderr（尾部 1500 字符） ---")
        print(proc.stderr[-1500:])
        print(f"exit code = {proc.returncode}")

        out = os.path.join(tmp, "275_old_test_WD注入.idml")
        if not os.path.isfile(out):
            print("[失败] 未生成输出文件:", out)
            return 1
        size = os.path.getsize(out)
        print(f"[通过] 输出文件已生成: {os.path.basename(out)} ({size} bytes)")

        # 与 python 直接运行 inject.py 的输出做字节级对比（回归依据）
        ref = os.path.join(tmp, "ref_WD注入.idml")
        ref_proc = subprocess.run(
            [PY, "-X", "utf8", os.path.join(CODE_DIR, "inject.py"),
             "--idml", idml, "--result", md, "--output", ref],
            capture_output=True, text=True, encoding="utf-8", timeout=300,
            stdin=subprocess.DEVNULL, env=env)
        print(f"reference exit = {ref_proc.returncode}")
        if ref_proc.returncode != 0:
            print("[失败] 参考运行失败:", ref_proc.stdout[-500:], ref_proc.stderr[-500:])
            return 1
        with open(out, "rb") as f1, open(ref, "rb") as f2:
            a, b = f1.read(), f2.read()
        if a == b:
            print(f"[通过] 输出与 python 直接运行字节级一致 ({size} bytes)")
        else:
            print(f"[警告] 字节不一致: launcher={len(a)} ref={len(b)}，"
                  f"尝试内容级对比…")
            return 2
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
