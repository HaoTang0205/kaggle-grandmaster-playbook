# Kaggle Grandmaster Playbook

An agentic Kaggle research skill built from a local book of competition write-ups, high-score notebooks, code evidence, and transferable tricks.

The goal is simple: when an AI agent sees a new Kaggle competition, it should not wait for the user to know the right algorithm. It should infer the competition shape, retrieve similar historical cases, rank the most useful evidence, turn that into experiment hypotheses, and collect new lessons back into the playbook.

## What This Is For

- Autonomous Kaggle competition research.
- Retrieving similar historical competitions from a book-derived catalog.
- Inferring likely algorithm families from slug, metric, data schema, README, sample columns, or failure symptoms.
- Extracting transferable tricks with source-backed code snippets when available.
- Helping an AI agent produce a first experiment queue, validation plan, and risk checklist.
- Collecting new competition write-ups/code/discussion notes into the same experience-card format.

This project does not claim to produce winning solutions automatically. It is a memory and retrieval layer for agentic research.

## Repository Layout

```text
kaggle-grandmaster-playbook/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── research_competition.py
│   ├── collect_competition_experience.py
│   ├── search_book_catalog.py
│   ├── extract_book_section.py
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
├── book/book.md
├── book/book.pdf
└── book_full/book.md
```

## Quick Start

Run an autonomous research brief from an incomplete competition profile:

```powershell
python scripts\research_competition.py `
  --description "CSV tabular binary classification with AUC, categorical columns, possible group leakage and public/private shift" `
  --metric "AUC" `
  --data "train.csv test.csv categorical numerical id" `
  --limit 8
```

Run targeted retrieval after the first brief identifies a direction:

```powershell
python scripts\search_book_catalog.py --auto --query "target encoding leakage grouped cv lightgbm auc" --limit 8
```

Extract a source section for deeper reading:

```powershell
python scripts\extract_book_section.py --anchor section-example-anchor --max-chars 25000
```

Collect a new competition source folder into a playbook-compatible card:

```powershell
python scripts\collect_competition_experience.py `
  --source-dir data\new_competition_sources `
  --out collected\new-competition-card.md `
  --slug "competition-slug" `
  --metric "AUC" `
  --data "CSV categorical numerical group id"
```

If your book file lives outside this repository:

```powershell
$env:KAGGLE_GRANDMASTER_BOOK = "path\to\book.md"
python scripts\build_book_catalog.py
```

## How The Agent Workflow Works

1. Build a profile from whatever is available: slug, title, metric, data files, columns, target, constraints, or symptoms.
2. Infer candidate domains: tabular, feature engineering, CV, NLP/LLM, audio, time series, ensemble, system, RL/game, or advanced topics.
3. Generate multiple recall queries automatically instead of trusting one user keyword.
4. Rank historical cases by modality fit, metric, validation hazards, source quality, code evidence, and exact competition matches.
5. Extract only the best source sections before writing detailed advice.
6. Produce an experiment queue with validation checks and failure modes.
7. If the competition produces useful new write-ups/code, collect them into a reusable experience card and rebuild the catalog.

For a more autonomous workflow, see `references/grandmaster-agent-loop.md`.

## Book Artifacts

- `book/book.md` is the compact polished book used for high-signal reading.
- `book/book.pdf` is an exported reading copy.
- `book_full/book.md` is the larger full archive for maximum recall.
- `assets/kaggle_book_catalog.json` indexes the compact book.
- `assets/kaggle_book_catalog_full.json` indexes the full archive.

## Where The Book Came From

The included book artifacts were generated from a local Kaggle research pipeline that collected public high-score notebooks, solution write-ups, discussion notes, code-derived analysis, and manual/LLM summaries into a structured markdown book. The catalog files are compact indexes extracted from those markdown books so an agent can search first and only open the most relevant sections.

The book is also useful for personal study. You can read `book/book.md` or `book/book.pdf` directly as a Kaggle experience notebook, then use this skill to retrieve related cases while working on a new competition.

Large files are intentional. If GitHub rejects future larger artifacts, use Git LFS for `*.pdf`, `*.docx`, and very large Markdown exports.

## Current Limitations

- This project is still an early research skill, not a guaranteed autonomous Kaggle winner.
- The crawler/downloader pipeline that produced the original book is not fully generalized here.
- Some environments may need path, Python, encoding, or shell adjustments.
- Ranking is heuristic and may miss good analogies or over-rank familiar patterns.
- The new-competition collection script creates a first-pass card; deeper LLM analysis is still recommended before adding it to the final book.
- Bugs are expected. Issues and ranking-failure examples are especially welcome.

## Skill Usage

Install or copy this folder into an agent skills directory, then invoke:

```text
Use $kaggle-grandmaster-playbook to infer the competition shape, retrieve historical Kaggle expert patterns, and propose evidence-backed experiments.
```

The skill is designed for automated research. A user can provide a vague competition description, and the agent should still infer possible algorithm families before searching.

## Contributing

Feedback is very welcome. Useful contributions include:

- Better domain inference rules.
- Improved ranking features for modality fit, validation hazards, or code evidence.
- New Kaggle cases with clean metadata.
- Corrections to extracted tricks or source attribution.
- Scripts for converting more notebook/code artifacts into analyzable Python.
- Better public-safe book sanitization and export workflows.
- Examples of new competition collection cards and ranking-failure cases.

Please open an issue with examples: input competition profile, expected retrieved cases, actual retrieved cases, and why the ranking should change.

## Safety Notes

- Do not commit API keys, Kaggle credentials, cookies, or local account files.
- Public book exports should be sanitized before publishing.
- Treat retrieved tricks as historical evidence, not leaderboard guarantees.
- Respect Kaggle competition rules and dataset licenses.

## License

Code and scripts are released under the repository code license. Book artifacts are separate content assets; see `CONTENT_LICENSE.md` before copying, redistributing, or using them commercially.
