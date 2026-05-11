# Kaggle Grandmaster Playbook 中文说明

这是一个面向 AI Agent 的 Kaggle 竞赛经验检索与研究技能。它把一批公开 Kaggle 高分方案、write-up、notebook 代码证据和可迁移 tricks 整理成书籍与索引，让 Agent 在面对新比赛时，可以先判断任务形态，再检索相似历史经验，最后给出有证据支撑的实验计划。

> 当前项目是自动化研究工作流的 demo / reference implementation，不是“自动赢比赛”的完整系统。它更像一个可拆、可改、可继续训练的 Kaggle 经验记忆层，欢迎你按自己的 Agent、LLM API、Kaggle CLI、浏览器抓取、向量库和重排序逻辑继续优化。

## 这个项目解决什么问题

- 用户不一定知道该用什么算法，但 Agent 可以根据题面、metric、数据文件和字段信号先推断任务类型。
- 面对新比赛时，Agent 可以自动召回相似历史比赛、相似验证风险、相似高分套路，而不是只做关键词搜索。
- 输出建议时尽量绑定历史证据，包括 write-up 结论、代码片段、验证风险、失败模式和下一步实验。
- 新比赛产生的 write-up、kernel、讨论和代码可以被整理成统一经验卡，后续继续加入知识库。

## 目录结构

```text
kaggle-grandmaster-playbook/
├── SKILL.md                         # Codex / Agent skill 主入口
├── README.md                        # 英文说明
├── README.zh-CN.md                  # 中文说明
├── agents/openai.yaml               # Agent UI 元信息
├── scripts/
│   ├── research_competition.py       # 根据比赛画像自动召回历史经验
│   ├── search_book_catalog.py        # 搜索经验索引
│   ├── extract_book_section.py       # 按 anchor 抽取书中原文 section
│   ├── collect_competition_experience.py
│   ├── build_book_catalog.py
│   └── sanitize_public_book.py
├── references/
│   ├── grandmaster-agent-loop.md
│   ├── chapter-map.md
│   ├── search-rules.md
│   └── output-schema.md
├── assets/
│   ├── kaggle_book_catalog.json
│   └── kaggle_book_catalog_full.json
├── book/book.md                     # 精简成书版
├── book/book.pdf                    # 阅读版 PDF
└── book_full/book.md                # 全量归档版
```

## 快速开始

如果你只是想测试检索能力，可以直接运行：

```powershell
python scripts\research_competition.py `
  --description "CSV tabular binary classification with AUC, categorical columns, possible group leakage and public/private shift" `
  --metric "AUC" `
  --data "train.csv test.csv categorical numerical id" `
  --limit 8
```

如果你已经知道方向，可以做定向搜索：

```powershell
python scripts\search_book_catalog.py --auto --query "target encoding leakage grouped cv lightgbm auc" --limit 8
```

拿到搜索结果里的 `anchor` 后，可以抽取完整章节：

```powershell
python scripts\extract_book_section.py --anchor section-example-anchor --max-chars 25000
```

如果你想把新比赛资料整理成同一格式：

```powershell
python scripts\collect_competition_experience.py `
  --source-dir data\new_competition_sources `
  --out collected\new-competition-card.md `
  --slug "competition-slug" `
  --metric "AUC" `
  --data "CSV categorical numerical group id"
```

## 作为 Codex Skill 使用

将整个仓库复制或克隆到你的 Agent skills 目录后，可以这样调用：

```text
Use $kaggle-grandmaster-playbook to infer the competition shape, retrieve historical Kaggle expert patterns, and propose evidence-backed experiments.
```

这个 skill 的默认思路是：

1. 先根据比赛 slug、题面、metric、数据文件、字段、运行限制等信息构造比赛画像。
2. 自动推断可能的大类：`tabular`、`feature`、`cv_vision`、`nlp_llm`、`audio`、`timeseries`、`ensemble`、`system`、`rl_game`、`advanced`。
3. 检索历史比赛经验，优先匹配任务类型、metric、验证风险、代码证据和 exact slug。
4. 抽取最相关的 1-3 个历史章节，再给出实验队列、验证检查和失败模式。
5. 如果当前比赛产生了新的高质量方案资料，再整理成经验卡，后续加入书和索引。

## 书和索引是怎么来的

本仓库中的书籍内容来自一个本地 Kaggle 研究流水线：它批量收集公开高分 notebook、方案 write-up、讨论资料、代码转写结果和 LLM / 人工整理的分析卡，再合并成 markdown 书籍。

- `book/book.md` 是更适合阅读和高信号检索的精简版。
- `book/book.pdf` 是导出的 PDF 阅读版。
- `book_full/book.md` 是全量归档版，适合最大召回。
- `assets/kaggle_book_catalog.json` 和 `assets/kaggle_book_catalog_full.json` 是从书中抽取出的检索索引。

你可以把它当作个人 Kaggle 学习资料，也可以把它当作 Agent 自动化研究时的“历史经验记忆库”。

## 当前限制

- 自动化研究目前只是 demo，召回、排序、质量评估和资料采集都还有很大优化空间。
- 该项目不会保证生成获胜方案，只能提供历史经验证据和实验假设。
- 原始 crawler / downloader 流水线没有完全开源泛化，当前主要开放的是整理后的书、索引、skill 和工具脚本。
- 不同系统、Python 版本、Agent runtime、Kaggle 账号配置和 LLM API 可能需要自己适配。
- 书中部分材料来自公开网页和公开 notebook 的整理与摘要，使用、二次分发或商业化前请认真检查 Kaggle 规则、notebook license、数据集 license 和引用要求。

## 适合贡献什么

欢迎 issue 或 PR，尤其是这些方向：

- 更好的任务类型推断规则。
- 更可靠的历史案例召回与重排序逻辑。
- 小型 benchmark，用于评价检索结果是否真的匹配比赛。
- Kaggle CLI、浏览器抓取、notebook 转 Python、write-up 清洗、讨论串整理等适配器。
- 更干净的公开版书籍清洗和导出流程。
- 新比赛经验卡示例，尤其是带代码证据、验证策略、失败模式的高质量案例。

提 issue 时最好包含：输入的比赛画像、期望召回的历史案例、实际召回结果、为什么你认为排序应该调整。

## 安全与许可

- 不要提交 API key、Kaggle token、cookie、本机绝对路径或账号文件。
- 代码脚本使用仓库代码 license。
- `book/` 和 `book_full/` 下的书籍内容是独立内容资产，不等同于代码 license，详见 `CONTENT_LICENSE.md`。
- 如果你计划公开传播、商业使用或再出版书籍内容，请先确认原始 Kaggle notebook、讨论、数据集和比赛规则的授权边界。

## 一句话定位

这个项目不是替你自动打赢 Kaggle，而是让 AI Agent 在打比赛前先“读过很多高手复盘”，并能把这些历史经验变成当前比赛的可验证实验计划。
