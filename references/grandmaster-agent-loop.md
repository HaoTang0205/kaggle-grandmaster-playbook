# Grandmaster Agent Loop

Use this loop when the agent is expected to operate with minimal user direction.

## 1. Competition Intake

- Capture slug, title, metric, deadline/status, data modalities, target, sample submission, runtime constraints, and known public kernels.
- If the user only gives a URL or vague description, inspect the competition page/data first with the regular Kaggle tooling, then run this skill.
- Translate the task into likely domains and validation hazards before choosing models.

## 2. Data And Metric Audit

- Read file structure, row counts, IDs/groups/timestamps, missingness, target distribution, duplicate risk, leakage candidates, and test/train shift.
- Reimplement or sanity-check the metric locally.
- Decide the validation split before optimizing models.

## 3. Historical Retrieval

- Run `scripts/research_competition.py` with the profile.
- Search exact slug first when available, then same modality+metric, then same validation hazard, then adjacent-domain analogies.
- Extract only the strongest sections and convert them into experiments, not generic advice.

## 4. Baseline And Evidence

- Build the simplest reliable baseline that matches the metric and split.
- Save OOF predictions, fold scores, seed, config, feature list, and submission hash.
- Treat every trick as a hypothesis that needs an ablation or a clear reason.

## 5. Experiment Queue

For each proposed experiment, track:

- Hypothesis.
- Historical evidence anchor.
- Implementation change.
- Expected local metric movement.
- Failure mode.
- Stop condition.

Prefer a small number of high-signal experiments over many untracked changes.

## 6. Submission Safety

- Validate row order, ID alignment, probability range, missing predictions, dtype, compression, and notebook/package constraints.
- Compare local CV, public LB, and known baselines before trusting a jump.
- If CV/LB disagree, retrieve `system`, `feature`, and `ensemble` cases again.

## 7. Knowledge Capture

- Save useful write-ups, final kernels, discussion notes, validation decisions, and failed experiments.
- Run `scripts/collect_competition_experience.py` to create a staging card.
- Refine the card with deeper LLM/human reading before appending to the final book.
- Rebuild the catalog after appending new book sections.
