#!/usr/bin/env python3
"""测量 inject 全流程的峰值内存与耗时（用于各层改造对比基线）"""
import sys
import os
import time
import ctypes
import importlib.util


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_rss_mb() -> float:
    try:
        psapi = ctypes.WinDLL("psapi.dll")
        kernel32 = ctypes.WinDLL("kernel32.dll")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = (
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
        pmc = PROCESS_MEMORY_COUNTERS()
        pmc.cb = ctypes.sizeof(pmc)
        handle = kernel32.GetCurrentProcess()
        psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb)
        return pmc.PeakWorkingSetSize / 1024 / 1024
    except Exception:
        return -1.0


def load_inject(module_name: str, path: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run(idml_path: str, result_path: str, output_path: str, inject_mod, tag: str):
    start = time.time()
    inject_mod.process(idml_path, result_path, output_path)
    elapsed = time.time() - start
    peak = peak_rss_mb()
    print(f"[{tag}] 耗时 {elapsed:.1f}s, 峰值内存 {peak:.0f} MB")
    return elapsed, peak


if __name__ == "__main__":
    idml = sys.argv[1]
    result = sys.argv[2]
    out = sys.argv[3]
    tag = sys.argv[4] if len(sys.argv) > 4 else "new"
    inject_path = sys.argv[5] if len(sys.argv) > 5 else "D:/Desktop/JidouInject/code/inject.py"
    inject_mod = load_inject("inject_bench", inject_path)
    run(idml, result, out, inject_mod, tag)
