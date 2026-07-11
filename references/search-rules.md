# Search Rules

## Retrieval Stack

The deterministic engine uses:

1. Competition profile inference with boundary-safe domain matching.
2. Curated, full-archive and reviewed learned-experience catalog deduplication.
3. Field-weighted BM25 over slug, title, tags, keywords, problem signals, tricks and summary.
4. Multiple lenses: user-defined questions, exact competition, task shape, modality, metric, validation risk, mechanism transfer, implementation and late-game ensemble.
5. Reciprocal-rank fusion across lenses.
6. Modality/risk/mechanism/metric/source-quality reranking.
7. Diversity selection across competitions and evidence.

The local cache is fingerprinted against both catalogs and the active policy. Catalog or policy changes invalidate it automatically.

## Profile Construction

Use these signal groups:

- Identity: slug, title, host, year and related competition series.
- Prediction unit: row, entity, timestamp, image, patient, recording, query, edge or episode.
- Modality: tabular, vision, NLP, audio, time series, graph/recommendation or simulation/game.
- Metric behavior: probability/ranking, thresholded classification, regression, overlap, detection, ordinal or custom.
- Validation risk: groups, time, duplicates, spatial parents, label noise, imbalance, shift or public-LB overfit.
- Constraints: runtime, memory, offline packages, accelerator, submission quota and inference format.

If no primary modality is inferred, inspect data before choosing models.

## Evidence Priority

1. Same competition with trustworthy source detail.
2. Same prediction unit/modality plus metric or validation risk.
3. Same modality with a plausible transfer mechanism.
4. Same causal, validation or engineering mechanism in an adjacent domain.
5. Cross-domain analogy with explicit caveats.

Exact slug is not an automatic endorsement. A weak tutorial from the same competition may rank below a strong direct case after LLM reranking.

Competition type is a soft prior, never a hard filter. Preserve high-signal cross-domain hits as `mechanism_bridges` when they share a validation risk or mechanism. Require an explicit dangerous-mismatch analysis before transfer.

## Custom Query Rules

- Accept repeated free-form `--query` values and TXT/Markdown/JSON `--query-file` inputs.
- Give each custom question an independent retrieval lens; do not collapse all questions into one taxonomy label.
- Preserve the original wording in the decision brief and scope it to each source competition during deep-dive research.
- Keep automatic profile and mechanism queries enabled as complementary recall unless the policy explicitly changes their weights.
- Override weights, query templates and vocabulary through `config/retrieval_policy.json`, `--policy` or `KAGGLE_GM_POLICY`; do not patch source code for normal tuning.

## Coverage Rules

High confidence normally requires:

- At least four direct/near hits.
- Multiple competitions.
- Source-backed code where implementation is requested.
- Validation-risk coverage when risks are known.

Low coverage requires more inspection or live research. Do not compensate by writing more confidently.

## Stage Rules

- Intake: boost validation, leakage, data usage and baseline evidence.
- Improve: boost the active component and current failure symptoms.
- Ensemble: boost OOF diversity, calibration and robust blending.
- Finalize: boost inference, packaging and submission safety.

## Reading Rules

- Read metadata first, then extract full sections for `must_read_anchors`.
- Use `book/book.md` for curated high-signal evidence.
- Use `book_full/book.md` for recall and niche cases.
- `auto-section-*` anchors are resolved against the full book automatically.
- `experience-*` anchors resolve to reviewed post-competition cards in `knowledge_base/experience_cards/`.
- Use `references/rerank-contract.md` before transferring a trick.
- Use `references/competition-deep-dive.md` and resolve the source research task before promoting a knowledge point to implementation advice.

## Failure Tests

Run `python scripts/evaluate_retrieval.py` after modifying inference, ranking, parsing or catalogs. Add a benchmark case whenever a real competition produces a surprising wrong-domain or wrong-risk result.
