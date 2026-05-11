from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import re
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = SKILL_DIR / "assets" / "kaggle_book_catalog.json"

DOMAIN_ALIASES = {
    "table": "tabular",
    "gbdt": "tabular",
    "lgbm": "tabular",
    "xgb": "tabular",
    "xgboost": "tabular",
    "catboost": "tabular",
    "nlp": "nlp_llm",
    "llm": "nlp_llm",
    "text": "nlp_llm",
    "rag": "nlp_llm",
    "retrieval": "nlp_llm",
    "vision": "cv_vision",
    "image": "cv_vision",
    "segmentation": "cv_vision",
    "detection": "cv_vision",
    "time": "timeseries",
    "forecast": "timeseries",
    "sensor": "timeseries",
    "sequence": "timeseries",
    "speech": "audio",
    "sound": "audio",
    "birdclef": "audio",
    "oof": "ensemble",
    "stacking": "ensemble",
    "blend": "ensemble",
    "pseudo": "ensemble",
    "repro": "system",
    "submit": "system",
    "kernel": "system",
    "engineering": "system",
    "rl": "rl_game",
    "game": "rl_game",
    "agent": "rl_game",
    "bandit": "rl_game",
}

DOMAIN_TERMS = {
    "tabular": "tabular table gbdt lightgbm lgbm xgboost xgb catboost categorical target encoding feature leakage 表格 树模型 特征",
    "feature": "feature engineering leakage target encoding aggregation missing label cleanup 特征 泄漏 聚合 清洗",
    "ensemble": "oof stacking blending ensemble meta pseudo label calibration fold 集成 融合 伪标签",
    "system": "repro seed stability submit package inference timeout memory kaggle kernel environment validation 复现 稳定 提交 推理",
    "deep_learning": "deep learning neural network embedding transformer mlp tabular dl 深度学习 神经网络",
    "timeseries": "time series forecasting temporal split lag rolling sensor event sequence 时序 时间序列 传感器",
    "cv_vision": "computer vision image detection segmentation classification dicom medical 3d tta augment postprocess 视觉 图像 分割 检测",
    "nlp_llm": "nlp llm text transformer deberta bert retrieval rag prompt tokenization embedding qa 文本 大模型 检索",
    "audio": "audio speech spectrogram mel librosa birdclef sound event waveform 音频 语音 声音 频谱",
    "advanced": "graph recommender optimization code golf generative probability simulation 推荐 图 优化 生成 概率",
    "rl_game": "rl reinforcement learning self-play game agent bandit imitation policy actor critic 强化学习 博弈 智能体",
}

INTENT_TERMS = {
    "code": "code implementation snippet source evidence notebook kernel reproduce 代码 证据 实现 复现",
    "strategy": "strategy solution writeup ablation insight why worked approach plan 方案 思路 复盘 消融 策略",
    "debug": "error fail mismatch submission timeout memory leakage cv lb overfit debug 修复 报错 提交 超时 内存 泄漏",
    "baseline": "baseline starter simple first experiment quick validation benchmark 入门 基线 快速",
    "high_score": "1st place gold medal top solution grandmaster high score winner 高分 第一名 金牌 优胜",
}

QUERY_EXPANSIONS = {
    "auc": "classification rank probability calibration threshold class imbalance",
    "f1": "threshold class imbalance macro micro multilabel validation",
    "rmse": "regression target transform clip residual ensemble",
    "rmspe": "regression weight target scale optiver volatility time_id",
    "map": "ranking retrieval candidate rerank recommender",
    "mAP": "detection object localization postprocess tta",
    "logloss": "probability calibration classification soft label",
    "qwk": "ordinal classification threshold quadratic weighted kappa",
    "tabular": DOMAIN_TERMS["tabular"],
    "image": DOMAIN_TERMS["cv_vision"],
    "text": DOMAIN_TERMS["nlp_llm"],
    "audio": DOMAIN_TERMS["audio"],
    "forecast": DOMAIN_TERMS["timeseries"],
    "time series": DOMAIN_TERMS["timeseries"],
}

DOMAIN_PRIORS = {
    "tabular": ["csv", "table", "tabular", "lightgbm", "xgboost", "catboost", "categorical", "numerical columns", "dataframe", "表格", "树模型"],
    "feature": ["feature", "leakage", "target encoding", "missing", "aggregation", "特征", "泄漏", "聚合", "缺失"],
    "ensemble": ["oof", "stack", "blend", "ensemble", "pseudo", "calibration", "集成", "融合", "伪标签"],
    "system": ["submission", "kernel", "timeout", "memory", "inference", "offline", "cv lb", "submit", "提交", "超时", "内存"],
    "timeseries": ["time series", "forecast", "temporal", "lag", "rolling", "sensor", "时序", "时间序列", "预测"],
    "cv_vision": ["image", "computer vision", "vision task", "detection", "segmentation", "dicom", "3d", "mask", "bbox", "图像", "视觉", "分割", "检测"],
    "nlp_llm": ["text", "nlp", "llm", "transformer", "bert", "deberta", "rag", "prompt", "文本", "大模型", "检索"],
    "audio": ["audio", "sound", "speech", "spectrogram", "mel", "birdclef", "音频", "语音", "频谱"],
    "rl_game": ["game", "agent", "rl", "self-play", "bandit", "policy", "reinforcement", "博弈", "强化学习", "智能体"],
    "advanced": ["graph", "recommend", "optimization", "code golf", "simulation", "probability", "图", "推荐", "优化"],
}


def load_catalog(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Catalog not found: {path}. Run build_book_catalog.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    d = domain.strip().lower().replace("-", "_")
    return DOMAIN_ALIASES.get(d, d)


def tokens(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    return re.findall(r"[\w\u4e00-\u9fff+#.-]+", text)


def infer_domains(query: str, explicit_domain: str | None, top_k: int = 4) -> list[str]:
    if explicit_domain:
        return [explicit_domain]
    q = query.lower()
    scores: Counter[str] = Counter()
    for domain, phrases in DOMAIN_PRIORS.items():
        for phrase in phrases:
            if phrase.lower() in q:
                scores[domain] += 3 if " " in phrase else 1
    for alias, domain in DOMAIN_ALIASES.items():
        if alias in q:
            scores[domain] += 2
    if not scores:
        return []
    return [domain for domain, _ in scores.most_common(top_k)]


def expand_query(query: str, domains: list[str]) -> str:
    expanded = [query]
    q = query.lower()
    for key, value in QUERY_EXPANSIONS.items():
        if key.lower() in q:
            expanded.append(value)
    for domain in domains:
        expanded.append(DOMAIN_TERMS.get(domain, domain))
    expanded.extend([DOMAIN_TERMS["system"], DOMAIN_TERMS["ensemble"]])
    return " ".join(expanded)


def source_bonus(entry: dict, intent: str | None) -> float:
    code_count = entry.get("code_evidence_count") or 0
    tricks_count = entry.get("tricks_count") or 0
    quality = entry.get("quality_score") or 0
    source_type = (entry.get("source_type") or "").lower()
    if intent == "code":
        return min(code_count, 20) * 2.2 + (8 if source_type == "analysis" else 0)
    if intent == "strategy":
        return min(tricks_count, 20) * 1.2 + (8 if "writeup" in source_type else 0)
    if intent == "debug":
        hay = entry.get("searchable_text", "")
        return sum(5 for t in ("submit", "timeout", "memory", "leakage", "cv", "lb", "error", "提交", "超时", "内存", "泄漏") if t in hay)
    if intent == "baseline":
        hay = entry.get("searchable_text", "")
        return sum(4 for t in ("baseline", "starter", "simple", "入门", "基线") if t in hay)
    if intent == "high_score":
        hay = entry.get("searchable_text", "")
        return math.log1p(quality) * 3 + sum(6 for t in ("1st", "first", "gold", "winner", "place", "第一", "金牌") if t in hay)
    return min(code_count, 20) * 0.5 + min(tricks_count, 20) * 0.4 + math.log1p(quality) * 1.5


def infer_intent(query: str, explicit_intent: str | None) -> str | None:
    if explicit_intent:
        return explicit_intent
    q = query.lower()
    scores: Counter[str] = Counter()
    for intent, terms in INTENT_TERMS.items():
        for t in tokens(terms):
            if t in q:
                scores[intent] += 1
    return scores.most_common(1)[0][0] if scores else None


def score_entry(entry: dict, query_tokens: list[str], domains: list[str], slug: str | None, intent: str | None) -> tuple[float, list[str]]:
    hay = entry.get("searchable_text", "")
    reasons: list[str] = []
    score = 0.0

    if slug:
        slug_l = slug.lower()
        if slug_l == (entry.get("competition_slug") or "").lower():
            score += 200
            reasons.append("exact competition slug")
        elif slug_l in hay:
            score += 80
            reasons.append("slug appears in text")

    for domain in domains:
        domain_terms = tokens(DOMAIN_TERMS.get(domain, domain))
        domain_hits = sum(1 for t in domain_terms if t in hay)
        if domain_hits:
            score += min(domain_hits, 12) * 2.5
            reasons.append(f"domain:{domain}")
        if domain in " ".join(entry.get("algo_tags", [])).lower():
            score += 18
            reasons.append(f"algo-tag:{domain}")
        chapter = entry.get("chapter", "")
        chapter_domain_hints = {
            "tabular": ["表格", "GBDT"],
            "feature": ["特征", "泄漏"],
            "ensemble": ["OOF", "Stacking"],
            "system": ["实验工程", "训练稳定"],
            "deep_learning": ["深度学习"],
            "timeseries": ["时间序列", "时序"],
            "cv_vision": ["视觉", "3D"],
            "nlp_llm": ["NLP", "LLM"],
            "audio": ["音频", "语音"],
            "advanced": ["进阶专题"],
        }
        if any(hint.lower() in chapter.lower() for hint in chapter_domain_hints.get(domain, [])):
            score += 22
            reasons.append(f"chapter:{domain}")

    term_counts: dict[str, int] = {}
    for t in query_tokens:
        if len(t) <= 1:
            continue
        if t in hay:
            term_counts[t] = hay.count(t)
            score += 4 + min(hay.count(t), 4)
    if term_counts:
        top_terms = sorted(term_counts, key=term_counts.get, reverse=True)[:6]
        reasons.append("terms:" + ",".join(top_terms))

    bonus = source_bonus(entry, intent)
    if bonus:
        score += bonus
        if intent:
            reasons.append(f"intent:{intent}")
    return score, reasons


def compact_entry(entry: dict, score: float, reasons: list[str]) -> dict:
    return {
        "score": round(score, 2),
        "reasons": reasons,
        "title": entry.get("title"),
        "chapter": entry.get("chapter"),
        "competition_slug": entry.get("competition_slug"),
        "source": entry.get("source"),
        "source_type": entry.get("source_type"),
        "anchor": entry.get("anchor"),
        "algo_tags": entry.get("algo_tags", []),
        "core_keywords": entry.get("core_keywords", [])[:12],
        "trick_highlights": entry.get("trick_highlights", [])[:8],
        "summary": entry.get("summary", "")[:700],
        "tricks_count": entry.get("tricks_count"),
        "code_evidence_count": entry.get("code_evidence_count"),
        "quality_score": entry.get("quality_score"),
    }


def print_text(results: list[dict], total: int) -> None:
    print(f"matches: {len(results)} / {total}")
    for i, item in enumerate(results, start=1):
        print(f"\n[{i}] score={item['score']} | {item['title']}")
        print(f"chapter: {item['chapter']}")
        print(f"competition: {item['competition_slug']} | source: {item['source']} | type: {item['source_type']}")
        print(f"anchor: {item['anchor']}")
        if item["reasons"]:
            print("why: " + "; ".join(item["reasons"]))
        if item["algo_tags"]:
            print("algo_tags: " + ", ".join(item["algo_tags"]))
        if item["core_keywords"]:
            print("keywords: " + ", ".join(item["core_keywords"]))
        if item["trick_highlights"]:
            print("tricks: " + " | ".join(item["trick_highlights"][:4]))
        if item["summary"]:
            print("summary: " + item["summary"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the Kaggle Grandmaster Playbook catalog.")
    parser.add_argument("--query", default="", help="Search query, e.g. 'target encoding leakage lightgbm'.")
    parser.add_argument("--domain", default=None, help="Optional domain: tabular, nlp_llm, cv_vision, timeseries, audio, ensemble, system, advanced.")
    parser.add_argument("--slug", default=None, help="Optional exact or partial Kaggle competition slug.")
    parser.add_argument("--intent", choices=sorted(INTENT_TERMS), default=None, help="Optional ranking intent: code, strategy, debug, baseline, high_score.")
    parser.add_argument("--auto", action="store_true", help="Infer domains and expand the query for autonomous agent research.")
    parser.add_argument("--recall", type=int, default=80, help="Internal candidate pool size before final ranking.")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    entries = catalog.get("entries", [])
    explicit_domain = normalize_domain(args.domain)
    seed_query = " ".join(x for x in (args.query, args.slug or "") if x)
    domains = infer_domains(seed_query, explicit_domain) if args.auto else ([explicit_domain] if explicit_domain else [])
    intent = infer_intent(seed_query, args.intent)
    q = expand_query(args.query, domains) if args.auto else args.query
    if args.slug:
        q += " " + args.slug
    q_tokens = tokens(q)

    scored = []
    for entry in entries:
        score, reasons = score_entry(entry, q_tokens, domains, args.slug, intent)
        if score > 0:
            scored.append((score, reasons, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = scored[: max(args.recall, args.limit)]
    # Lightweight diversity: avoid letting one competition dominate broad autonomous searches.
    seen_slugs: Counter[str] = Counter()
    diversified = []
    for score, reasons, entry in candidates:
        slug_key = entry.get("competition_slug") or entry.get("title") or ""
        if not args.slug and seen_slugs[slug_key] >= 2:
            score *= 0.92
            reasons = reasons + ["diversity-penalty"]
        seen_slugs[slug_key] += 1
        diversified.append((score, reasons, entry))
    diversified.sort(key=lambda x: x[0], reverse=True)
    results = [compact_entry(entry, score, reasons) for score, reasons, entry in diversified[: args.limit]]

    if args.json:
        print(json.dumps({
            "mode": "auto-research" if args.auto else "ranked",
            "domains": domains,
            "intent": intent,
            "query_expanded": q if args.auto else None,
            "candidate_count": len(candidates),
            "count": len(results),
            "results": results,
        }, ensure_ascii=False, indent=2))
    else:
        if args.auto:
            print(f"mode: auto-research | domains: {', '.join(domains) if domains else 'unclassified'} | intent: {intent or 'general'}")
        print_text(results, len(entries))


if __name__ == "__main__":
    main()
