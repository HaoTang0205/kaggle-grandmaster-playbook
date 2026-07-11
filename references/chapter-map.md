# Kaggle Experience Book Chapter Map

Use this map to route a new competition or question to the right part of the local book catalog.

| Domain | Chapter | Best Search Signals |
|---|---|---|
| `system` | 第1章 实验工程与训练稳定性 | reproducibility, seed, CV stability, local/hidden mismatch, submit, packaging, inference timeout, memory, environment, offline install |
| `feature` | 第2章 特征工程与泄漏控制 | feature engineering, leakage, target encoding, grouped data, missing values, aggregation, label cleanup, public/private split |
| `ensemble` | 第3章 OOF、Stacking 与元学习 | OOF, stacking, blending, meta model, pseudo label, calibration, fold ensemble, leaderboard stability |
| `tabular` | 第4章 表格树模型与 GBDT 实战 | LightGBM, XGBoost, CatBoost, ranking, categorical, tabular baseline, feature importance, monotonic, adversarial validation |
| `deep_learning` | 第5章 表格深度学习 | tabular neural network, embeddings, FT-Transformer, MLP, multimodal tabular, deep tabular ensemble |
| `timeseries` | 第6章 时间序列与时序验证 | forecasting, sensor, lag, rolling, temporal split, grouped time CV, event detection, sequence validation |
| `cv_vision` | 第7章 视觉与 3D 感知 | image, detection, segmentation, classification, DICOM, medical, 3D, TTA, augment, postprocess |
| `nlp_llm` | 第8章 NLP 与 LLM | text classification, retrieval, QA, DeBERTa, BERT, LLM, RAG, prompt, tokenization, long context |
| `audio` | 第9章 音频与语音 | audio, speech, birdclef, spectrogram, librosa, mel, sound event, waveform, fold by recording |
| `advanced` | 第10章 进阶专题：生成、图、概率与推荐 | graph, recommender, optimization, code golf, generative, probability, simulation, RL/game special cases |

Domain aliases accepted by the search script:

| Alias | Canonical Domain |
|---|---|
| `table`, `gbdt`, `lgbm`, `xgb`, `catboost` | `tabular` |
| `nlp`, `llm`, `text`, `rag`, `retrieval` | `nlp_llm` |
| `vision`, `image`, `computer vision`, `segmentation`, `detection` | `cv_vision` |
| `forecast`, `sensor` | `timeseries` |
| `speech`, `sound`, `birdclef` | `audio` |
| `oof`, `stacking`, `blend`, `pseudo` | `ensemble` |
| `submit`, `kernel`, `engineering` | `system` |
| `rl`, `game`, `bandit` | `rl_game` |

Practical routing:

- If the question is "how do I improve score?", search by domain plus metric and baseline model.
- If the question is "why CV and LB disagree?", search `system`, `feature`, and `ensemble`.
- If the question is "which tricks are transferable?", search broad first, then extract 1-3 sections with matching problem signals.
- If the question is "write a competition plan", search the closest domain, then add `system` and `ensemble` as secondary domains.
- If the question is "debug submission", search `system` first, then the task domain.
