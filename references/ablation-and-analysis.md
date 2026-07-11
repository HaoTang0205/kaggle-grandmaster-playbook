# Ablation And Result Analysis System

The JSON competition state is the source of truth. The following files are generated views under each isolated workspace's `experiment_reports/` directory:

- `ablation_matrix.csv`: pre-registered controls, treatments, fixed conditions and decisions.
- `experiment_results.csv`: normalized metrics, fold/slice results, resources, provenance and analysis status.
- `experiment_analysis_log.md`: human-readable parent/child analysis with version history.

Do not manually maintain competing copies. Use the CLI and regenerate views with `export-reports` when needed.

The schema follows the core tracking expectations in [MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/) and the experimental-detail/reproducibility expectations in the [NeurIPS Paper Checklist](https://neurips.cc/public/guides/PaperChecklist), while remaining a lightweight local format.

## Pre-Register The Ablation

An ablation row answers before execution:

- What single factor is being tested?
- What is the control and treatment?
- Which fold assignment, seed policy, data, preprocessing, metric and budget stay fixed?
- What diagnostic should move if the hypothesis is true?
- What result would falsify or leave the hypothesis inconclusive?
- Which verified research claims motivated the test?

Supported designs:

- `ofat`: one factor at a time; default for causal diagnosis.
- `factorial`: explicit interaction study when independent OFAT tests are insufficient.
- `negative_control`: a change expected not to help, used to detect leakage or evaluation artifacts.
- `sensitivity`: robustness across seeds, thresholds, folds, horizons or resource settings.

```powershell
python scripts\competition_memory.py plan-ablation `
  --workspace "workspace" `
  --id A003 `
  --design ofat `
  --parent-experiment E01 `
  --component features `
  --factor "patient normalization" `
  --control disabled `
  --treatment enabled `
  --fixed-condition "folds=v2" `
  --fixed-condition "seed_policy=42,43,44" `
  --hypothesis "Fold-safe patient normalization reduces site shift." `
  --expected-signal "OOF gain on unseen-site slices without higher fold variance." `
  --research-id R001 `
  --cost low
```

Bind the resulting treatment run to the plan with `--ablation-id A003`. The CLI rejects a mismatched control parent and unverified `research_id`.

Record code/data/config/environment/fold/metric versions, seeds and a parameter snapshot whenever available. These fields remain optional for exploratory runs, but a result should not be promoted to the reproducible best artifact while key provenance is unknown.

For long/background jobs, register `--status running` first and close the same ID with `competition_memory.py finalize`. This preserves one run identity instead of creating a second result row.

## Analyze Every Diagnostic Run

After recording a treatment, run `analyze` before selecting the next experiment:

```powershell
python scripts\competition_memory.py analyze `
  --workspace "workspace" `
  --id E03 `
  --verdict partially_supported `
  --mechanism "Normalization reduced site-specific scale shift." `
  --confounder "Only one seed completed" `
  --slice-finding "Unseen-site AUC improved; common-site AUC was flat" `
  --resource-tradeoff "+3 minutes, memory unchanged" `
  --next-action "Repeat the same ablation on two additional seeds"
```

Verdicts:

- `supported`: predicted diagnostics moved consistently and dangerous confounders are controlled.
- `partially_supported`: some predicted diagnostics moved, but the mechanism or scope is narrower than claimed.
- `not_supported`: the expected signal did not move or moved in the wrong direction under a valid test.
- `inconclusive`: failures, variance, confounding or insufficient power prevent attribution.

## Interpretation Rules

Never decide from mean CV alone. Review together:

1. Direction-aware CV delta and change in fold variance.
2. Paired fold deltas and directional fold wins. Do not treat a small fold count as formal significance.
3. Slice deltas aligned with the mechanism claimed in the hypothesis.
4. Calibration, threshold, robustness or residual diagnostics when relevant.
5. Runtime, peak memory and inference/submission cost.
6. Code/config diff and whether all declared fixed conditions were actually fixed.
7. Public LB only as secondary shift evidence, never as causal proof.

If several major components changed, mark the result `inconclusive` or register a factorial design. If the treatment wins only one anomalous fold, investigate the slice/group composition before promotion. A failed experiment still needs a diagnosis when it changes what the team believes.

## Report Refresh

Reports update automatically after state mutations. They can also be rebuilt deterministically:

```powershell
python scripts\competition_memory.py export-reports --workspace "workspace"
```
