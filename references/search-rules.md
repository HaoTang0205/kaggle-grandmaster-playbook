# Search Rules

Use these rules to query and interpret the local Kaggle experience catalog.

## Autonomous Research First

When the user only provides a competition, do not ask them to choose an algorithm family. Build a profile from slug, title, metric, file types, columns, target, runtime constraints, and observed failure signals. Then run broad recall with `research_competition.py` or `search_book_catalog.py --auto`.

## Query Construction

Build queries from five ingredients:

- Competition identity: slug, title, host, year.
- Data modality: tabular, image, text, audio, time series, graph, game, optimization.
- Metric and target: AUC, F1, RMSE, MAP, mAP, logloss, ranking, interval F1.
- Failure signals: leakage, unstable CV, class imbalance, noisy labels, hidden test shift, timeout, memory pressure.
- Method family: LightGBM, CatBoost, DeBERTa, ViT, EfficientNet, U-Net, spectrogram, OOF, stacking, TTA, pseudo labels.

## Retrieval Priority

1. Exact competition slug or close prior competition.
2. Same data modality and metric.
3. Same validation risk, such as grouped split or temporal split.
4. Same model family.
5. Same engineering constraint, such as offline packages or inference server.
6. Adjacent-domain analogies, such as audio-as-image spectrograms, tabular+image fusion, text retrieval for recommendation, or segmentation postprocessing for 3D detection.

## Reading Priority

- Read catalog summaries first.
- Extract full sections only for the strongest 1-3 hits.
- For code implementation, prefer sections with nonzero `code_evidence_count`.
- For strategic insight, prefer entries with strong writeup-derived summary or many tricks.
- For debugging, prefer system/validation entries even if the modality differs.

## Combining Results

When writing advice for a new competition:

- Start with inferred algorithm-family hypotheses, not with a single chosen model.
- Separate "directly applicable" from "inspired by analogy".
- Turn repeated tactics across hits into candidate experiments.
- Translate old code into the current competition's data and metric.
- Name validation checks before leaderboard expectations.
- Preserve uncertainty when the match is weak.
