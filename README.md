# JidouInject

佛经句读（标点）回注 IDML 工具——从 InDesign 导出的 IDML 文件中提取佛经文本，清除原有标点后，将 AI 句读结果（中文句号「。」）注入回 IDML，排版样式原封不动。

## 快速开始

### 环境要求

- Python 3.11+
- 无需额外依赖（仅使用标准库）

### 单文件处理

```bash
python code/inject.py --idml source/XXX导出.idml --result source/XXX句读结果.md
```

或直接拖拽 IDML 和句读结果文件到 `code/inject.bat`。

### 批量处理

1. 将文件放入 `pending/` 目录（`*导出.idml` + `*句读结果.md` 成对放置）
2. 双击 `一键批量处理.bat`（或运行 `python code/batch_inject.py`）
3. 结果输出到 `output/`，自动归档到 `done/` 和 `injected/`

## 目录结构

```
JidouInject/
├── code/              # 脚本
├── source/            # 原始文件（只读）
├── pending/           # 待处理（放文件到这里）
├── output/            # 本轮输出
├── injected/          # 所有输出汇总
├── done/              # 已完成归档
├── backup/            # 版本备份
├── README.md
└── CLAUDE.md          # 项目说明 + 句读规则
```

## 验证测试

```bash
python code/test_verify_inject.py
```

## 规则

详见 [CLAUDE.md](CLAUDE.md)——句读规则（35 条细则）及 8 轮处理流程。
