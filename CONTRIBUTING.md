# Contributing

Thanks for helping improve the Kaggle Grandmaster Playbook.

This project is especially interested in making AI agents better at autonomous Kaggle research: reading a competition, inferring likely solution families, retrieving historical evidence, and producing useful experiments.

## Good Issue Reports

Please include:

- Competition profile or slug.
- Query or command you ran.
- Expected historical cases.
- Actual historical cases.
- Why the ranking or output should change.

Example:

```text
Profile: audio multi-label BirdCLEF-style competition, weak labels, AUC metric.
Expected: BirdCLEF SED / spectrogram / overlap inference cases near the top.
Actual: generic CV cases ranked above audio cases.
Reason: audio modality should dominate; CV should appear only as spectrogram analogy.
```

## Useful Pull Requests

- Add or improve domain inference rules in `scripts/research_competition.py`.
- Improve ranking in `scripts/search_book_catalog.py`.
- Add tests or reproducible examples for bad retrieval cases.
- Improve `references/search-rules.md` and `references/output-schema.md`.
- Add cleaner book export and sanitization workflows.

## Data And Safety

- Do not submit private API keys, Kaggle credentials, cookies, or local account files.
- Do not include private absolute paths in public book exports.
- Keep source attribution when adding new cases.
- Respect Kaggle rules, notebook licenses, and dataset licenses.

## Development Checks

```powershell
python scripts\research_competition.py --description "CSV tabular AUC categorical leakage" --metric "AUC" --data "train.csv test.csv" --limit 5
python scripts\search_book_catalog.py --auto --query "birdclef audio spectrogram sed overlap inference" --limit 5
```

If you use this as a Codex/OpenAI skill, validate the skill folder with your local skill validator.
