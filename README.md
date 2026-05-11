# Kaggle Grandmaster Playbook

An agentic Kaggle research skill built from a local book of competition write-ups, high-score notebooks, code evidence, and transferable tricks.

The goal is simple: when an AI agent sees a new Kaggle competition, it should not wait for the user to know the right algorithm. It should infer the competition shape, retrieve similar historical cases, rank the most useful evidence, and turn that into experiment hypotheses.

## What This Is For

- Autonomous Kaggle competition research.
- Retrieving similar historical competitions from a book-derived catalog.
- Inferring likely algorithm families from slug, metric, data schema, README, sample columns, or failure symptoms.
- Extracting transferable tricks with source-backed code snippets when available.
- Helping an AI agent produce a first experiment queue, validation plan, and risk checklist.

This project does not claim to produce winning solutions automatically. It is a memory and retrieval layer for agentic research.

## Repository Layout

```text
kaggle-grandmaster-playbook/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── research_competition.py
│   ├── search_book_catalog.py
│   ├── extract_book_section.py
│   ├── build_book_catalog.py
│   └── sanitize_public_book.py
├── references/
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

## Book Artifacts

- `book/book.md` is the compact polished book used for high-signal reading.
- `book/book.pdf` is an exported reading copy.
- `book_full/book.md` is the larger full archive for maximum recall.
- `assets/kaggle_book_catalog.json` indexes the compact book.
- `assets/kaggle_book_catalog_full.json` indexes the full archive.

Large files are intentional. If GitHub rejects future larger artifacts, use Git LFS for `*.pdf`, `*.docx`, and very large Markdown exports.

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

Please open an issue with examples: input competition profile, expected retrieved cases, actual retrieved cases, and why the ranking should change.

## Safety Notes

- Do not commit API keys, Kaggle credentials, cookies, or local account files.
- Public book exports should be sanitized before publishing.
- Treat retrieved tricks as historical evidence, not leaderboard guarantees.
- Respect Kaggle competition rules and dataset licenses.

## License

Code and scripts are released under the repository code license. Book artifacts are separate content assets; see `CONTENT_LICENSE.md` before copying, redistributing, or using them commercially.
