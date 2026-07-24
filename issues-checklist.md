# JidouInject 待处理问题清单

> 基于 2026-07-24 第二轮项目检查 | 已处理 5 项，剩余 17 项
> 最后更新: 2026-07-24 | GitHub: https://github.com/LXQ1230/JidouInject | 默认分支: main

---

## 🔴 高优先级（3 项）

### 13. inject.py 偏大（1600 行）
- **当前状态**: 1600 行，超过 800 行编码规范上限（2x）
- **风险**: 单一文件维护困难，修改一处可能影响全局
- **方案**: 拆分为 5 个模块
  - `code/extract.py` — IDML 解析与文字提取（~250 行）
  - `code/align.py` — 验证与字符级对齐（~200 行）
  - `code/rebuild.py` — XML 重建与 Br/Group 规则（~500 行）
  - `code/verify.py` — 六层输出验证（~300 行）
  - `code/inject.py` — 主流程 + CLI 入口（~200 行）
- **依赖**: 需先修复测试（#14），确保重构不引入回归

### 14. 测试在 Windows 上崩溃
- **当前状态**: `test_verify_inject.py` 因 `UnicodeEncodeError` 无法运行
- **根因**: Windows 控制台默认 GBK 编码，无法输出 `✓`、`✗` 等 Unicode 符号
- **修复方案**（二选一）:
  ```python
  # 方案 A: 入口处设置
  import sys
  sys.stdout.reconfigure(encoding='utf-8')
  
  # 方案 B: 环境变量
  # 运行前执行: set PYTHONIOENCODING=utf-8
  ```
- **建议**: 方案 A（代码内修复，不依赖运行环境）

### 15. 37MB 二进制文件已追踪 ✅
- **状态**: 已在本次会话中处理（`git rm --cached` + `.gitignore` 更新）
- **遗留**: 旧 commit 中仍有二进制历史，如需彻底清理需 `git filter-branch` 或 `bfg-repo-cleaner`
- **建议**: 不紧急，GitHub 推送前处理即可

---

## 🟡 中优先级（7 项）

### 6. 类型注解不完整
- **涉及文件**: `code/inject.py`
- **缺失函数**:
  - `main()` (line 217) — 需添加 `def main() -> None:`
  - `process(idml_path, result_path, output_path)` (line 1554) — 需添加完整注解
- **工作量**: 5 分钟

### 7. print() 替代 logging
- **涉及文件**: `code/inject.py`
- **现状**: 20+ `print()` 调用用于状态输出和错误
- **规范要求**: 生产代码使用 `logging` 模块
- **方案**:
  ```python
  import logging
  logging.basicConfig(level=logging.INFO, format='%(message)s')
  logger = logging.getLogger(__name__)
  # print("错误: ...") → logger.error("...")
  # print("处理完成") → logger.info("处理完成")
  ```
- **工作量**: 30 分钟
- **注意事项**: CLI 交互式输入（冲突处理菜单）仍需保留 `print()`/`input()`

### 10. 无 requirements.txt
- **现状**: 目前仅依赖 Python 标准库
- **建议**: 创建并注明"纯标准库"，未来如有依赖可及时更新
- **额外建议**: 同时创建 `.python-version`（内容：`3.11`）

### 16. `.agents/skills/` 与 `.claude/skills/` 重复
- **现状**: `.claude/skills/` 已删除（本次提交），但 `.agents/skills/` 含完整副本
- **是否保留**: 取决于是否需要 `.agents/skills/` 目录（某些工具可能读取此路径）
- **建议**: 确认是否有工具依赖 `.agents/skills/`，如无则删除

### 19. 无 CI/CD
- **现状**: 测试需手动运行，无自动化
- **建议**: 创建 `.github/workflows/test.yml`
  ```yaml
  name: Test
  on: [push, pull_request]
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: '3.11' }
        - run: python code/test_verify_inject.py
  ```
- **前提**: 测试需先能在 CI Linux 环境运行（#14 修复 + 路径适配）

### 20. 数据目录膨胀
- **现状**: `backup/` (5.2M) + `done/` (2.7M) + `injected/` (1.4M) + `source/` (28M) = 37MB
- **`.gitignore` 已添加**: `injected/`、`done/`、`backup/`、`*.idml`、`*.indd`
- **遗留**: `source/` 目录也在 `.gitignore` 范围内吗？当前仅排除了 `*.idml`/`*.indd`
- **建议**: 确认 `source/` 中的 IDML/indd 是否需要版本控制，不需要则一并排除

### 遗留: findings.md 中的 2 个 MEDIUM/LOW 项
- **MEDIUM**: `_rebuild_paragraph_xml()` 后缀提取中 `find('>', ...)` 返回 -1 时无防护
- **LOW**: `_find_punct_style()` 返回 None 时静默跳过（无警告）
- **来源**: `findings.md` 第 26-27 行

---

## 🟢 低优先级（7 项）

### 9. UTF-8 BOM / 编码
- **状态**: 无 BOM（✓），CRLF 行尾（Windows 正常）
- **建议**: 如需跨平台协作，考虑添加 `.editorconfig`

### 21. 无 Python 版本声明
- **建议**: 创建 `.python-version`（`3.11`）或 `pyproject.toml`

### 22. 分支 master → main ✅
- **状态**: 已在本次会话中处理

### 23. 无 `.editorconfig`
- **建议**: 统一编辑器设置（特别是 CRLF/LF 行尾、缩进）
  ```ini
  root = true
  [*]
  charset = utf-8
  end_of_line = crlf
  indent_style = space
  indent_size = 4
  [*.md]
  trim_trailing_whitespace = false
  ```

### 24. 无 `pyproject.toml`
- **建议**: 即使纯标准库也可以创建，配置 ruff/pytest 等工具
  ```toml
  [project]
  name = "jidou-inject"
  version = "1.1.0"
  requires-python = ">=3.10"
  
  [tool.ruff]
  line-length = 100
  
  [tool.pytest.ini_options]
  testpaths = ["code"]
  ```

### 25. `code/__pycache__/` 已在 `.gitignore` 中
- **状态**: ✅ 已覆盖

### 26. `inject.py` 函数 `_count_br` 重复定义
- **位置**: line 1316（`_verify_structure` 内部）和 line 1455（`_verify_br_count` 内部）
- **说明**: 两个局部函数定义相同逻辑，拆分后可提取为模块级函数

---

## 📋 建议执行顺序

### 本次已完成 ✅
- [x] 清理临时文件（`275导出_WD注入_test.idml`、`新建文本文档.txt`）
- [x] 完善 `.gitignore`（添加 `*.idml`、`*.indd`、`injected/`、`done/`、`backup/`）
- [x] Git 索引移除 30 个二进制文件
- [x] 清理 `.claude/skills/` 残留（439 文件）
- [x] 分支重命名 `master` → `main`

### 下一步（建议按序处理）
1. [ ] **修复测试崩溃**（#14）— 5 分钟，解锁后续所有验证
2. [ ] **创建 requirements.txt + .python-version**（#10 + #21）— 2 分钟
3. [ ] **补全类型注解**（#6）— 5 分钟
4. [ ] **修复 findings.md 遗留 MEDIUM 项**（find_path 返回 -1 防护）— 10 分钟
5. [ ] **拆分 inject.py**（#13）— 2-3 小时
6. [ ] **print() → logging**（#7）— 30 分钟
7. [ ] **CI/CD**（#19）— 30 分钟
8. [ ] **清理 .agents/skills/**（#16）— 确认后 1 分钟
9. [ ] **.editorconfig + pyproject.toml**（#23 + #24）— 10 分钟
