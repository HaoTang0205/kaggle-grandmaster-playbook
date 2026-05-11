# Recommended Output Schema

Use this schema when turning retrieved book hits into a useful Kaggle plan or expert-experience card.

## Agentic Research Brief

```markdown
## Competition Profile
- slug:
- metric:
- data signals:
- constraints:
- inferred domains:

## Algorithm Family Hypotheses
| Family | Why Plausible | What To Check First |
|---|---|---|

## Historical Evidence Map
| Rank | Source Case | Match Signal | Transferable Pattern | Anchor |
|---:|---|---|---|---|

## Transferable Tricks
- Trick:
  Current-condition trigger:
  Why it may work:
  Implementation sketch:
  Validation check:
  Failure mode:

## Code Evidence
```python
# Include only source-backed snippets that exist in extracted sections.
```

## Experiment Queue
1. Experiment:
   Historical evidence:
   Expected signal:
   Validation:
   Stop condition:
```

## Competition Strategy Note

```markdown
## Competition Profile
- slug:
- task type:
- metric:
- data risks:
- likely validation split:
- closest book domains:

## Retrieved Experience
| Rank | Book Case | Why It Matches | Useful Pattern |
|---:|---|---|---|

## High-ROI Experiments
1. Experiment:
   Why:
   Evidence:
   Validation:
   Risk:

## Tricks To Try
- Trick:
  When it helps:
  How to implement:
  What to monitor:

## Code Evidence
```python
# Include only code that exists in the extracted source.
```

## Validation And Submission Checklist
- Local validation:
- Leakage checks:
- Ablation:
- Submission safety:
```

## Expert-Experience Card

```markdown
### Title
- domains:
- algo_tags:
- source_case:
- competition_slug:
- index_keywords:
- problem_signals:

**Essence**

**Why It Works**

**When To Use**

**Implementation Pattern**

**Evidence**

```python
# Source-backed code snippet if available.
```

**Failure Modes**

**Practice Prompt**
```

## New Competition Collection Card

```markdown
## 1. source-name {#section-competition-source}

> 比赛：[competition-slug](competition-url) · 来源：[source-name](source-url) · 类型：collected_experience

- 算法标签:
- 核心关键词:
- tricks:
- 代码证据:
- 质量分:
- 收集日期:

### 摘要

### 题面与风险画像
- metric:
- data_signals:
- risk_signals:

### Algorithm Family Hypotheses

### 重点 Trick

### Source Inventory
| Kind | File | Size |
|---|---|---:|

### Evidence Notes
```

Rules:

- Keep code evidence short and source-backed.
- Prefer "what to try next" over generic description.
- Infer algorithm families from the competition profile before trusting the user's initial wording.
- Keep all local paths out of user-facing book or sale-ready notes.
- When multiple cases agree on a tactic, state the repeated pattern explicitly.
- New collection cards are staging artifacts; refine them with deeper code/write-up reading before treating them as final book chapters.
