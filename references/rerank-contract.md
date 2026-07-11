# Evidence Rerank Contract

Use this contract after deterministic retrieval and before detailed advice.

## Required Inputs

- Current competition profile and stage.
- Validation risks and runtime constraints.
- Top candidate metadata from `research_competition.py`.
- Full text for each `must_read_anchor` from `extract_book_section.py`.
- Current baseline/experiment state when available.

## Pairwise Evaluation

For every candidate, score the following dimensions from 0 to 3:

| Dimension | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| Prediction unit | Different | Weak analogy | Mostly aligned | Same |
| Modality/task | Different | Adjacent | Same modality | Same task shape |
| Metric behavior | Different | Unknown | Similar | Same |
| Validation risk | Conflicts | Not discussed | Partly matched | Directly matched |
| Runtime regime | Incompatible | Unknown | Adaptable | Similar |
| Evidence quality | Generic | Summary only | Write-up or code | Write-up plus code/ablation |

Do not hide mismatches behind a total score. List the strongest matching condition and the most dangerous mismatch.

## Output

```json
{
  "anchor": "section-id",
  "evidence_level": "exact|direct|near|adjacent|analogy",
  "matching_conditions": [],
  "mismatches": [],
  "transferable_mechanism": "",
  "required_adaptations": [],
  "validation_test": "",
  "code_evidence": {
    "available": true,
    "source": "",
    "relevant_symbols_or_lines": []
  },
  "confidence": "high|medium|low",
  "decision": "use|ablate|background-only|reject"
}
```

## Hard Rejections

Reject or demote evidence when:

- It relies on prohibited external data or target leakage.
- The split contradicts the current prediction unit.
- The source is only a generic tutorial while direct competition evidence exists.
- The code and write-up describe materially different pipelines.
- The trick depends on unavailable compute/runtime.
- The claimed gain has no ablation, code, or clear mechanism and conflicts with stronger evidence.

## Synthesis Rules

- Repeated independent evidence strengthens a mechanism, not a specific hyperparameter.
- A single exact-competition source can dominate directness but not automatically reliability.
- Code is strongest for implementation details; write-ups are strongest for motivation, ablation and failure context.
- Preserve negative evidence and failed approaches when they constrain the search space.
- Convert every accepted mechanism into an isolated experiment with a stop condition.
