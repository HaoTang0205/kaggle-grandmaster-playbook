# Kaggle Grandmaster Playbook

[中文说明](README.zh-CN.md)

An evidence-driven Kaggle research and experiment-decision skill for AI agents. It turns historical high-score notebooks, write-ups and code evidence into a disciplined workflow: competition profiling, validation design, hybrid retrieval, source reranking, budget-aware experiments, comparative reflection and isolated memory.

It does not guarantee medals or claim that installing a prompt makes an agent a Kaggle Grandmaster. Its purpose is to reduce avoidable mistakes, improve research quality and make experimentation reproducible.

## What Changed

- Infer task shape from competition facts and data rather than trusting the user's initial algorithm guess.
- Profile real files, CSV/TSV/Parquet/Feather schemas, images, audio, text/replays, archives, target candidates, IDs, groups, timestamps and unused data sources.
- Fuse a curated 173-entry catalog with a 2,708-entry full catalog covering roughly 613 competitions.
- Repair full-catalog metadata that previously lost competition slugs, sources, quality and code evidence.
- Use a low-memory fingerprinted SQLite FTS5 index, independent free-form query lenses, reciprocal-rank fusion, risk/mechanism/metric/source reranking and diversity selection.
- Treat competition type as a soft prior and preserve cross-domain evidence through shared mechanisms and validation risks.
- Accept repeated `--query` inputs and TXT/Markdown/JSON `--query-file` inputs without replacing them with a fixed taxonomy.
- Turn retrieved knowledge points into source-competition deep dives covering official facts, original solutions, failures and transfer conditions.
- Classify evidence as exact, direct, near, adjacent or analogy.
- Require full-section reading before converting a hit into implementation advice.
- Maintain parent/child experiments with hypotheses, isolated changes, diagnostics, costs and stop conditions.
- Pre-register ablations and automatically project synchronized ablation, result and analysis reports per workspace.
- Distill every finished competition through a draft/review/promotion gate into a third learned-experience index, including negative evidence.
- Attach bounded code excerpts with relative paths, symbols, line ranges and source/excerpt hashes; external code promotion also requires repository, immutable commit and license.
- Wrap every external section as untrusted evidence so write-ups, discussions and repositories cannot inject agent instructions.
- Isolate each workspace with a `run_id`; mismatched agent windows cannot mutate the same ledger.
- Ship ten ranked retrieval cases plus a no-Harness end-to-end skill evaluation and a relocation doctor.

The current repository benchmark passes 10/10 cases with MRR 1.0 and Recall@5 1.0. This measures repository behavior, not Kaggle medal performance.

## Architecture

```text
competition page/data
        |
        v
profile_competition.py  -> profile, target/ID/group/time candidates, data-usage gate
        |
        v
research_competition.py -> validation contract, custom/automatic evidence, source deep dives, experiments
        |
        +--> extract_book_section.py -> full source/code evidence
        +--> live primary-source research
        |
        v
competition_memory.py   -> isolated research tasks, ablations, analysis log, experiment tree
        |
        v
Kaggle CLI / notebook / chosen runtime -> optional execution and submissions
        |
        v
collect_competition_experience.py -> reviewed new memory -> rebuilt catalogs
distill_competition_experience.py -> postmortem -> review gate -> learned catalog
```

## Quick Start

Profile local competition data:

```powershell
python scripts\profile_competition.py `
  --data-dir "path\to\competition\data" `
  --slug "competition-slug" `
  --metric "AUC" `
  --out "path\to\workspace\competition-profile.json"
```

Initialize isolated memory:

```powershell
python scripts\competition_memory.py init `
  --workspace "path\to\workspace" `
  --slug "competition-slug" `
  --metric "AUC" `
  --metric-direction higher
```

Set the returned `KAGGLE_GM_RUN_ID` command in the current agent window. In stateless agent calls, pass the returned value with `--run-id` on every mutating command.

Build a decision brief:

```powershell
python scripts\research_competition.py `
  --profile "path\to\workspace\competition-profile.json" `
  --query "Why did this help private LB but not grouped CV?" `
  --query-file "path\to\workspace\questions.json" `
  --stage intake `
  --budget standard `
  --limit 12 `
  --json-out "path\to\workspace\decision-brief.json" `
  --out "path\to\workspace\decision-brief.md"
```

Extract must-read evidence:

```powershell
python scripts\extract_book_section.py --anchor "section-or-auto-section-anchor" --max-chars 30000
```

Pre-register an ablation, then bind the treatment experiment to it:

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

## Agent Invocation

```text
Use $kaggle-grandmaster-playbook to inspect this competition, lock validation, retrieve and rerank expert evidence, research current methods, and build a budget-aware experiment loop.
```

Use Kaggle CLI, the regular Kaggle skill, notebooks or another runtime for downloads, execution and submissions. This repository intentionally has no Harness adapter and needs no LLM API.

## Main Components

| Path | Purpose |
|---|---|
| `scripts/grandmaster_core.py` | Profile inference, SQLite FTS5/RRF retrieval, risk reranking and experiment candidates |
| `scripts/profile_competition.py` | Deterministic data-directory profiling and data-usage gate |
| `scripts/research_competition.py` | Evidence-backed competition decision brief |
| `scripts/search_book_catalog.py` | Targeted hybrid retrieval |
| `scripts/extract_book_section.py` | Full evidence extraction by curated/full anchor |
| `scripts/competition_memory.py` | Run isolation, source-research tasks, ablation matrix, result analysis and next-action policy |
| `scripts/audit_pipeline.py` | Static leakage, split, data-usage, metric and reproducibility audit |
| `scripts/evaluate_retrieval.py` | Ranked retrieval, provenance and latency benchmark |
| `scripts/evaluate_skill.py` | Portable no-Harness end-to-end workflow evaluation |
| `scripts/skill_doctor.py` | Python/FTS5/catalog/card/privacy/manifest portability checks |
| `scripts/collect_competition_experience.py` | Staging cards for new competition knowledge |
| `scripts/distill_competition_experience.py` | Post-competition distillation, quality review and learned-index promotion |
| `scripts/build_book_catalog.py` | Catalog generation from Markdown books |

The first full search builds a fingerprinted local cache. Catalog or indexed domain-vocabulary changes invalidate it automatically; ranking-only changes do not trigger needless rebuilds. `.cache/` is not committed. Retrieval weights, vocabulary extensions and deep-dive query templates can be overridden with `--policy` or `KAGGLE_GM_POLICY` instead of editing Python.

Each workspace automatically contains `experiment_reports/ablation_matrix.csv`, `experiment_results.csv` and `experiment_analysis_log.md`. The JSON state remains the source of truth; these are synchronized views.

After a competition, run `distill_competition_experience.py draft`, then `review`, then `promote`. Only hash-verified cards with mechanisms, provenance, transfer/failure conditions and analyzed experiments enter `knowledge_base/experience_cards/` and the default learned catalog. Failed and inconclusive experiments are preserved as negative lessons.

## Portability

Core scripts use Python 3.10+ and the standard library. Paths are resolved relative to the skill root. `KAGGLE_GM_CATALOGS`, `KAGGLE_GRANDMASTER_BOOK`, `KAGGLE_GM_KNOWLEDGE_BASE`, `KAGGLE_GM_CACHE_DIR` and `KAGGLE_GM_POLICY` can relocate the knowledge pack and writable cache. Use one workspace/run ID per competition. See `references/portability.md` for Windows, Linux/macOS and concurrent-agent guidance.

## Test

```text
python -m unittest discover -s tests -v
python scripts/evaluate_retrieval.py --strict
python scripts/evaluate_skill.py --strict
python scripts/skill_doctor.py --strict
```

Before executing generated code:

```powershell
python scripts\audit_pipeline.py --script path\to\train.py --profile path\to\competition-profile.json --strict
```

Add a benchmark case whenever a real competition reveals wrong-domain, wrong-risk or poor evidence ranking. Prefer measurable regression cases over one-off ranking patches.

## Book And Catalogs

- `book/book.md`: curated high-signal edition.
- `book/book.pdf`: reading edition.
- `book_full/book.md`: full archive.
- `assets/kaggle_book_catalog.json`: curated catalog.
- `assets/kaggle_book_catalog_full.json`: full catalog.
- `assets/learned_experience_catalog.json`: reviewed local post-competition experience catalog.
- `assets/knowledge-pack-manifest.json`: relative paths, roles, sizes and SHA-256 hashes for portable distribution.

The catalogs index method keywords, problem signals, transfer scenarios and pattern families in addition to titles, tags, tricks and summaries.

## Research Basis

See `references/research-foundations.md` for primary sources and design consequences. The workflow incorporates ideas from MLE-Bench, MLE-STAR, AIDE, MARS, Gome, AutoKaggle, MLAgentBench and Agent K: task-specific retrieval, component ablation, branch search, structured diagnostic feedback, budget planning, leakage/data-usage checks, unit tests and comparative memory.

## Boundaries

- The 10/10 benchmark and end-to-end fixture validate repository behavior, not medal rate.
- Deterministic profiling covers common tabular and multimodal assets; specialized medical, graph, database and simulator semantics still require inspection.
- Final evidence reranking depends on the calling model, but now follows an explicit comparison/rejection contract.
- This repository does not bundle a universal LLM API runner.
- External data, pretrained weights and code must comply with competition rules and licenses.

## Contributing

High-value contributions include:

- Retrieval failures with expected results.
- Better metric and validation-risk inference.
- New modality/data profilers.
- Source-backed winning-solution cards.
- Experiment scheduling and comparative-memory improvements.
- Reproducible evaluations on MLE-Bench or real Kaggle tasks.

An issue should ideally include the input profile, expected evidence, actual evidence, failure analysis and a testable acceptance criterion.

## Safety And Licensing

- Never commit API keys, Kaggle credentials, cookies or absolute private paths.
- Respect Kaggle rules, dataset licenses, notebook licenses and external-data restrictions.
- Code and book content have separate licensing boundaries; see `CONTENT_LICENSE.md`.
