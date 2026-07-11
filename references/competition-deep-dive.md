# Source Competition Deep Dive

Use this protocol whenever retrieval surfaces a knowledge point that may influence an experiment. The catalog hit is a lead, not proof.

## Required Sequence

1. Open the source competition's official overview, data, evaluation and rules pages.
2. Establish the original prediction unit, metric behavior, split boundary, resource limits and external-data rules.
3. Read the cited full-book anchor.
4. Find the original author write-up, notebook/code and relevant discussion when available.
5. Separate the claimed change from simultaneous changes and look for ablations, fold evidence, failure reports or counterexamples.
6. Compare source and current conditions using the transfer map below.
7. Mark the research task `verified`, `rejected` or `uncertain`. Do not leave a used claim as `pending`.

Do not stop after generating search queries. Execute them with web search, Kaggle pages, Kaggle CLI or available browser tools. Prefer official pages and original authors. Community summaries are discovery aids, not final provenance.

The default policy creates a dossier for every distinct competition in the selected evidence and mechanism bridges. Set `deep_dive.top_competitions` to a positive number only when a deliberate budget cap is needed; `0` means no source-count cap. Experiment candidates are restricted to knowledge points already present in this queue.

## Transfer Map

Record these fields for every accepted knowledge point:

| Field | Question |
|---|---|
| Source mechanism | What causal or engineering mechanism is claimed? |
| Source conditions | What data structure, split, metric and constraints made it work? |
| Current conditions | Which of those conditions exist now? |
| Dangerous mismatch | Which differences could reverse the result? |
| Evidence | What code, ablation, fold result or discussion supports the claim? |
| Failure boundary | When did it fail or stop helping? |
| Minimal test | What cheap, reversible experiment can falsify the transfer? |

Modality is a prior, not a gate. Group leakage can transfer between patients, speakers, users and scenes; temporal causality can transfer between demand forecasting and event prediction; calibration and threshold behavior can transfer across model families. Promote cross-domain evidence only through a shared mechanism and an explicit mismatch analysis.

## Custom Queries

Automatic queries are defaults. Add arbitrary natural-language questions with repeated `--query` flags or `--query-file`. Preserve each user/agent question verbatim and also run a competition-scoped version. Do not rewrite it into a fixed taxonomy and lose the original intent.

```powershell
python scripts\research_competition.py `
  --profile "workspace\competition-profile.json" `
  --query "Why did this technique improve private LB but not grouped CV?" `
  --query "Find negative evidence and failed ablations" `
  --query-file "workspace\research-questions.json" `
  --json-out "workspace\decision-brief.json" `
  --out "workspace\decision-brief.md"
```

## Research Ledger

Import generated knowledge points into the isolated competition state:

```powershell
python scripts\competition_memory.py import-research `
  --workspace "workspace" `
  --brief "workspace\decision-brief.json"
```

After inspecting sources, resolve each task:

```powershell
python scripts\competition_memory.py resolve-research `
  --workspace "workspace" `
  --id R001 `
  --status verified `
  --source-url "https://www.kaggle.com/competitions/source-slug" `
  --source-url "https://www.kaggle.com/code/author/notebook" `
  --conclusion "The gain is consistent with group-disjoint validation." `
  --transfer-conditions "Repeated entities occur in both tasks." `
  --failure-conditions "The technique is irrelevant when entities never repeat."
```

Missing source code does not make a write-up useless. Leave `implementation_evidence` empty when no code exists; judge the claim using provenance, validation evidence and transfer conditions instead.
