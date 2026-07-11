# Pipeline Audit

`scripts/audit_pipeline.py` is a deterministic first-pass review for generated Python pipelines. It does not prove that code is leakage-free.

## Severity

- `blocker`: direct test fitting, test-target access or syntax failure. Do not execute.
- `high`: likely split/preprocessing mismatch under known group/time risks. Resolve before trusting CV.
- `medium`: missing metric/template/data-usage evidence. Review and document.
- `low`: reproducibility hygiene such as missing seeds.
- `info`: dynamic behavior that requires runtime logging or human/LLM review.

## Current Checks

- Learned `.fit`, `.fit_transform` or `.partial_fit` receives a test-like object.
- A target candidate is accessed from a test-like object.
- Train and test are concatenated before preprocessing/modeling.
- Group/time risks coexist with random KFold/train-test splitting.
- Learned preprocessing appears before the first validation split.
- Profile-inventoried files are not referenced and no dynamic discovery is visible.
- Official metric, sample-submission template or reproducibility seed is not visible.

## Required Semantic Review

Static analysis cannot reliably determine:

- Whether a feature uses future or target-derived information through helper functions.
- Whether transductive preprocessing is allowed and harmless.
- Whether fold construction truly keeps entities/duplicates disjoint.
- Whether external data and pretrained weights are competition-legal.
- Whether metric and postprocessing behavior exactly match the official evaluator.
- Whether every dynamically discovered file is actually consumed.

Review the complete data lineage, fold construction and runtime logs after the static pass. Add a regression fixture whenever a real leakage bug escapes or a safe pattern is repeatedly misclassified.
