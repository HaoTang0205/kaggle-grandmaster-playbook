# Kaggle Grandmaster Playbook 中文说明

这是一个面向 AI Agent 的 Kaggle 研究、证据检索与实验决策 skill。它不会靠一句“像 Grandmaster 一样思考”的提示词假装变强，而是把高手工作方式拆成可检查的系统：数据画像、验证契约、历史案例与赛后经验三库召回、证据精排、预算感知实验、比较式反思、任务隔离和长期经验写回。

它不保证奖牌，也不声称安装后就能替代 Kaggle Grandmaster。它的目标是让 Agent 少犯低级错误、少做无记录的随机实验，并能利用本仓库整理的大量公开高分方案经验。

## 这一版解决了什么

- 不要求用户先知道算法。Agent 先从题面、metric、文件、字段和约束推断任务形态。
- 验证优先。检测 group、时间、重复、患者/场景、分布漂移、标签噪声等风险。
- 精简库、全量库与赛后学习库三路检索。精简索引 173 条高信号章节，全量索引 2708 条、覆盖约 613 场比赛。
- 修复了旧全量索引丢失 slug、来源、质量分和代码证据的问题。
- 采用低内存 SQLite FTS5、一次联合召回、多查询视角 RRF、风险/机制/metric/来源质量精排和多样性选择。
- 比赛类型只是弱先验；患者、说话人、用户、场景等不同赛题可通过共享泄漏边界、因果约束、校准、弱监督或系统瓶颈互相召回。
- 支持任意自然语言自定义查询，可重复传入 `--query`，也可用 TXT/Markdown/JSON `--query-file` 批量输入，不会被固定分类词覆盖。
- 命中知识点后自动建立“来源比赛深挖”队列，要求核对官方规则、原 write-up、代码/讨论、消融、失败条件和迁移边界。
- 将证据分成 exact、direct、near、adjacent、analogy，禁止把类比包装成直接结论。
- 先抽取全文再建议，避免只看摘要产生幻觉。
- 实验按 parent/child 记录，强调单变量消融、诊断信号、停止条件和预算。
- 每个消融先登记 control、treatment、固定条件和预期信号；结果自动生成逐折、slice、方差与资源代价分析日志。
- 每场比赛结束后执行 `draft -> review -> promote` 赛后蒸馏；有效经验与失败反例通过门禁后进入第三个个人实战索引，供未来比赛自动召回。
- 代码佐证采用相对路径、符号、行号、片段哈希和源文件哈希；外部代码入库还必须记录仓库、不可变 commit 与许可证。
- 所有 write-up、讨论、书稿和第三方代码都被包在不可信证据边界内，不能向 Agent 注入指令。
- 每个 workspace 有独立 `run_id`，两个 Codex 窗口误指向同一目录时会拒绝跨窗口写入。
- 提供 10 项排名/负向/中文自定义检索基准、无 Harness 端到端测试和可迁移 doctor。目前为 10/10、MRR 1.0、Recall@5 1.0；这不是比赛胜率。

## 架构

```text
比赛题面/数据目录
       |
       v
profile_competition.py  -> 任务、metric、target、ID、group/time、数据源清单
       |
       v
research_competition.py -> 验证契约 + 自定义/自动召回 + 来源比赛深挖 + 实验组合
       |
       +--> extract_book_section.py -> 精读原始章节和代码证据
       |
       +--> 当前网络研究 -> 官方页面、原论文、官方仓库、作者 write-up
       |
       v
competition_memory.py   -> 隔离状态、研究任务标记、实验树、最佳分支和下一动作
       |
       v
Kaggle CLI / Notebook / 自选运行时 -> 可选训练与提交
       |
       v
collect_competition_experience.py -> 新经验卡 -> 审核 -> 重建索引
distill_competition_experience.py -> 赛后实验蒸馏 -> 审核门禁 -> learned catalog
```

## 快速开始

### 1. 数据画像

```powershell
python scripts\profile_competition.py `
  --data-dir "path\to\competition\data" `
  --slug "competition-slug" `
  --metric "AUC" `
  --out "path\to\workspace\competition-profile.json"
```

它会检查文件类型、train/test/sample submission、CSV 字段、target 候选、ID、group 和时间字段，并生成 data-usage gate。

### 2. 初始化独立比赛记忆

```powershell
python scripts\competition_memory.py init `
  --workspace "path\to\workspace" `
  --slug "competition-slug" `
  --metric "AUC" `
  --metric-direction higher
```

把输出中的 shell 命令放进当前窗口。Codex 等无状态调用最好在每条写命令中显式传入 `--run-id 返回值`。每场比赛、每个 Agent 窗口必须使用不同 workspace。

### 3. 生成比赛决策书

```powershell
python scripts\research_competition.py `
  --profile "path\to\workspace\competition-profile.json" `
  --query "这个技巧为什么只提升 private LB？" `
  --query "寻找跨模态的 group leakage 反例" `
  --query-file "path\to\workspace\questions.json" `
  --stage intake `
  --budget standard `
  --limit 12 `
  --json-out "path\to\workspace\decision-brief.json" `
  --out "path\to\workspace\decision-brief.md"
```

输出不只是 tricks，而是：比赛契约、验证 gate、证据覆盖率、历史案例、跨赛题机制桥梁、来源比赛深挖、自定义问题、必读 anchors、实验组合、停止条件和下一动作。

### 4. 精读证据

```powershell
python scripts\extract_book_section.py `
  --anchor "section-or-auto-section-anchor" `
  --max-chars 30000
```

`section-*` 通常来自精简书，`auto-section-*` 自动路由到全量书。

将深挖任务导入当前比赛的隔离状态，完成官方页、原方案与讨论核验后再标记：

```powershell
python scripts\competition_memory.py import-research `
  --workspace "path\to\workspace" `
  --brief "path\to\workspace\decision-brief.json"

python scripts\competition_memory.py research-status --workspace "path\to\workspace"
```

未核验的 `research_id` 不能绑定到经验驱动实验。没有开源代码不会被自动判无效，代码证据字段可以留空。

### 5. 记录实验

先注册消融计划：

```powershell
python scripts\competition_memory.py plan-ablation `
  --workspace "path\to\workspace" `
  --id "A003" `
  --parent-experiment "E01" `
  --component features `
  --factor "patient normalization" `
  --control disabled `
  --treatment enabled `
  --fixed-condition "folds=v2" `
  --hypothesis "Fold-safe normalization reduces site shift" `
  --expected-signal "Unseen-site OOF improves without higher variance"
```

```powershell
python scripts\competition_memory.py record `
  --workspace "path\to\workspace" `
  --id "E03" `
  --parent-id "E01" `
  --component features `
  --hypothesis "Patient-normalized features reduce site shift" `
  --change "Add fold-safe patient-wise z-score features" `
  --ablation-id "A003" `
  --status success `
  --cv-mean 0.9132 `
  --cv-std 0.0041 `
  --runtime-minutes 18
```

```powershell
python scripts\competition_memory.py status --workspace "path\to\workspace"
python scripts\competition_memory.py next --workspace "path\to\workspace"
python scripts\competition_memory.py compare --workspace "path\to\workspace" --parent E01 --child E03
```

随后运行 `analyze` 写入标准化结论。系统会在该比赛 workspace 下自动维护：

- `experiment_reports/ablation_matrix.csv`
- `experiment_reports/experiment_results.csv`
- `experiment_reports/experiment_analysis_log.md`

JSON 状态是唯一事实源，这三份文件是自动同步的可读投影，不应分别手工维护。

### 6. 赛后经验蒸馏与入库

```powershell
python scripts\distill_competition_experience.py draft `
  --workspace "path\to\workspace" `
  --profile "path\to\workspace\competition-profile.json"

python scripts\distill_competition_experience.py review --workspace "path\to\workspace"
python scripts\distill_competition_experience.py promote --workspace "path\to\workspace"
```

原始聊天总结不会直接进入长期库。只有包含机制、实现改动、实验/消融证据、迁移条件、失败边界和复现信息且通过审核的卡片，才会写入 `knowledge_base/experience_cards/` 与 `assets/learned_experience_catalog.json`。失败和未支持的假设同样会被保留。

## 在 Codex 中调用

```text
使用 $kaggle-grandmaster-playbook 检查这场比赛的数据与 metric，先确定验证方案，再检索历史高分方案和当前方法，生成有证据、有预算、有停止条件的实验队列。
```

如果要实际下载数据、运行 Kernel 或提交，可搭配 Kaggle CLI、普通 `kaggle` skill、Notebook 或任意自选运行时。本 skill 不接 Harness 执行适配器，也不需要大模型 API。

## 主要脚本

| 文件 | 作用 |
|---|---|
| `scripts/grandmaster_core.py` | 画像、SQLite FTS5、RRF、风险精排、多样性和实验候选核心 |
| `scripts/profile_competition.py` | 从真实数据目录生成比赛画像和 data-usage gate |
| `scripts/research_competition.py` | 生成完整决策书 |
| `scripts/search_book_catalog.py` | 定向混合检索 |
| `scripts/extract_book_section.py` | 按 anchor 抽取完整证据章节 |
| `scripts/competition_memory.py` | 隔离状态、研究任务、消融矩阵、结果分析日志和下一动作 |
| `scripts/audit_pipeline.py` | 训练脚本泄漏、切分、数据使用、metric 与复现静态审计 |
| `scripts/evaluate_retrieval.py` | 排名、来源覆盖、负向控制与延迟基准 |
| `scripts/evaluate_skill.py` | 无 Harness 端到端工作流验收 |
| `scripts/skill_doctor.py` | Python、FTS5、索引、经验卡、隐私、知识包可迁移检查 |
| `scripts/collect_competition_experience.py` | 收集新比赛资料并生成暂存经验卡 |
| `scripts/distill_competition_experience.py` | 将赛后实验、消融和失败反例蒸馏为经审核的可检索经验卡 |
| `scripts/build_book_catalog.py` | 从书稿重建索引 |

首次全量检索会构建本地缓存；书或 catalog 变化时会通过指纹自动失效。缓存位于 `.cache/`，不会提交到 Git。

正常调参无需修改 Python。复制并覆盖 `config/retrieval_policy.json` 中需要的字段，然后用 `--policy path\to\override.json` 或环境变量 `KAGGLE_GM_POLICY` 加载；权重、机制词表、领域/风险扩展、深挖数量和查询模板都可配置。

## 可迁移与并发隔离

核心脚本只要求 Python 3.10+ 与标准库，所有资源都相对 skill 根目录定位，不绑定原作者电脑路径。通过 `KAGGLE_GM_CATALOGS`、`KAGGLE_GRANDMASTER_BOOK`、`KAGGLE_GM_KNOWLEDGE_BASE`、`KAGGLE_GM_CACHE_DIR` 和 `KAGGLE_GM_POLICY` 可以把知识包、经验卡和可写缓存放到任意位置。

同时打多场比赛时，每场比赛、每个 Agent 窗口使用独立 workspace 和 `run_id`；检索索引可以并发只读共享。移动或安装后运行 `python scripts/skill_doctor.py --strict`，再运行 `python scripts/evaluate_skill.py --strict`。Windows、Linux/macOS、只读安装和大文件知识包说明见 `references/portability.md`。

## 验证与测试

```text
python -m unittest discover -s tests -v
python scripts/evaluate_retrieval.py --strict
python scripts/evaluate_skill.py --strict
python scripts/skill_doctor.py --strict
```

执行生成代码前先跑：

```powershell
python scripts\audit_pipeline.py --script path\to\train.py --profile path\to\competition-profile.json --strict
```

当真实比赛出现错误召回时，应新增 benchmark case，而不是只为这一条输入硬编码规则。

## 书和索引

- `book/book.md`：精简高信号版。
- `book/book.pdf`：阅读版。
- `book_full/book.md`：全量归档版。
- `assets/kaggle_book_catalog.json`：精简索引。
- `assets/kaggle_book_catalog_full.json`：全量索引。
- `assets/learned_experience_catalog.json`：本地赛后审核通过的个人实战索引。
- `assets/knowledge-pack-manifest.json`：知识包相对路径、用途、大小和 SHA-256 清单。

索引除了标题和关键词，现在还纳入 `Method Keywords`、`Problem Signals`、`Transfer Scenarios` 和 `pattern_family`，因此可以从“数据症状”检索，而不只是搜模型名。

## 设计依据

`references/research-foundations.md` 整理了这版设计使用的一手资料，包括 MLE-Bench、MLE-STAR、AIDE、MARS、Gome、AutoKaggle、MLAgentBench 和 Agent K。主要吸收的是：任务特定检索、组件级消融、树/分支搜索、结构化诊断反馈、预算规划、泄漏检查、数据使用检查、单元测试和比较式记忆。

## 当前边界

- 10 项 benchmark 与端到端 fixture 只验证本仓库行为，不代表 Kaggle 奖牌率。
- 自动画像已覆盖常见表格、Parquet/Feather 元数据、图片、音频、文本/回放与压缩包；复杂医学、图、数据库和仿真语义仍需 Agent 深入检查。
- 最终 LLM 精排仍依赖所用模型的推理能力，但现在有显式证据契约和拒绝规则。
- 仓库不包含通用 LLM API 自动执行器或 Harness 适配器；它就是一个可由 Codex 或其他 Agent 直接调用的普通 skill。
- 任何外部数据、预训练权重和代码都必须检查比赛规则与许可。

## 欢迎贡献

特别欢迎：

- 带期望结果的检索失败案例。
- 更好的 metric/validation 风险检测。
- 新模态的数据画像适配器。
- 高质量冠军 write-up 与代码证据卡。
- 实验调度、诊断反馈和跨分支记忆改进。
- MLE-Bench 或真实 Kaggle 任务上的可复现实验。

Issue 最好包含：输入画像、期望召回、实际召回、错误原因和可验证的改进标准。

## 安全与许可

- 禁止提交 API key、Kaggle token、cookie 和本机绝对路径。
- 尊重 Kaggle 规则、数据许可、Notebook 许可和外部数据限制。
- 代码许可与书籍内容许可分开，书籍资产见 `CONTENT_LICENSE.md`。
- 公开或商业使用书籍内容前，请检查原始来源授权和引用要求。
