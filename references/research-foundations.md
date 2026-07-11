# Research Foundations

This skill borrows mechanisms from primary research and official implementations, then adapts them to a local Kaggle evidence library. The sources support design choices; they do not prove that this skill itself reaches Grandmaster performance.

## MLE-Bench

- [OpenAI MLE-Bench repository](https://github.com/openai/mle-bench)
- [MLE-Bench paper](https://arxiv.org/abs/2410.07095)

Relevant lessons:

- Evaluate on many heterogeneous Kaggle tasks instead of one showcase competition.
- Separate public task material from held-out grading data.
- Preserve run metadata, code, logs and submissions so results can be reproduced and graded.
- Treat valid submission generation as a distinct engineering capability.

Playbook consequence: maintain retrieval benchmarks, competition-isolated workspaces, explicit submission gates and reproducible experiment artifacts.

## MLE-STAR

- [Google Research overview](https://research.google/blog/mle-star-a-state-of-the-art-machine-learning-engineering-agents/)

Relevant lessons:

- Search for task-specific current methods instead of relying only on an LLM's remembered defaults.
- Refine individual pipeline components rather than rewriting a monolithic script each round.
- Use ablations to identify the component with the largest performance contribution.
- Add dedicated leakage and data-usage checks because executable code can still be logically wrong.

Playbook consequence: combine the local historical library with live primary-source research, require component-level experiments, and run leakage/data-usage gates before execution.

## AIDE

- [AIDE official repository](https://github.com/WecoAI/aideml)

Relevant lessons:

- Represent candidate solutions as branches in code space.
- Reuse and refine promising solutions rather than restarting from scratch.
- Preserve a visible solution tree and metric feedback.

Playbook consequence: preserve parent experiment IDs and the best reproducible artifact; open distinct branches when uncertainty is real or a branch plateaus.

## MARS

- [Google Research publication](https://research.google/pubs/mars-modular-agent-with-reflective-search-for-automated-ai-research/)

Relevant lessons:

- Plan under an explicit execution budget.
- Decompose design, implementation and evaluation.
- Compare branches to assign credit and distill high-signal lessons.
- Cross-branch lessons can matter more than repeatedly polishing one branch.

Playbook consequence: rank experiments by expected information gain and cost, enforce isolated changes, and trigger cross-branch exploration after repeated non-improvements.

## Reasoning As Gradient (Gome)

- [Microsoft Research publication](https://www.microsoft.com/en-us/research/publication/reasoning-as-gradient-scaling-mle-agents-beyond-tree-search/)
- [Paper](https://arxiv.org/abs/2603.01692)

Relevant lessons:

- A scalar validation score discards most diagnostic information.
- Strong reasoning models can use structured execution feedback as an update direction.
- Success memory can provide momentum; parallel traces provide diverse search directions.

Playbook consequence: compare fold behavior, residual slices, runtime, memory and code/config differences, then state the mechanism supported by the result before choosing the next update.

## AutoKaggle

- [AutoKaggle paper](https://arxiv.org/abs/2410.20424)

Relevant lessons:

- Decompose data science into explicit phases with specialist responsibilities.
- Run code, debug from actual errors and unit-test phase outputs.
- Unit tests materially improve completion and valid-submission rates.

Playbook consequence: enforce phase gates, metric/fold/submission tests and bounded debugging loops.

## MLAgentBench

- [MLAgentBench official repository](https://github.com/snap-stanford/MLAgentBench)
- [MLAgentBench paper](https://arxiv.org/abs/2310.03302)

Relevant lessons:

- Agents need file access, code execution, experiment logs and workspace snapshots.
- Performance varies sharply on recent tasks, exposing reliance on memorized solutions.
- Long-horizon planning and hallucination remain major failure modes.

Playbook consequence: keep current-method research, execution-grounded decisions, explicit state and short diagnostic loops.

## Agent K

- [Agent K paper](https://arxiv.org/abs/2411.03562)

Relevant lessons:

- Separate short-term and long-term memory.
- Retrieve experience selectively instead of placing the entire archive in context.
- Use environmental rewards to update decisions and optimization priorities.

Playbook consequence: retrieve small evidence packets, keep a per-competition experiment ledger and promote only supported lessons to long-term memory.

## Experiment Tracking And Reproducibility

- [MLflow Tracking official documentation](https://mlflow.org/docs/latest/ml/tracking/)
- [NeurIPS Paper Checklist guidelines](https://neurips.cc/public/guides/PaperChecklist)

Relevant lessons:

- A run should preserve parameters, code version, metrics and output artifacts rather than only the best scalar score.
- Reproducibility requires data splits, hyperparameters, environment and exact execution instructions or an equivalent verifiable path.
- Experimental claims should report variation and limitations, not only central tendency.

Playbook consequence: maintain versioned experiment metadata, pre-register control/treatment/fixed conditions, compare paired folds and slices, record resources and confounders, and generate synchronized ablation/result/analysis views from one state source.
