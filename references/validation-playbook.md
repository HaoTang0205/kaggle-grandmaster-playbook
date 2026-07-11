# Validation Playbook

Validation is a model of the hidden test process. Choose the split from the prediction unit and data-generating process, not from whichever split produces the highest score.

## Universal Gates

1. Reimplement the official metric and test tiny edge cases.
2. Identify the prediction unit: row, entity, timestamp, image, patient, recording, query, edge or episode.
3. Identify dependencies that make examples non-independent.
4. Fit preprocessing, encoders, thresholds, calibrators and feature selection inside each fold.
5. Save fold assignments and OOF predictions.
6. Report mean, spread, worst fold and important slice metrics.
7. Validate the sample-submission contract before serious training.

## Tabular

- Use stratification only when rows are independent.
- Keep customers, users, households, devices, sessions and repeated entities group-disjoint.
- Keep duplicate and near-duplicate clusters in one fold.
- For target/frequency encodings, generate training features out-of-fold and fit test mappings on full train only.
- Run adversarial validation when train/test origins, collection dates or populations differ.
- Compare random and group/time CV only as a diagnostic; choose the split closest to the hidden-test relationship.

## Time Series And Events

- Use forward, expanding-window or blocked validation.
- Respect forecast horizon and gap/embargo requirements.
- Compute lag and rolling features from information available at prediction time.
- Avoid random row splits even when rows look tabular.
- Evaluate by important groups/horizons, not only global mean.

## Vision And Medical Imaging

- Split by patient, study, slide, scene, video or acquisition session where relevant.
- Hash or embed images to find exact/near duplicates before folding.
- Keep tiles from one parent image/slide in the same fold.
- Fit normalization using training-fold data or fixed pretrained statistics.
- Validate the complete inference path: tiling, overlap, TTA, thresholding, connected components and resizing.

## NLP And LLM Tasks

- Split repeated authors, prompts, questions, documents or source groups when they can leak style/content.
- Detect near-duplicate text and templated examples.
- Keep retrieval corpus construction fold-safe.
- Tune thresholds and calibrators on OOF predictions.
- Check truncation, token-length and language/domain slices.

## Audio

- Split by recording, speaker, site, device, session or original long recording.
- Keep chunks from one recording in the same fold.
- Track rare-class fold coverage for multilabel tasks.
- Validate clip aggregation, overlapping-window inference and smoothing separately from the encoder.
- Audit external recordings for duplicates and label-space mismatches.

## Ranking And Recommendation

- Split by time and query/user/item exposure according to deployment.
- Ensure candidate generation uses only information available at prediction time.
- Evaluate the same cutoff and tie behavior as the official metric.
- Save OOF candidate sets and reranker scores; a reranker cannot recover missing candidates.

## Graphs

- Match the hidden evaluation regime: transductive vs inductive, node vs edge, temporal vs static.
- Prevent target edges or future neighborhoods from entering message passing/features.
- Group connected components or entities when random edge splits would leak topology.

## Simulation And Game Agents

- Use multiple seeds, maps, starting positions and opponent styles.
- Keep a fixed regression suite of replays and adversarial opponents.
- Track win rate confidence intervals, runtime, invalid actions and timeout rate.
- Do not optimize against one leaderboard opponent snapshot.

## CV/LB Diagnostics

- Strong CV and weak LB: inspect split mismatch, leakage, shift, metric reproduction and submission alignment.
- Weak CV and strong LB: suspect public-LB noise, overlap/leakage or a nonrepresentative validation set.
- High fold variance: inspect group sizes, class coverage, seeds and distribution differences.
- Large public/private shakeup risk: reduce LB feedback frequency and favor robust OOF evidence.

## Final Submission Gate

- Correct columns, order, row count and IDs.
- No NaN/Inf; valid ranges and dtypes.
- Training and inference preprocessing are identical.
- Runtime and memory fit platform limits with margin.
- Model/checkpoint/config versions are recorded.
- A tiny end-to-end rerun reproduces the saved submission hash or score within tolerance.
