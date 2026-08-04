# JidouInject 待处理问题清单

> 基于 2026-07-24 第二轮项目检查 | 最后更新: 2026-08-04
> 状态说明：✅ 已解决 / 🔲 保持开放 / 📄 已迁移
> 2026-08-04（P3-9）：结合 fix-plan-2026-08-04.md 执行情况逐项复核

---

## 🔴 高优先级（3 项）

### 13. inject.py 偏大（2000+ 行）
- **状态**: 🔲 保持开放（大重构，风险高）
- **现状**: inject.py 2026-08-04 起约 2000 行。模块拆分（extract/align/rebuild/verify/inject）需在测试完全覆盖后谨慎进行
- **已吸收部分**: CharRecord slots dataclass、流式写回、内存释放（P2-10）已解决大经书内存问题；FIX-1~7 已修复审查发现的静默数据错误
- **前置条件**: 需先建立全量回归基准（当前 5 本经书回归 + ZIP 14 项 + 合成用例 7 项已具备）

### 14. 测试在 Windows 上崩溃 ✅
- **状态**: ✅ 已解决（2026-08-04）
- **修复**: inject.py 入口 `sys.stdout.reconfigure(encoding='utf-8')` + inject.bat/batch_inject.bat 加 `-X utf8`（P2-1）

### 15. 37MB 二进制文件已追踪 ✅
- **状态**: ✅ 已处理（git rm --cached + .gitignore）
- **遗留**: 旧 commit 历史仍含二进制，GitHub 推送前如需彻底清理可用 filter-repo（非紧急）

---

## 🟡 中优先级（7 项）

### 6. 类型注解不完整
- **状态**: 📄 部分完成
- **现状**: 新代码（CharRecord、validate_and_align、process 等）已有完整注解；旧函数（main、部分内部函数）仍缺
- **迁移**: 与模块拆分（#13）一并处理，不在当前迭代强制

### 7. print() 替代 logging
- **状态**: 📄 决策关闭（2026-08-04）
- **决策**: 保持 print()。本项目是交互式 CLI 工具（含 input() 冲突菜单），logging 会干扰交互输出；错误信息已足够详细（P3-6 增加 traceback）

### 10. 无 requirements.txt ✅
- **状态**: ✅ 已创建（2026-08-04，P3-9）
- **内容**: 注明纯标准库实现，无第三方运行时依赖

### 16. `.agents/skills/` 目录
- **状态**: 🔲 保留待确认
- **现状**: 含第三方技能（algorithmic-art、brand-guidelines、canvas-design 等），可能有其他工具依赖，暂不删除

### 19. 无 CI/CD
- **状态**: 🔲 保持开放（待用户决定）
- **现状**: 测试需手动运行。创建 GitHub Actions 前需确认仓库推送策略（dev 分支推送后）与 497 大经书测试时长

### 20. 数据目录膨胀
- **状态**: ✅ 已缓解
- **现状**: .gitignore 已覆盖 injected/done/backup/*.idml/*.indd；2026-08-04 根目录导出 txt 已移入 source/ 或归档（P3-7）

### findings.md 遗留 MEDIUM/LOW 项 ✅
- **状态**: ✅ 已关闭（2026-08-04）
- **MEDIUM**（_rebuild_paragraph_xml 后缀提取 find('>') 无防护）: 相关死函数 `_insert_punct_csrs` 已随 P3-3 删除，代码路径不存在
- **LOW**（_find_punct_style 静默跳过）: 函数已随 v2.0 重构移除

---

## 🟢 低优先级（7 项）

### 9. UTF-8 BOM / 编码 ✅
- **状态**: ✅ 无 BOM（utf-8-sig 读取兼容），CRLF 行尾（Windows 正常）

### 21. 无 Python 版本声明 ✅
- **状态**: ✅ 已创建 `.python-version`（3.11，2026-08-04 P3-9）

### 22. 分支 master → main ✅
- **状态**: ✅ 已处理

### 23. 无 `.editorconfig`
- **状态**: 🔲 可选（保持开放）
- **建议**: 如跨平台协作可添加（charset=utf-8, end_of_line=crlf, indent=4）

### 24. 无 `pyproject.toml`
- **状态**: 🔲 可选（保持开放）
- **建议**: 如需 ruff/pytest 配置可添加；纯标准库当前不需要

### 25. `code/__pycache__/` 已在 `.gitignore` 中 ✅
- **状态**: ✅ 已覆盖

### 26. `_count_br` 重复定义 ✅
- **状态**: ✅ 已解决（2026-08-04 P3-9）
- **修复**: 提取为模块级函数 `_count_br`，删除 _verify_structure / _verify_br_count 内局部定义

---

## 📋 汇总（2026-08-04）

- ✅ 已解决：14, 15, 10, 20, 21, 25, 26, findings 遗留项 + 会话内修复
- 🔲 保持开放：13（模块拆分）, 16, 19（CI）, 23（editorconfig）, 24（pyproject）
- 📄 已决策：7（保持 print）, 6（随 #13 处理）
