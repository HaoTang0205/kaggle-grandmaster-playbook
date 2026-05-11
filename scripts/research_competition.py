from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

from search_book_catalog import (
    DEFAULT_CATALOG,
    DOMAIN_TERMS,
    compact_entry,
    expand_query,
    infer_domains,
    load_catalog,
    score_entry,
    tokens,
)


PRIMARY_DOMAINS = {"tabular", "cv_vision", "nlp_llm", "audio", "timeseries", "rl_game", "advanced"}
PRIMARY_DOMAIN_MARKERS = {
    "tabular": ("tabular", "gbdt", "lightgbm", "xgboost", "catboost", "表格"),
    "cv_vision": ("cv", "vision", "image", "segmentation", "detection", "dicom", "视觉", "图像", "分割", "检测", "3d"),
    "nlp_llm": ("nlp", "llm", "text", "bert", "deberta", "rag", "文本", "大模型"),
    "audio": ("audio", "speech", "sound", "spectrogram", "birdclef", "音频", "语音", "频谱"),
    "timeseries": ("time_series", "timeseries", "forecast", "temporal", "时序", "时间序列"),
    "rl_game": ("rl", "game", "agent", "self-play", "reinforcement", "强化学习", "博弈"),
    "advanced": ("graph", "recommend", "optimization", "simulation", "probability", "图", "推荐", "优化"),
}

FAMILY_GUIDE = {
    "tabular": {
        "families": ["LightGBM/XGBoost/CatBoost", "target/frequency encoding", "adversarial validation", "OOF stacking"],
        "signals": ["CSV/table data", "categorical columns", "AUC/RMSE/logloss", "public/private shift"],
    },
    "feature": {
        "families": ["leak-free aggregation", "nested target encoding", "missing-pattern features", "external-data joins"],
        "signals": ["group IDs", "duplicate rows", "leakage risk", "train/test distribution mismatch"],
    },
    "cv_vision": {
        "families": ["CNN/ViT backbones", "segmentation or detection heads", "TTA", "postprocessing/NMS/RLE"],
        "signals": ["images/DICOM/3D volumes", "mAP/Dice/IoU", "large tiled inference", "medical or satellite imagery"],
    },
    "nlp_llm": {
        "families": ["DeBERTa/BERT fine-tuning", "retrieval + reranking", "prompt/LLM judging", "long-context chunking"],
        "signals": ["text pairs", "QA/ranking", "token limits", "label noise"],
    },
    "audio": {
        "families": ["mel spectrogram CNN", "SED attention pooling", "voice/noise filtering", "overlap-window inference"],
        "signals": ["wav/ogg/audio clips", "BirdCLEF/soundscape", "multi-label events", "weak labels"],
    },
    "timeseries": {
        "families": ["lag/rolling features", "grouped temporal CV", "sequence models", "event postprocessing"],
        "signals": ["timestamps", "forecast horizon", "sensor streams", "time leakage risk"],
    },
    "ensemble": {
        "families": ["OOF blending", "hill-climb weights", "meta models", "pseudo-labeling/calibration"],
        "signals": ["many public kernels", "unstable LB", "close CV scores", "multiple modalities"],
    },
    "system": {
        "families": ["reproducible folds", "offline package strategy", "inference acceleration", "submission sanity checks"],
        "signals": ["Kaggle notebook constraints", "timeout/memory risk", "CV/LB mismatch", "submission format errors"],
    },
    "rl_game": {
        "families": ["self-play", "policy search", "simulation heuristics", "agent evaluation harness"],
        "signals": ["game environment", "leaderboard agents", "simulation budget", "stochastic opponents"],
    },
    "advanced": {
        "families": ["graph/recommender methods", "probabilistic simulation", "optimization heuristics", "generative augmentation"],
        "signals": ["networks", "ranking/recommendation", "combinatorial search", "simulation"],
    },
}


@dataclass
class QuerySpec:
    name: str
    text: str
    domains: list[str]
    slug: str | None = None


def read_profile(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("--profile JSON must be an object.")
        return {str(k): stringify(v) for k, v in payload.items()}
    return {"description": raw}


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(stringify(v) for v in value)
    if isinstance(value, dict):
        return " ".join(f"{k}: {stringify(v)}" for k, v in value.items())
    return str(value)


def compact_text(value: str, max_chars: int = 1800) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_chars]


def profile_text(profile: dict[str, str]) -> str:
    ordered_keys = ["slug", "title", "metric", "data", "description", "constraints", "notes"]
    parts = [profile.get(k, "") for k in ordered_keys]
    parts.extend(v for k, v in profile.items() if k not in ordered_keys)
    return compact_text(" ".join(x for x in parts if x), 2500)


def detect_signals(text: str) -> dict[str, list[str]]:
    lower = text.lower()
    groups = {
        "metrics": ["auc", "f1", "rmse", "rmspe", "mae", "map", "map@k", "dice", "iou", "logloss", "qwk", "ndcg"],
        "risks": ["leakage", "shift", "group", "temporal", "imbalance", "noisy", "timeout", "memory", "offline", "cv", "lb"],
        "data": ["csv", "image", "dicom", "mask", "bbox", "text", "audio", "spectrogram", "time series", "graph", "json"],
    }
    return {name: [term for term in terms if term in lower] for name, terms in groups.items()}


def build_queries(profile: dict[str, str], domains: list[str]) -> list[QuerySpec]:
    core = profile_text(profile)
    slug = profile.get("slug") or None
    metric = profile.get("metric", "")
    data = profile.get("data", "")
    queries: list[QuerySpec] = []
    if slug:
        queries.append(QuerySpec("exact-competition", slug, domains, slug=slug))
    queries.append(QuerySpec("competition-profile", core, domains))
    for domain in domains[:5]:
        domain_terms = DOMAIN_TERMS.get(domain, domain)
        queries.append(QuerySpec(f"domain-transfer-{domain}", f"{core} {domain_terms}", [domain]))
    queries.append(QuerySpec("validation-and-leakage", f"{core} {metric} {data} validation split leakage cv lb shift group temporal", list(dict.fromkeys(domains + ["system", "feature"]))))
    queries.append(QuerySpec("high-score-ensemble", f"{core} {metric} oof stacking blending pseudo label calibration leaderboard high score", list(dict.fromkeys(domains + ["ensemble"]))))
    queries.append(QuerySpec("code-evidence", f"{core} notebook kernel code implementation training inference reproducible", list(dict.fromkeys(domains + ["system"]))))
    return queries


def primary_domains(domains: list[str]) -> list[str]:
    return [domain for domain in domains if domain in PRIMARY_DOMAINS]


def modality_fit(entry: dict, primaries: list[str]) -> tuple[int, str]:
    if not primaries:
        return 0, "unspecified"
    tags = " ".join(entry.get("algo_tags", [])).lower()
    chapter = (entry.get("chapter") or "").lower()
    hay = entry.get("searchable_text", "")
    score = 0
    for domain in primaries:
        if domain in tags:
            score += 3
        if domain in hay:
            score += 2
        if domain == "tabular" and any(x in tags + " " + chapter for x in ("tabular", "gbdt", "表格")):
            score += 3
        if domain == "cv_vision" and any(x in tags + " " + chapter for x in ("cv", "vision", "视觉", "3d")):
            score += 3
        if domain == "audio" and any(x in tags + " " + chapter for x in ("audio", "speech", "音频", "语音")):
            score += 3
        if domain == "nlp_llm" and any(x in tags + " " + chapter for x in ("nlp", "llm", "文本")):
            score += 3
        if domain == "timeseries" and any(x in tags + " " + chapter for x in ("time_series", "timeseries", "时序", "时间序列")):
            score += 3
    if score >= 4:
        return score, "direct"
    if any(x in tags for x in ("ensemble", "feature", "system")):
        return score, "adjacent"
    return score, "analogy"


def conflicting_primary_domains(entry: dict, primaries: list[str]) -> list[str]:
    if not primaries:
        return []
    allowed = set(primaries)
    text = " ".join(
        [
            " ".join(entry.get("algo_tags", [])),
            entry.get("chapter") or "",
            entry.get("title") or "",
            " ".join(entry.get("core_keywords", [])),
        ]
    ).lower()
    conflicts = []
    for domain, markers in PRIMARY_DOMAIN_MARKERS.items():
        if domain in allowed:
            continue
        if any(marker in text for marker in markers):
            conflicts.append(domain)
    return conflicts


def merge_results(catalog: dict, queries: list[QuerySpec], per_query: int, domains: list[str]) -> list[dict]:
    by_anchor: dict[str, dict] = {}
    entries = catalog.get("entries", [])
    primaries = primary_domains(domains)
    for spec in queries:
        query_domains = spec.domains or infer_domains(spec.text, None)
        expanded = expand_query(spec.text, query_domains)
        q_tokens = tokens(expanded)
        scored = []
        for entry in entries:
            score, reasons = score_entry(entry, q_tokens, query_domains, spec.slug, intent=None)
            if score > 0:
                fit_score, fit_label = modality_fit(entry, primaries)
                conflicts = conflicting_primary_domains(entry, primaries)
                if spec.slug and (entry.get("competition_slug") or "").lower() == spec.slug.lower():
                    score += 80
                    fit_label = "exact"
                elif primaries:
                    score += fit_score * 9
                    if conflicts and fit_label == "direct":
                        fit_label = "mixed"
                        score *= 0.78
                    if fit_label == "analogy":
                        score *= 0.82
                    elif fit_label == "adjacent":
                        score *= 0.94
                reasons = reasons + [f"modality-fit:{fit_label}"]
                if conflicts:
                    reasons.append("cross-modal:" + ",".join(conflicts[:3]))
                scored.append((score, reasons, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        for score, reasons, entry in scored[:per_query]:
            anchor = entry.get("anchor") or entry.get("id")
            current = by_anchor.get(anchor)
            item = compact_entry(entry, score, reasons)
            item["matched_queries"] = [spec.name]
            if not current or item["score"] > current["score"]:
                if current:
                    item["matched_queries"] = sorted(set(current["matched_queries"] + item["matched_queries"]))
                by_anchor[anchor] = item
            else:
                current["matched_queries"] = sorted(set(current["matched_queries"] + [spec.name]))
    results = list(by_anchor.values())
    results.sort(
        key=lambda item: (
            "modality-fit:exact" in item.get("reasons", []),
            "modality-fit:direct" in item.get("reasons", []),
            "modality-fit:mixed" not in item.get("reasons", []),
            len(item["matched_queries"]),
            item["score"],
        ),
        reverse=True,
    )
    return results


def family_hypotheses(domains: list[str], signals: dict[str, list[str]]) -> list[dict]:
    hypotheses = []
    for domain in domains:
        guide = FAMILY_GUIDE.get(domain)
        if not guide:
            continue
        evidence = sorted(set(guide["signals"]).intersection(set(sum(signals.values(), []))))
        hypotheses.append({
            "domain": domain,
            "candidate_families": guide["families"],
            "profile_signals": evidence or guide["signals"][:3],
        })
    if not hypotheses:
        hypotheses.append({
            "domain": "unclassified",
            "candidate_families": ["start with data inspection, metric-aware validation, strong baseline, then retrieve again"],
            "profile_signals": ["not enough explicit competition signals"],
        })
    return hypotheses


def render_markdown(payload: dict) -> str:
    lines = ["# Kaggle Grandmaster Research Brief", ""]
    profile = payload["profile"]
    lines += ["## Competition Profile"]
    for key in ("slug", "title", "metric", "data", "constraints"):
        if profile.get(key):
            lines.append(f"- {key}: {profile[key]}")
    lines.append(f"- inferred_domains: {', '.join(payload['domains']) if payload['domains'] else 'unclassified'}")
    for name, values in payload["signals"].items():
        if values:
            lines.append(f"- {name}: {', '.join(values)}")
    lines += ["", "## Algorithm Family Hypotheses"]
    for hyp in payload["family_hypotheses"]:
        lines.append(f"- {hyp['domain']}: {', '.join(hyp['candidate_families'])}")
    lines += ["", "## Top Historical Evidence"]
    lines.append("| Rank | Score | Case | Why It Matches | Anchor |")
    lines.append("|---:|---:|---|---|---|")
    for idx, item in enumerate(payload["results"], start=1):
        why = "; ".join(item.get("reasons", [])[:4])
        case = item.get("title") or item.get("source") or item.get("competition_slug")
        lines.append(f"| {idx} | {item['score']} | {case} | {why} | `{item['anchor']}` |")
    lines += ["", "## Agent Next Actions"]
    lines.append("- Start with a data/metric audit: schema, row counts, IDs/groups/timestamps, target distribution, and metric reproduction.")
    lines.append("- Establish a trustworthy validation split before optimizing model families.")
    lines.append("- Extract the top 1-3 anchors before writing detailed strategy notes.")
    lines.append("- Translate each historical trick into a current-competition experiment with validation and failure checks.")
    lines.append("- Prefer source-backed code snippets when the extracted section contains code evidence.")
    lines.append("- Track OOF, fold scores, config, feature list, seed, and submission hash for every serious experiment.")
    lines.append("- Capture useful new write-ups/code with collect_competition_experience.py before the context is lost.")
    lines.append("- If the match is weak, inspect the data schema first, then rerun retrieval with stronger profile signals.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an autonomous Kaggle research brief from a competition profile.")
    parser.add_argument("--profile", type=Path, default=None, help="Optional JSON/TXT/MD file with competition profile text.")
    parser.add_argument("--slug", default="", help="Kaggle competition slug.")
    parser.add_argument("--title", default="", help="Competition title.")
    parser.add_argument("--description", default="", help="Problem statement, README excerpt, or data description.")
    parser.add_argument("--metric", default="", help="Evaluation metric.")
    parser.add_argument("--data", default="", help="Data schema, modalities, columns, files, or sample descriptions.")
    parser.add_argument("--constraints", default="", help="Notebook, runtime, submission, memory, or inference constraints.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--per-query", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    profile = read_profile(args.profile)
    for key in ("slug", "title", "description", "metric", "data", "constraints"):
        value = getattr(args, key)
        if value:
            profile[key] = value
    text = profile_text(profile)
    domains = infer_domains(text, None, top_k=5)
    # System and ensemble lessons are useful for nearly every competition, but they should not hide the primary modality.
    if domains and "system" not in domains:
        domains.append("system")
    signals = detect_signals(text)
    queries = build_queries(profile, domains)
    results = merge_results(load_catalog(args.catalog), queries, args.per_query, domains)[: args.limit]
    payload = {
        "mode": "autonomous-competition-research",
        "profile": profile,
        "domains": domains,
        "signals": signals,
        "family_hypotheses": family_hypotheses(domains, signals),
        "queries": [spec.__dict__ for spec in queries],
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(payload))


if __name__ == "__main__":
    main()
