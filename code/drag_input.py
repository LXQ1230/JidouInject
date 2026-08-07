#!/usr/bin/env python3
"""拖拽输入解析（纯逻辑，无 GUI/IO 依赖）。

exe 图标拖拽（launcher.py）与 GUI 窗口内拖拽（gui_inject.py）共用本模块，
保证识别口径唯一、可单测。

核心接口：
- classify_paths(paths) -> DragPlan  任意路径列表 → 处理计划（顺序自适应）
- find_result_for_idml(idml) -> str|None  单 IDML 自动查找句读结果
- find_pairs_in_dir(base_dir) -> list     目录内按经号配对（自 gui_inject 迁移）

识别规则（v1.5.5 方案，见 plan-drag-and-drop-2026-08-07.md）：
- 按扩展名分类（.idml / .md .txt / 目录），与拖拽顺序无关
- 排除输入：文件名含 _WD注入 / _old_test / _test（防测试产物误当输入）
- 单 IDML 无结果 → 自动查找（同名 → 同经号）→ 找不到标记 need_result
- 散文件多对 → 经号配对 → 未配对 IDML 目录内补找
- 目录 → find_pairs_in_dir 配对
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# 与 gui_inject._TEST_PATTERNS 口径一致（防测试产物误当正式输入）
_TEST_PATTERNS: tuple[str, ...] = ('_old_test', '_test')
_IDML_EXT: str = '.idml'
_RESULT_EXTS: tuple[str, ...] = ('.md', '.txt')


@dataclass
class DragPlan:
    """拖拽输入解析结果。

    Attributes:
        mode: single（单对，idml+result 就绪）/ single_need_result（有 IDML 缺结果）/
              batch（多对）/ error（无法处理）
        idml: single 系列：IDML 绝对路径
        result: single 系列：句读结果绝对路径（need_result 时为 None）
        pairs: batch：[(idml绝对路径, 结果绝对路径, 经号), ...]
        base_dir: batch：输出默认目录依据（首个 IDML 所在目录或拖入目录）
        messages: 警告/提示（不阻断，供调用方展示）
    """
    mode: str
    idml: str | None = None
    result: str | None = None
    pairs: list[tuple[str, str, str]] | None = None
    base_dir: str | None = None
    messages: list[str] = field(default_factory=list)


# ─────────────────────────── 基础工具 ───────────────────────────

def _extract_number(filename: str) -> str | None:
    """从文件名中提取开头的经号（数字）。"""
    m = re.match(r'^(\d+)', filename)
    return m.group(1) if m else None


def is_excluded_input(f: str) -> bool:
    """判断文件名是否属于排除输入（测试产物 / 已注入输出）。"""
    return any(p in f for p in _TEST_PATTERNS) or '_WD注入' in f


def _is_result_file(path: str) -> bool:
    return path.lower().endswith(_RESULT_EXTS)


def _is_idml_file(path: str) -> bool:
    return path.lower().endswith(_IDML_EXT)


# ─────────────────────────── 目录内配对（自 gui_inject 迁移） ───────────────────────────

def find_pairs_in_dir(base_dir: str) -> list[tuple[str, str, str]]:
    """按经号配对目录内的 IDML 与句读结果（与批处理脚本口径一致）。

    规则：
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
        if _is_idml_file(f) and not is_excluded_input(f):
            num = _extract_number(f)
            if num is None:
                print(f"警告: {f} 文件名无经号，跳过")
                continue
            idml_by_number.setdefault(num, []).append(f)

    for f in all_files:
        if _is_result_file(f) and not is_excluded_input(f):
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


# ─────────────────────────── 单 IDML 自动查找结果 ───────────────────────────

def find_result_for_idml(idml: str) -> str | None:
    """为单个 IDML 自动查找句读结果（两级优先）。

    1. 同目录、同 basename（去扩展名）的 .md/.txt（最精确）
    2. 同目录下、同开头经号的结果文件（复用 find_pairs_in_dir 配对，取排序第一）
    3. 找不到 → None
    """
    d = os.path.dirname(idml)
    base = os.path.splitext(os.path.basename(idml))[0]

    for ext in _RESULT_EXTS:
        cand = os.path.join(d, base + ext)
        if os.path.isfile(cand):
            return cand

    num = _extract_number(os.path.basename(idml))
    if num:
        try:
            pairs = find_pairs_in_dir(d)
        except Exception:
            pairs = []
        for pidml, presult, pnum in pairs:
            if pnum == num and os.path.abspath(pidml) == os.path.abspath(idml):
                return presult
    return None


# ─────────────────────────── 散文件多对配对 ───────────────────────────

def _pair_loose_files(idmls: list[str], results: list[str],
                      messages: list[str]) -> list[tuple[str, str, str]]:
    """散文件（无目录）按经号配对（4.3 规则）。

    1. 拖入 IDML × 拖入结果按经号配对（每个结果只配一次，取排序第一）
    2. 未配对的 IDML → 在其所在目录补找（find_result_for_idml）
    3. 未使用的结果 → 警告
    """
    pairs: list[tuple[str, str, str]] = []

    # 结果按经号分组（排序稳定）
    by_num: dict[str, list[str]] = {}
    for r in sorted(results):
        num = _extract_number(os.path.basename(r))
        by_num.setdefault(num, []).append(r)

    matched_idml: set[str] = set()
    for idml in sorted(idmls):
        num = _extract_number(os.path.basename(idml))
        if num is None:
            messages.append(f"警告: {os.path.basename(idml)} 文件名无经号，无法配对")
            continue
        cand = by_num.get(num)
        if cand:
            pairs.append((idml, cand[0], num))
            by_num[num] = cand[1:]
            matched_idml.add(idml)

    # 未配对 IDML → 目录补找
    for idml in sorted(idmls):
        if idml in matched_idml:
            continue
        r = find_result_for_idml(idml)
        if r:
            num = _extract_number(os.path.basename(idml))
            pairs.append((idml, r, num))
            matched_idml.add(idml)
        else:
            messages.append(f"警告: {os.path.basename(idml)} 找不到对应句读结果，跳过")

    # 未使用结果警告
    leftover = [r for rl in by_num.values() for r in rl]
    for r in leftover:
        messages.append(f"警告: 句读结果 {os.path.basename(r)} 未配对到任何 IDML")

    return pairs


# ─────────────────────────── 主入口 ───────────────────────────

def _clean_paths(paths: list[str]) -> list[str]:
    """绝对路径化、去重、保留存在的路径。"""
    seen: set[str] = set()
    cleaned: list[str] = []
    for p in paths:
        if not p or not isinstance(p, str):
            continue
        ap = os.path.abspath(p)
        if ap in seen:
            continue
        seen.add(ap)
        if os.path.isfile(ap) or os.path.isdir(ap):
            cleaned.append(ap)
    return cleaned


def classify_paths(paths: list[str]) -> DragPlan:
    """把任意拖入路径列表解析为处理计划（顺序自适应）。

    覆盖形态：
    - 2 个文件（IDML + 结果，任意顺序）
    - 只拖 1 个 IDML（自动找结果 / 标记 need_result）
    - 批量多对散文件
    - 整个文件夹（含与散文件混合）
    """
    cleaned = _clean_paths(paths)
    if not cleaned:
        return DragPlan('error', messages=['没有可用的拖入路径（文件不存在或已删除）'])

    idmls: list[str] = []
    results: list[str] = []
    dirs: list[str] = []
    invalid: list[str] = []
    messages: list[str] = []

    for p in cleaned:
        if os.path.isdir(p):
            dirs.append(p)
        elif _is_idml_file(p):
            if is_excluded_input(os.path.basename(p)):
                messages.append(f"已排除: {os.path.basename(p)}（_WD注入输出或测试产物）")
            else:
                idmls.append(p)
        elif _is_result_file(p):
            if is_excluded_input(os.path.basename(p)):
                messages.append(f"已排除: {os.path.basename(p)}（_WD注入输出或测试产物）")
            else:
                results.append(p)
        else:
            invalid.append(os.path.basename(p))
    if invalid:
        messages.append(f"已忽略不支持的文件类型: {', '.join(invalid)}")

    # ── 目录分支：目录配对 + 散文件合并 ──
    if dirs:
        pairs: list[tuple[str, str, str]] = []
        for d in sorted(dirs):
            try:
                dp = find_pairs_in_dir(d)
            except Exception as e:  # noqa: BLE001  （目录不可读等，转警告）
                messages.append(f"目录配对失败 {d}: {e}")
                continue
            if dp:
                pairs.extend(dp)
            else:
                messages.append(f"目录 {d} 中未找到可配对的 IDML 与句读结果")
        if idmls or results:
            pairs.extend(_pair_loose_files(idmls, results, messages))
        if not pairs:
            return DragPlan('error', messages=messages or ['未找到可处理的文件对'])
        base_dir = dirs[0] if (len(dirs) == 1 and not idmls and not results) \
            else os.path.dirname(pairs[0][0])
        if len(pairs) == 1:
            return DragPlan('single', idml=pairs[0][0], result=pairs[0][1],
                            messages=messages)
        return DragPlan('batch', pairs=pairs, base_dir=base_dir, messages=messages)

    # ── 无目录分支 ──
    if len(idmls) == 1 and not results:
        # 单 IDML：自动查找结果
        r = find_result_for_idml(idmls[0])
        if r:
            return DragPlan('single', idml=idmls[0], result=r, messages=messages)
        return DragPlan('single_need_result', idml=idmls[0], messages=messages)

    if len(idmls) == 1:
        return DragPlan('single', idml=idmls[0], result=results[0], messages=messages)

    if not idmls and results:
        return DragPlan('error',
                        messages=['缺少 IDML 文件，只拖入了句读结果: '
                                  + ', '.join(os.path.basename(r) for r in sorted(results))])

    if len(idmls) > 1:
        pairs = _pair_loose_files(idmls, results, messages)
        if not pairs:
            return DragPlan('error', messages=messages or ['无法将拖入的 IDML 与句读结果配对'])
        if len(pairs) == 1:
            return DragPlan('single', idml=pairs[0][0], result=pairs[0][1],
                            messages=messages)
        return DragPlan('batch', pairs=pairs,
                        base_dir=os.path.dirname(pairs[0][0]), messages=messages)

    return DragPlan('error', messages=messages or ['拖入内容无法识别'])
