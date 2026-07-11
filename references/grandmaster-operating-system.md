# Grandmaster Operating System

## State Machine

```text
INTAKE -> DATA_AUDIT -> VALIDATION -> BASELINE -> SEARCH -> ENSEMBLE -> FINALIZE
                                  ^        |          |
                                  |        v          v
                                DEBUG <- REFLECT <- SUBMIT_PROBE
```

Do not advance because a file exists. Advance only when the current phase gate passes.

## Phase Gates

### Intake

- Official metric and submission format are understood.
- Prediction unit and major data modalities are identified.
- Rules for external data, pretrained models and internet are checked.

### Data Audit

- All provided data sources are inventoried.
- Target, IDs, groups, timestamps and duplicate risks are reviewed.
- Train/test shift hypotheses are written down.

### Validation

- Local metric passes edge-case tests.
- Fold construction matches the hidden-test relationship.
- Leakage-sensitive transforms are fold-safe.
- OOF artifacts and fold assignments are saved.

### Baseline

- End-to-end training and inference run successfully.
- Submission assertions pass.
- Score, variance, runtime and artifact hashes are recorded.

### Search

- Every experiment has a parent, one major change and a falsifiable hypothesis.
- The result includes rich diagnostics and a parent comparison.
- Failed branches are preserved and labeled.
- Every historical claim used by an experiment has a source-competition deep-dive task.
- Cross-domain evidence is transferred through a shared mechanism and explicit mismatch analysis.

### Ensemble

- Components have credible OOF predictions.
- Diversity is measured by prediction/residual correlation and slice behavior.
- Blend/stack weights are learned without test or public-LB leakage.

### Finalize

- Full-data retraining preserves preprocessing and configuration parity.
- Inference fits resource limits with margin.
- The submission is reproducible and structurally valid.

## Search Policy

### Breadth

Start with 2-4 branches only when they represent genuinely different hypotheses. Examples:

- Tree model vs neural representation.
- Raw input vs task-specific representation.
- Group split vs temporal split hypothesis.
- Classification vs regression/ordinal formulation.

Do not call five random seeds five branches.

### Directed Refinement

Within a promising branch:

1. Compare to parent.
2. Identify the dominant error slice or bottleneck.
3. Select one component.
4. Predict which diagnostic should move.
5. Implement one change.
6. Run the cheapest test that can falsify it.
7. Promote, revise or discard.

### Plateau

After three successful non-improving experiments:

- Stop hyperparameter polishing.
- Re-read failed branches and current evidence gaps.
- Retrieve a different validation risk, representation, model family or postprocessing mechanism.
- Open a new branch from the best stable baseline.

### Reflection

Compare parent and child using:

- Code/config diff.
- Mean and per-fold score.
- Fold variance and worst fold.
- Class/group/time/error slices.
- Runtime, peak memory and inference latency.
- Prediction/residual correlation.
- New failure modes.

Write the lesson as a conditional mechanism: "When condition C holds, change X affected diagnostic Y, suggesting mechanism M." Avoid unconditional rules from one experiment.

Pre-register diagnostic changes in the ablation matrix and complete standardized result analysis before starting another branch.

## Budget Policy

Allocate a competition budget before search:

- 15% intake, audit and validation.
- 20% reliable baselines and pipeline hardening.
- 45% high-information component search.
- 15% ensembling/postprocessing.
- 5% final reproducibility and packaging.

Adjust by modality and deadline, but never reduce validation to zero.

Use kill gates:

- Smoke test before full training.
- One fold/short epoch before all folds when representative.
- Runtime and memory estimate before expensive branching.
- Stop when the predicted diagnostic does not move.

## Memory Policy

Short-term memory contains current profile, open hypotheses, active branches and diagnostics.

Long-term memory contains only reviewed lessons with:

- Source or experiment provenance.
- Conditions where it applies.
- Evidence and counterevidence.
- Implementation pattern.
- Validation check.
- Failure modes.

Do not copy raw logs into long-term memory. Distill them after comparison.

At competition end, create a postmortem card, review mechanism/provenance/transfer boundaries, and promote only a hash-verified card into the learned-experience catalog. Preserve negative and inconclusive results.
