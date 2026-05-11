---
name: kaggle-grandmaster-playbook
description: "Use when an AI agent should behave like a Kaggle grandmaster research partner: autonomously infer task families, retrieve similar historical competitions from the local Kaggle Grandmaster Playbook, rank expert write-up/code evidence, extract transferable tricks, propose experiments, collect new competition experience into the same playbook format, and keep improving the local Kaggle knowledge base. Useful even when the user does not know which algorithm to use."
---

# Kaggle Grandmaster Playbook

Agentic retrieval and memory layer for a local Kaggle expert-experience book. The goal is not to answer only the user's stated algorithm preference; the goal is to help an AI agent read a competition, infer plausible directions, retrieve historical evidence, propose experiments, and save new lessons back into the playbook.

## Core Principle

Treat user intent as incomplete evidence. A Kaggle user may only know the competition URL, slug, metric, columns, or a vague goal like "improve score". First infer the competition shape, then search the playbook.

Act like a detachable Kaggle research teammate: inspect the problem, form hypotheses, retrieve analogies, propose experiments, identify validation risks, ask for missing data only when necessary, and preserve useful new findings.

## Inputs To Gather

Use whatever is available; do not block if some fields are missing.

- Competition identity: slug, title, host, year, prior related competitions.
- Problem statement: target, task wording, constraints, hidden-test clues.
- Metric: AUC, F1, RMSE, RMSPE, MAP, Dice, IoU, logloss, QWK, NDCG, custom metric.
- Data signals: file types, modalities, sample columns, IDs/groups, timestamps, images/audio/text/3D/graph.
- Runtime signals: Kaggle notebook limits, offline package needs, memory, inference server, submission format.
- Current symptoms: weak baseline, CV/LB gap, leakage suspicion, timeout, overfit, unstable ensemble.

## Default Workflow

1. Build a competition profile from the available signals.
2. Infer one or more domains: `tabular`, `feature`, `cv_vision`, `nlp_llm`, `audio`, `timeseries`, `ensemble`, `system`, `rl_game`, `advanced`.
3. Run autonomous research first:

```powershell
python scripts/research_competition.py --slug "competition-slug" --description "problem statement or README excerpt" --metric "AUC" --data "CSV columns or file modalities" --limit 12
```

4. Inspect the returned algorithm-family hypotheses and top historical evidence.
5. Extract only the strongest 1-3 anchors before giving detailed advice:

```powershell
python scripts/extract_book_section.py --anchor section-example-anchor --max-chars 25000
```

6. Produce a research brief: profile, inferred families, retrieved cases, transferable tricks, code evidence when present, and an experiment queue.

## Search Tools

Refresh the catalog after changing the book:

```powershell
python scripts/build_book_catalog.py
```

Use repo-relative book files when this skill is published. If the book lives elsewhere, set:

```powershell
$env:KAGGLE_GRANDMASTER_BOOK = "path\to\book.md"
```

Targeted catalog search is useful after the autonomous brief identifies a direction:

```powershell
python scripts/search_book_catalog.py --auto --query "tabular auc target encoding leakage grouped cv" --limit 8
python scripts/search_book_catalog.py --auto --query "birdclef audio spectrogram sed overlap inference" --limit 8 --json
python scripts/search_book_catalog.py --slug "lux-ai-season-3" --limit 5
```

Use the full archive catalog for maximum recall:

```powershell
python scripts/search_book_catalog.py --catalog assets/kaggle_book_catalog_full.json --auto --query "medical segmentation dice tta postprocess" --limit 12
```

## Collect New Competition Experience

When a new competition has write-ups, kernels, code, discussion exports, or notes, collect them into a playbook-compatible card before deeper LLM analysis:

```powershell
python scripts/collect_competition_experience.py --source-dir path\to\new_competition_sources --out collected\competition-card.md --slug "competition-slug" --metric "AUC" --data "CSV + categorical + group id"
```

Then review the card, run deeper LLM analysis if needed, append it to a book markdown file, and rebuild the catalog:

```powershell
python scripts/build_book_catalog.py --book book/book.md --out assets/kaggle_book_catalog.json
```

Use this to keep the skill learning from future contests instead of staying frozen at the original book.

## Ranking Heuristics

- Exact slug or close prior competition outranks generic technique matches.
- Same modality plus same metric outranks same model family alone.
- Validation hazards matter: grouped split, temporal split, leakage, hidden shift, noisy labels, imbalance.
- Code-heavy sections are best for implementation patterns.
- Write-up-heavy sections are best for "why it worked", ablations, and strategy.
- System sections are often relevant even when the task domain differs.
- Ensemble sections become more important after a stable single-model baseline exists.

## Output Contract

For automated research, return a concise but actionable brief:

- Competition profile and inferred domains.
- Algorithm-family hypotheses with why each family is plausible.
- Historical evidence table with anchors or source names.
- Transferable tricks, each tied to the current competition condition.
- Source-backed code snippets only when extracted source contains useful code.
- Experiment queue with validation check, expected signal, and failure mode.
- Open questions for the next data-inspection or Kaggle CLI step.
- New-experience collection plan when the current competition has useful write-ups/code not yet in the playbook.

Use `references/output-schema.md` when writing a polished strategy note or expert-experience card.

## References

- `references/chapter-map.md`: domain aliases and chapter routing.
- `references/search-rules.md`: retrieval strategy for weak/incomplete competition signals.
- `references/output-schema.md`: output shapes for research briefs and reusable cards.
- `references/grandmaster-agent-loop.md`: detachable agent operating loop for live competitions.

## Guardrails

- Do not assume the user knows the right algorithm; infer candidates from the competition profile.
- Do not invent code evidence. If no useful source code exists, write the insight without a code block.
- Do not expose private API keys, Kaggle credentials, or local absolute paths in public notes.
- Treat the playbook as historical evidence, not a guarantee of leaderboard performance.
- Prefer relative paths from the skill/repository root in commands and documentation.
- For live Kaggle operations, combine this skill with the regular `kaggle` skill for CLI downloads, notebooks, datasets, and submissions.
