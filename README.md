# JidouInject

佛经句读（标点）回注 IDML 工具——从 InDesign 导出的 IDML 文件中提取佛经文本，清除原有标点后，将 AI 句读结果（中文句号「。」）注入回 IDML，排版样式原封不动。

## 快速开始

### 环境要求

- Python 3.11+
- 无需额外依赖（仅使用标准库）

### 单文件处理

```bash
python -X utf8 code/inject.py --idml source/XXX导出.idml --result source/XXX句读结果.md
```

或直接拖拽 IDML 和句读结果文件到 `code/inject.bat`（已内置 `-X utf8`）。

> 可选参数：`--output`（指定输出路径）、`--min-clean N`（正文 Story 判定阈值，默认 50）。

### 批量处理

1. 将文件放入 `pending/` 目录（`*导出.idml` + `*句读结果.md` 成对放置，句读结果文件名必须含「句读结果」字样）
2. 双击 `一键批量处理.bat`（或运行 `python -X utf8 code/batch_inject.py`）
3. 结果输出到 `output/`，自动归档到 `done/` 和 `injected/`

> 安全说明：句读结果文件仅允许「文字 + 句号」；含非句号旧标点会被拒绝（疑似以原文导出文本冒充结果）。

## 目录结构

```
JidouInject/
├── 一键批量处理.bat     # 根目录快捷启动
├── AGENTS.md           # 项目说明 + 句读规则（35 条细则 + 8 轮流程）
├── CLAUDE.md           # 历史项目说明
├── README.md           # 本文件
├── progress.md         # 进度日志
├── findings.md         # 技术发现与决策
├── issues-checklist.md # 剩余问题清单
├── task_plan.md        # 实现计划
│
├── code/               # 脚本
│   ├── inject.py       # 单文件注入（唯一实现，2100+ 行）
│   ├── inject.bat      # 单文件拖拽包装器
│   ├── batch_inject.py # 批量处理
│   ├── batch_inject.bat
│   ├── test_verify_inject.py  # 核心回归（275+461）
│   ├── test_zip_stream.py     # ZIP 流式 14 项测试
│   ├── test_stress_idml.py    # 压力测试
│   └── bench_inject.py        # 性能基准
│
├── source/             # 原始文件（只读，不处理）
├── pending/            # 待处理（放文件到这里）
├── output/             # 本轮处理结果
├── injected/           # 所有注入结果汇总（永久保留）
├── done/               # 已完成归档（按经本分目录）
├── backup/             # 代码版本备份（v1.0 ~ v1.4）
│
└── .gitignore          # 排除: *.idml, *.indd, __pycache__, output/, pending/, injected/, done/, backup/
```

## 验证测试

```bash
python -X utf8 code/test_verify_inject.py    # 核心回归（275 + 461）
python -X utf8 code/test_zip_stream.py      # ZIP 流式 14 项
```

## 规则

详见 [AGENTS.md](AGENTS.md)——句读规则（35 条细则）及 8 轮处理流程。
