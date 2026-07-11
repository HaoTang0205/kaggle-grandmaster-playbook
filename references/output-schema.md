# Output Schemas

## Competition Decision Brief

```markdown
# Competition Decision Brief

## Competition Contract
- slug:
- prediction unit:
- metric and direction:
- modalities:
- constraints:
- unresolved facts:

## Validation Contract
| Gate | Action | Pass Condition | Status |
|---|---|---|---|

## Evidence Coverage
- confidence:
- direct/near cases:
- code/write-up coverage:
- gaps:

## Evidence Map
| Rank | Level | Historical Case | Matching Condition | Dangerous Mismatch | Anchor |
|---:|---|---|---|---|---|

## Cross-Competition Mechanism Bridges
| Source Competition | Shared Mechanism | Surface-Type Difference | Transfer Test | Anchor |
|---|---|---|---|---|

## Source Competition Deep Dives
- research id and status:
- source competition and official page:
- knowledge point:
- original prediction unit/metric/split:
- source-backed implementation, if available:
- gain attribution and counterevidence:
- transfer conditions:
- failure conditions:
- custom queries executed:
- sources checked:

## Current Research
| Source | Current Method/Constraint | Why Relevant | License/Rule Check |
|---|---|---|---|

## Experiment Portfolio
| ID | Parent | Component | Hypothesis | Isolated Change | Expected Diagnostic | Stop Condition | Cost |
|---|---|---|---|---|---|---|---|

## Next Action
- mode:
- action:
- reason:
```

## Experiment Record

```json
{
  "id": "E03",
  "parent_id": "E01",
  "component": "features",
  "hypothesis": "",
  "change": "",
  "evidence_anchors": [],
  "research_ids": [],
  "ablation_id": "A003",
  "code_version": "git-commit-or-snapshot",
  "data_version": "dataset-manifest-or-hash",
  "config_hash": "",
  "environment_hash": "",
  "fold_version": "",
  "metric_version": "",
  "seeds": [42],
  "params": {},
  "status": "success|failed|discarded",
  "cv_mean": null,
  "cv_std": null,
  "fold_scores": [],
  "slice_metrics": {},
  "lb_score": null,
  "runtime_minutes": null,
  "peak_memory": null,
  "artifact": "",
  "diagnosis": "",
  "next_decision": "promote|refine|discard|branch"
}
```

## Ablation Registration

```json
{
  "id": "A003",
  "design": "ofat|factorial|negative_control|sensitivity",
  "parent_experiment_id": "E01",
  "component": "features",
  "factor": "patient normalization",
  "control": "disabled",
  "treatment": "enabled",
  "fixed_conditions": ["folds=v2", "seed_policy=42,43,44"],
  "hypothesis": "",
  "expected_signal": "",
  "research_ids": ["R001"],
  "status": "planned|running|completed|failed|discarded",
  "decision": "pending|supported|partially_supported|not_supported|inconclusive"
}
```

## Result Analysis Log

```json
{
  "experiment_id": "E03",
  "version": 1,
  "verdict": "supported|partially_supported|not_supported|inconclusive",
  "snapshot": {
    "cv_delta": null,
    "cv_std_delta": null,
    "fold_deltas": [],
    "fold_wins": 0,
    "slice_deltas": {},
    "runtime_minutes_delta": null,
    "peak_memory_mb_delta": null
  },
  "mechanism": "",
  "confounders": [],
  "slice_findings": [],
  "resource_tradeoff": "",
  "next_action": ""
}
```

## Comparative Reflection

```markdown
### Parent -> Child
- Exact code/config difference:
- Predicted diagnostic movement:
- Observed mean/fold/slice movement:
- Runtime/memory movement:
- Supported mechanism:
- Falsified hypothesis:
- Remaining confounders:
- Transfer conditions:
- Next action:
```

## Long-Term Experience Card

```markdown
### Title
- domains:
- source or experiment provenance:
- competition slug:
- prediction unit:
- metric family:
- validation risks:
- index keywords:

**Conditional lesson**

**Why it works**

**When to use**

**Implementation pattern**

**Source-backed code**

**Evidence and counterevidence**

**Failure modes**

**Minimal validation test**
```

Rules:

- Never invent code evidence.
- Do not promote a retrieved claim while its source research task is pending.
- Keep public notes free of credentials and absolute local paths.
- Preserve uncertainty and mismatches.
- Prefer conditional mechanisms over generic tricks.
- Keep staging cards separate from reviewed long-term memory.
- Use `draft -> reviewed -> promoted/rejected` lifecycle states and invalidate review when card content changes.
- Index promoted cards in the learned-experience catalog; keep raw experiment state as provenance rather than copying it wholesale.
