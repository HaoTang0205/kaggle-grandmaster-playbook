from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import lru_cache
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from ipaddress import ip_address
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlsplit
import warnings
import zlib

from evidence_safety import evidence_risk_flags


SKILL_DIR = Path(__file__).resolve().parents[1]
CURATED_CATALOG = SKILL_DIR / "assets" / "kaggle_book_catalog.json"
FULL_CATALOG = SKILL_DIR / "assets" / "kaggle_book_catalog_full.json"
LEARNED_CATALOG = SKILL_DIR / "assets" / "learned_experience_catalog.json"
DEFAULT_POLICY_PATH = SKILL_DIR / "config" / "retrieval_policy.json"
INDEX_SCHEMA_VERSION = 8
CATALOGS_ENV = "KAGGLE_GM_CATALOGS"
CACHE_DIR_ENV = "KAGGLE_GM_CACHE_DIR"

PRIMARY_DOMAINS = {
    "tabular",
    "deep_learning",
    "timeseries",
    "cv_vision",
    "nlp_llm",
    "audio",
    "rl_game",
    "advanced",
}
SUPPORT_DOMAINS = {"feature", "ensemble", "system"}


def safe_public_url(value: str) -> bool:
    try:
        parsed = urlsplit((value or "").strip())
        host = parsed.hostname or ""
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return False
        if host.lower() == "localhost" or host.lower().endswith(".local"):
            return False
        try:
            address = ip_address(host)
        except ValueError:
            return True
        return not (address.is_private or address.is_loopback or address.is_link_local)
    except ValueError:
        return False

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
    "forecast": "timeseries",
    "sensor": "timeseries",
    "speech": "audio",
    "sound": "audio",
    "birdclef": "audio",
    "oof": "ensemble",
    "stacking": "ensemble",
    "blend": "ensemble",
    "pseudo": "ensemble",
    "submit": "system",
    "kernel": "system",
    "engineering": "system",
    "rl": "rl_game",
    "game": "rl_game",
    "bandit": "rl_game",
}

DOMAIN_PHRASES = {
    "tabular": (
        "tabular", "table data", "csv", "dataframe", "categorical", "numerical columns",
        "lightgbm", "xgboost", "catboost", "gbdt", "表格", "树模型", "类别特征",
    ),
    "feature": (
        "feature engineering", "target encoding", "aggregation", "missing values", "leakage",
        "特征工程", "目标编码", "聚合", "缺失值", "泄漏",
    ),
    "ensemble": (
        "oof", "stacking", "blending", "ensemble", "pseudo label", "calibration",
        "集成", "融合", "伪标签", "校准",
    ),
    "system": (
        "submission", "kaggle kernel", "notebook constraint", "timeout", "memory", "offline",
        "inference", "reproducible", "cv lb", "提交", "超时", "内存", "离线", "复现",
    ),
    "deep_learning": (
        "neural network", "deep learning", "embedding", "transformer", "mlp", "深度学习", "神经网络",
    ),
    "timeseries": (
        "time series", "forecast", "forecasting", "demand forecasting", "temporal", "timestamp", "lag", "rolling", "sensor",
        "时间序列", "时序", "时间戳", "滞后", "滚动",
    ),
    "cv_vision": (
        "computer vision", "image", "dicom", "mask", "segmentation", "detection", "bbox",
        "medical imaging", "3d volume", "图像", "视觉", "分割", "检测", "影像",
    ),
    "nlp_llm": (
        "natural language", "text", "nlp", "llm", "bert", "deberta", "token", "prompt", "rag",
        "文本", "大模型", "语言模型", "分词", "检索增强",
    ),
    "audio": (
        "audio", "speech", "sound", "spectrogram", "mel", "waveform", "birdclef", "ogg", "wav",
        "音频", "语音", "声音", "频谱", "声景",
    ),
    "rl_game": (
        "reinforcement learning", "self play", "self-play", "game agent", "policy", "actor critic",
        "simulation competition", "强化学习", "自博弈", "博弈", "策略网络", "仿真竞赛",
    ),
    "advanced": (
        "graph", "recommender", "recommendation", "combinatorial optimization", "simulation",
        "generative", "图学习", "推荐系统", "组合优化", "生成模型",
    ),
}

DOMAIN_QUERY_TERMS = {
    domain: " ".join(phrases) for domain, phrases in DOMAIN_PHRASES.items()
}

METRIC_FAMILIES = {
    "probability_ranking": ("auc", "auroc", "average precision", "prauc", "logloss", "log loss"),
    "threshold_classification": ("f1", "macro f1", "micro f1", "accuracy", "balanced accuracy", "mcc"),
    "regression": ("rmse", "rmsle", "rmspe", "mae", "mape", "mean squared", "pinball"),
    "ranking_retrieval": ("map@", "mapk", "ndcg", "mrr", "recall@", "precision@"),
    "overlap_segmentation": ("dice", "iou", "jaccard"),
    "detection": ("map", "mean average precision"),
    "ordinal": ("qwk", "quadratic weighted kappa"),
    "correlation": ("pearson", "spearman", "correlation"),
}

RISK_PATTERNS = {
    "group_leakage": (
        "group", "customer_id", "patient_id", "speaker_id", "recording_id", "user_id", "household",
        "same entity", "repeated entities", "组泄漏", "患者", "用户重复", "实体重复",
    ),
    "temporal_leakage": (
        "timestamp", "time series", "temporal", "future", "forecast", "event time", "时间", "未来信息", "时序泄漏",
    ),
    "duplicate_leakage": (
        "duplicate", "near duplicate", "same image", "dedup", "重复样本", "近重复", "哈希去重",
    ),
    "spatial_leakage": (
        "tile", "patch", "slide", "patient", "study_id", "scene", "spatial", "切片", "病人", "场景", "空间泄漏",
    ),
    "distribution_shift": (
        "shift", "adversarial validation", "train test mismatch", "public private", "domain shift",
        "分布漂移", "训练测试分布", "公榜私榜",
    ),
    "class_imbalance": (
        "imbalance", "rare class", "long tail", "positive rate", "少数类", "类别不平衡", "长尾",
    ),
    "label_noise": (
        "noisy label", "weak label", "annotation noise", "pseudo label", "标签噪声", "弱标签", "伪标签",
    ),
    "public_lb_overfit": (
        "leaderboard overfit", "public lb", "private lb", "shakeup", "榜单过拟合", "抖榜", "公榜", "私榜",
    ),
    "metric_mismatch": (
        "threshold", "postprocess", "calibration", "competition metric", "阈值", "后处理", "校准", "指标不一致",
    ),
}

CONSTRAINT_PATTERNS = {
    "gpu": ("gpu", "cuda", "t4", "p100", "a100"),
    "cpu_only": ("cpu only", "no gpu", "cpu-only", "仅 cpu"),
    "memory": ("memory", "oom", "ram", "vram", "内存", "显存"),
    "time": ("timeout", "runtime", "hours", "inference limit", "超时", "运行时间", "推理限制"),
    "offline": ("offline", "no internet", "internet disabled", "离线", "无网络"),
    "submission_quota": ("submission limit", "daily submissions", "提交次数", "提交限制"),
}

INTENT_TERMS = {
    "code": ("code", "implementation", "snippet", "reproduce", "notebook", "代码", "实现", "复现"),
    "strategy": ("strategy", "solution", "writeup", "ablation", "why worked", "方案", "复盘", "消融", "策略"),
    "debug": ("error", "fail", "mismatch", "timeout", "memory", "leakage", "debug", "报错", "修复", "泄漏"),
    "baseline": ("baseline", "starter", "simple", "first experiment", "基线", "入门"),
    "high_score": ("1st place", "winner", "gold", "top solution", "第一名", "金牌", "高分方案"),
}

FAMILY_GUIDE = {
    "tabular": ["CatBoost/LightGBM/XGBoost baselines", "leak-safe encodings and aggregations", "adversarial validation"],
    "feature": ["group-aware aggregation", "nested target encoding", "missingness and duplicate diagnostics"],
    "ensemble": ["OOF blending", "prediction-correlation analysis", "calibration and constrained stacking"],
    "system": ["deterministic folds", "artifact and submission assertions", "runtime-aware inference"],
    "deep_learning": ["embedding/MLP baselines", "tabular transformers", "multimodal fusion"],
    "timeseries": ["lag/rolling baselines", "blocked or forward validation", "horizon-aware postprocessing"],
    "cv_vision": ["strong pretrained backbones", "patient/scene-disjoint validation", "TTA and postprocessing ablations"],
    "nlp_llm": ["transformer fine-tuning", "retrieval/reranking", "chunking and label-noise analysis"],
    "audio": ["mel-spectrogram models", "recording-disjoint folds", "overlap-window inference and pooling"],
    "rl_game": ["deterministic simulator harness", "self-play/opponent pools", "replay-driven policy diagnostics"],
    "advanced": ["graph/recommender baselines", "constraint-aware search", "simulation and probabilistic modeling"],
}

GENERIC_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "using", "use", "used", "data",
    "model", "models", "train", "test", "kaggle", "competition", "solution", "analysis", "code", "notebook",
    "一个", "这个", "使用", "可以", "比赛", "模型", "数据", "方案", "分析", "代码", "进行", "通过",
}

_BASE_DOMAIN_PHRASES = {key: tuple(values) for key, values in DOMAIN_PHRASES.items()}
_BASE_RISK_PATTERNS = {key: tuple(values) for key, values in RISK_PATTERNS.items()}
POLICY: dict = {}
MECHANISM_PHRASES: dict[str, tuple[str, ...]] = {}


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def configure_policy(path: Path | None = None) -> dict:
    global DOMAIN_PHRASES, DOMAIN_QUERY_TERMS, RISK_PATTERNS, MECHANISM_PHRASES, POLICY
    default_payload = {}
    if DEFAULT_POLICY_PATH.exists():
        default_payload = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    configured_path = path or (Path(os.environ["KAGGLE_GM_POLICY"]) if os.environ.get("KAGGLE_GM_POLICY") else None)
    payload = default_payload
    if configured_path and configured_path.resolve() != DEFAULT_POLICY_PATH.resolve():
        custom = json.loads(configured_path.read_text(encoding="utf-8"))
        payload = _deep_merge(default_payload, custom)

    DOMAIN_PHRASES = {key: tuple(values) for key, values in _BASE_DOMAIN_PHRASES.items()}
    for domain, additions in (payload.get("domain_extensions") or {}).items():
        current = list(DOMAIN_PHRASES.get(domain, ()))
        DOMAIN_PHRASES[domain] = tuple(dict.fromkeys(current + [str(value) for value in additions]))
    RISK_PATTERNS = {key: tuple(values) for key, values in _BASE_RISK_PATTERNS.items()}
    for risk, additions in (payload.get("risk_extensions") or {}).items():
        current = list(RISK_PATTERNS.get(risk, ()))
        RISK_PATTERNS[risk] = tuple(dict.fromkeys(current + [str(value) for value in additions]))
    DOMAIN_QUERY_TERMS = {domain: " ".join(phrases) for domain, phrases in DOMAIN_PHRASES.items()}
    MECHANISM_PHRASES = {
        str(name): tuple(str(value) for value in values)
        for name, values in (payload.get("mechanism_phrases") or {}).items()
    }
    POLICY = payload
    phrase_token_set.cache_clear()
    return POLICY


def policy_value(section: str, key: str, default):
    return (POLICY.get(section) or {}).get(key, default)


@dataclass
class CompetitionProfile:
    slug: str = ""
    title: str = ""
    description: str = ""
    metric: str = ""
    data: str = ""
    constraints: str = ""
    stage: str = "intake"
    domains: list[str] | None = None
    mechanisms: list[str] | None = None
    metric_family: str = "unknown"
    validation_risks: list[str] | None = None
    runtime_constraints: list[str] | None = None
    unknowns: list[str] | None = None

    def text(self) -> str:
        return normalize_text(" ".join((self.slug, self.title, self.description, self.metric, self.data, self.constraints)))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class QueryLens:
    name: str
    text: str
    weight: float
    domains: tuple[str, ...]


def normalize_text(value: str) -> str:
    value = (value or "").lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = value.replace("_", " ").replace("-", " ")
    return re.sub(r"\s+", " ", value).strip()


def _ascii_phrase_present(text: str, phrase: str) -> bool:
    escaped = re.escape(phrase).replace(r"\ ", r"\s+")
    return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text))


def phrase_present_normalized(text: str, phrase: str) -> bool:
    phrase = normalize_text(phrase)
    if not phrase:
        return False
    if re.search(r"[\u4e00-\u9fff]", phrase):
        return phrase in text
    return _ascii_phrase_present(text, phrase)


def phrase_present(text: str, phrase: str) -> bool:
    return phrase_present_normalized(normalize_text(text), phrase)


def tokenize(text: str) -> list[str]:
    text = normalize_text(text)
    output: list[str] = []
    output.extend(re.findall(r"[a-z0-9][a-z0-9+#.]{1,}", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        if 2 <= len(chunk) <= 12:
            output.append(chunk)
        for width in (2, 3):
            if len(chunk) >= width:
                output.extend(chunk[i : i + width] for i in range(len(chunk) - width + 1))
    return [token for token in output if token not in GENERIC_STOPWORDS and len(token) > 1]


@lru_cache(maxsize=1024)
def phrase_token_set(phrase: str) -> frozenset[str]:
    return frozenset(tokenize(phrase))


def token_set_matches(token_set: set[str], phrase: str) -> bool:
    phrase_tokens = phrase_token_set(phrase)
    return bool(phrase_tokens) and phrase_tokens.issubset(token_set)


configure_policy()


def normalize_domain(domain: str | None) -> str | None:
    if not domain:
        return None
    key = normalize_text(domain).replace(" ", "_")
    return DOMAIN_ALIASES.get(key, key)


def infer_domains(text: str, explicit_domain: str | None = None, top_k: int = 5) -> list[str]:
    explicit = normalize_domain(explicit_domain)
    if explicit:
        return [explicit]
    normalized = normalize_text(text)
    scores: Counter[str] = Counter()
    for domain, phrases in DOMAIN_PHRASES.items():
        for phrase in phrases:
            if phrase_present_normalized(normalized, phrase):
                scores[domain] += 4 if " " in phrase or len(phrase) > 8 else 2
    token_set = set(tokenize(normalized))
    for alias, domain in DOMAIN_ALIASES.items():
        if alias in token_set:
            scores[domain] += 3
    if not scores:
        return []
    ordered = [name for name, _ in scores.most_common()]
    primary = [name for name in ordered if name in PRIMARY_DOMAINS]
    support = [name for name in ordered if name in SUPPORT_DOMAINS]
    return (primary + support)[:top_k]


def infer_mechanisms(text: str, top_k: int = 6) -> list[str]:
    normalized = normalize_text(text)
    scores: Counter[str] = Counter()
    for mechanism, phrases in MECHANISM_PHRASES.items():
        for phrase in phrases:
            if phrase_present_normalized(normalized, phrase):
                scores[mechanism] += 3 if " " in phrase or len(phrase) > 8 else 1
    return [name for name, _ in scores.most_common(top_k)]


def infer_intent(text: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    scores: Counter[str] = Counter()
    for intent, phrases in INTENT_TERMS.items():
        for phrase in phrases:
            if phrase_present(text, phrase):
                scores[intent] += 1
    return scores.most_common(1)[0][0] if scores else None


def infer_metric_family(metric: str) -> str:
    normalized = normalize_text(metric)
    for family, phrases in METRIC_FAMILIES.items():
        for phrase in phrases:
            if phrase_present(normalized, phrase):
                if phrase == "map" and "@" in normalized:
                    continue
                return family
    return "custom" if normalized else "unknown"


def detect_named_signals(text: str, patterns: dict[str, Sequence[str]]) -> list[str]:
    normalized = normalize_text(text)
    return [name for name, phrases in patterns.items() if any(phrase_present_normalized(normalized, phrase) for phrase in phrases)]


def detect_signals(text: str) -> dict[str, list[str]]:
    normalized = normalize_text(text)
    metrics = []
    for phrases in METRIC_FAMILIES.values():
        metrics.extend(phrase for phrase in phrases if phrase_present(normalized, phrase))
    return {
        "metrics": list(dict.fromkeys(metrics)),
        "risks": detect_named_signals(normalized, RISK_PATTERNS),
        "data": infer_domains(normalized, None, top_k=5),
    }


def family_hypotheses(domains: Sequence[str], signals: dict[str, list[str]]) -> list[dict]:
    hypotheses = []
    for domain in domains:
        families = FAMILY_GUIDE.get(domain)
        if families:
            hypotheses.append(
                {
                    "domain": domain,
                    "candidate_families": families,
                    "profile_signals": list(dict.fromkeys(signals.get("data", []) + signals.get("risks", [])))[:6],
                }
            )
    if not hypotheses:
        hypotheses.append(
            {
                "domain": "unclassified",
                "candidate_families": ["inspect data, reproduce the metric, establish validation, then retrieve again"],
                "profile_signals": ["insufficient task evidence"],
            }
        )
    return hypotheses


def build_profile(
    *,
    slug: str = "",
    title: str = "",
    description: str = "",
    metric: str = "",
    data: str = "",
    constraints: str = "",
    stage: str = "intake",
    explicit_domain: str | None = None,
) -> CompetitionProfile:
    combined = " ".join((slug, title, description, metric, data, constraints))
    domains = infer_domains(combined, explicit_domain, top_k=5)
    mechanisms = infer_mechanisms(combined)
    risks = detect_named_signals(combined, RISK_PATTERNS)
    risk_mechanism_map = POLICY.get("risk_mechanism_map") or {}
    for risk in risks:
        mapped = risk_mechanism_map.get(risk, [])
        if isinstance(mapped, str):
            mapped = [mapped]
        mechanisms.extend(str(value) for value in mapped if str(value))
    mechanisms = list(dict.fromkeys(mechanisms))
    runtime = detect_named_signals(constraints + " " + description, CONSTRAINT_PATTERNS)
    unknowns: list[str] = []
    if not metric:
        unknowns.append("official metric and local implementation")
    if not data:
        unknowns.append("file inventory, train/test schema, target and ID columns")
    if not any(domain in PRIMARY_DOMAINS for domain in domains):
        unknowns.append("primary data modality and prediction unit")
    if not risks:
        unknowns.append("validation grouping, chronology, duplicate and shift risks")
    return CompetitionProfile(
        slug=slug,
        title=title,
        description=description,
        metric=metric,
        data=data,
        constraints=constraints,
        stage=stage,
        domains=domains,
        mechanisms=mechanisms,
        metric_family=infer_metric_family(metric),
        validation_risks=risks,
        runtime_constraints=runtime,
        unknowns=unknowns,
    )


def default_catalog_paths() -> list[Path]:
    paths: list[Path] = []
    configured = os.environ.get(CATALOGS_ENV, "").strip()
    if configured:
        paths.extend(Path(value).expanduser() for value in configured.split(os.pathsep) if value.strip())
    paths.extend(path for path in (CURATED_CATALOG, FULL_CATALOG, LEARNED_CATALOG) if path.exists())
    return list(dict.fromkeys(path.resolve() for path in paths))


def _entry_key(entry: dict) -> str:
    parts = [
        normalize_text(entry.get("competition_slug") or ""),
        normalize_text(entry.get("source") or ""),
        normalize_text(entry.get("title") or ""),
        normalize_text(entry.get("source_type") or ""),
    ]
    if any(parts[:3]):
        return "|".join(parts)
    return normalize_text(entry.get("anchor") or entry.get("id") or "")


def load_entries(paths: Sequence[Path] | None = None) -> list[dict]:
    selected = list(paths or default_catalog_paths())
    if not selected:
        raise FileNotFoundError("No catalog found. Run build_book_catalog.py first.")
    merged: dict[str, dict] = {}
    for path in selected:
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem.lower()
        tier = "learned" if "learned" in stem else "archive" if "full" in stem else "curated"
        for raw in payload.get("entries", []):
            entry = dict(raw)
            entry["catalog_tier"] = tier
            key = _entry_key(entry)
            current = merged.get(key)
            if not current or (tier == "curated" and current.get("catalog_tier") != "curated"):
                merged[key] = entry
            elif current:
                for field in ("competition_slug", "competition_url", "source", "source_url", "source_type"):
                    if not current.get(field) and entry.get(field):
                        current[field] = entry[field]
    return list(merged.values())


def catalog_fingerprint(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(f"index-schema:{INDEX_SCHEMA_VERSION}".encode("ascii"))
    # Only domain vocabulary changes alter persisted index fields. Runtime ranking
    # weights can be tuned without paying for a full catalog rebuild.
    index_policy = {"domain_extensions": POLICY.get("domain_extensions") or {}}
    digest.update(json.dumps(index_policy, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _entry_fields(entry: dict) -> list[tuple[str, float]]:
    return [
        (entry.get("competition_slug") or "", 4.0),
        (entry.get("title") or "", 3.2),
        (entry.get("source") or "", 2.8),
        (entry.get("chapter") or "", 1.5),
        (" ".join(entry.get("algo_tags") or []), 2.8),
        (" ".join(entry.get("core_keywords") or []), 2.6),
        (" ".join(entry.get("method_keywords") or []), 2.4),
        (" ".join(entry.get("problem_signals") or []), 3.0),
        (" ".join(entry.get("transfer_scenarios") or []), 1.7),
        (" ".join(entry.get("pattern_families") or []), 2.2),
        (" ".join(entry.get("trick_highlights") or []), 2.1),
        (entry.get("summary") or "", 1.3),
    ]


def entry_tokens(entry: dict) -> Counter[str]:
    counts: Counter[str] = Counter()
    for value, weight in _entry_fields(entry):
        for token, count in Counter(tokenize(value)).items():
            counts[token] += count * weight
    return counts


def entry_domain_scores(entry: dict, token_set: set[str] | None = None) -> Counter[str]:
    if token_set is None:
        token_set = set(tokenize(" ".join(value for value, _ in _entry_fields(entry))))
    scores: Counter[str] = Counter()
    for domain, phrases in DOMAIN_PHRASES.items():
        for phrase in phrases:
            if token_set_matches(token_set, phrase):
                scores[domain] += 2 if " " in phrase else 1
    chapter_tokens = set(tokenize(entry.get("chapter") or ""))
    chapter_hints = {
        "system": ("实验工程", "训练稳定"),
        "feature": ("特征工程", "泄漏控制"),
        "ensemble": ("oof", "stacking", "元学习"),
        "tabular": ("表格树模型", "gbdt"),
        "deep_learning": ("表格深度学习",),
        "timeseries": ("时间序列", "时序验证"),
        "cv_vision": ("视觉", "3d 感知"),
        "nlp_llm": ("nlp", "llm"),
        "audio": ("音频", "语音"),
        "advanced": ("进阶专题",),
    }
    for domain, hints in chapter_hints.items():
        if any(token_set_matches(chapter_tokens, hint) for hint in hints):
            scores[domain] += 5
    return scores


class BM25Index:
    def __init__(self, entries: Sequence[dict]):
        self.entries = list(entries)
        self.documents = [entry_tokens(entry) for entry in self.entries]
        self.entry_token_sets = [set(document) for document in self.documents]
        self.domain_scores = {
            index: entry_domain_scores(entry, self.entry_token_sets[index])
            for index, entry in enumerate(self.entries)
        }
        self.lengths = [sum(doc.values()) for doc in self.documents]
        self.avg_length = sum(self.lengths) / max(len(self.lengths), 1)
        self.df: Counter[str] = Counter()
        self.postings: dict[str, list[int]] = defaultdict(list)
        for document in self.documents:
            self.df.update(document.keys())
        for index, document in enumerate(self.documents):
            for token in document:
                self.postings[token].append(index)

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def get_entry(self, index: int) -> dict:
        return self.entries[index]

    def get_facet_entry(self, index: int) -> dict:
        return self.entries[index]

    def get_token_set(self, index: int) -> set[str]:
        return self.entry_token_sets[index]

    def get_domain_scores(self, index: int) -> Counter[str]:
        return self.domain_scores[index]

    def score_counts(self, query_counts: Counter[str], index: int, *, k1: float = 1.3, b: float = 0.72) -> float:
        document = self.documents[index]
        doc_len = self.lengths[index]
        total = 0.0
        corpus_size = max(len(self.documents), 1)
        for token, qtf in query_counts.items():
            tf = document.get(token, 0.0)
            if not tf:
                continue
            df = self.df[token]
            idf = math.log(1.0 + (corpus_size - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1.0 - b + b * doc_len / max(self.avg_length, 1.0))
            total += idf * (tf * (k1 + 1.0) / denom) * (1.0 + math.log1p(qtf) * 0.15)
        return total

    def score(self, query: str, index: int, *, k1: float = 1.3, b: float = 0.72) -> float:
        return self.score_counts(Counter(tokenize(query)), index, k1=k1, b=b)

    def rank_counts(self, query_counts: Counter[str], limit: int) -> list[tuple[float, int]]:
        candidate_indices: set[int] = set()
        for token in query_counts:
            candidate_indices.update(self.postings.get(token, ()))
        ranked = [
            (self.score_counts(query_counts, index), index)
            for index in candidate_indices
        ]
        ranked = [item for item in ranked if item[0] > 0]
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked[:limit]


FTS_COLUMNS = (
    "competition_slug",
    "title",
    "source",
    "chapter",
    "algo_tags",
    "core_keywords",
    "method_keywords",
    "problem_signals",
    "transfer_scenarios",
    "pattern_families",
    "trick_highlights",
    "summary",
)
FTS_WEIGHTS = (4.0, 3.2, 2.8, 1.5, 2.8, 2.6, 2.4, 3.0, 1.7, 2.2, 2.1, 1.3)


def _fts_token(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def _fts_tokens(value: str) -> list[str]:
    return list(
        dict.fromkeys(normalized for token in tokenize(value) if len(normalized := _fts_token(token)) > 1)
    )


class SQLiteIndex:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.connection = sqlite3.connect(str(self.path))
        self.connection.execute("PRAGMA query_only=ON")
        self.connection.execute("PRAGMA cache_size=-8192")
        self._entry_cache: dict[int, dict] = {}
        self._facet_cache: dict[int, dict] = {}
        self._token_cache: dict[int, set[str]] = {}
        self._domain_cache: dict[int, Counter[str]] = {}
        row = self.connection.execute("SELECT value FROM metadata WHERE key='entry_count'").fetchone()
        self._entry_count = int(row[0]) if row else 0

    @property
    def entry_count(self) -> int:
        return self._entry_count

    def close(self) -> None:
        if getattr(self, "connection", None) is not None:
            self.connection.close()
            self.connection = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _remember(cache: dict, index: int, value, limit: int = 192):
        cache[index] = value
        if len(cache) > limit:
            cache.pop(next(iter(cache)))
        return value

    def _row(self, index: int) -> tuple[bytes, bytes, bytes, str]:
        row = self.connection.execute(
            "SELECT payload, facet_payload, token_set, domain_scores FROM entries WHERE rowid=?",
            (index,),
        ).fetchone()
        if row is None:
            raise IndexError(index)
        return row

    def get_entry(self, index: int) -> dict:
        if index not in self._entry_cache:
            payload, _, _, _ = self._row(index)
            value = json.loads(zlib.decompress(payload).decode("utf-8"))
            self._remember(self._entry_cache, index, value, 96)
        return self._entry_cache[index]

    def get_facet_entry(self, index: int) -> dict:
        if index not in self._facet_cache:
            _, payload, _, _ = self._row(index)
            value = json.loads(zlib.decompress(payload).decode("utf-8"))
            self._remember(self._facet_cache, index, value)
        return self._facet_cache[index]

    def get_token_set(self, index: int) -> set[str]:
        if index not in self._token_cache:
            _, _, payload, _ = self._row(index)
            value = set(zlib.decompress(payload).decode("utf-8").split())
            self._remember(self._token_cache, index, value)
        return self._token_cache[index]

    def get_domain_scores(self, index: int) -> Counter[str]:
        if index not in self._domain_cache:
            _, _, _, payload = self._row(index)
            self._remember(self._domain_cache, index, Counter(json.loads(payload)))
        return self._domain_cache[index]

    def rank_counts(self, query_counts: Counter[str], limit: int) -> list[tuple[float, int]]:
        terms = list(dict.fromkeys(_fts_token(token) for token in query_counts if len(_fts_token(token)) > 1))
        if not terms:
            return []
        query = " OR ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
        weights = ", ".join(str(value) for value in FTS_WEIGHTS)
        rows = self.connection.execute(
            f"SELECT rowid, -bm25(entries_fts, {weights}) AS score "
            "FROM entries_fts WHERE entries_fts MATCH ? "
            f"ORDER BY bm25(entries_fts, {weights}) LIMIT ?",
            (query, limit),
        ).fetchall()
        return [(float(score), int(rowid)) for rowid, score in rows if score > 0]


def _sqlite_index_valid(path: Path, fingerprint: str) -> bool:
    if not path.exists():
        return False
    connection = None
    try:
        connection = sqlite3.connect(str(path))
        values = dict(connection.execute("SELECT key, value FROM metadata"))
        return (
            values.get("fingerprint") == fingerprint
            and values.get("schema_version") == str(INDEX_SCHEMA_VERSION)
            and int(values.get("entry_count") or 0) > 0
        )
    except (OSError, sqlite3.Error, ValueError):
        return False
    finally:
        if connection is not None:
            connection.close()


def _build_sqlite_index(path: Path, entries: Sequence[dict], fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(str(temporary))
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            PRAGMA temp_store=MEMORY;
            PRAGMA locking_mode=EXCLUSIVE;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE entries (
                rowid INTEGER PRIMARY KEY,
                payload BLOB NOT NULL,
                facet_payload BLOB NOT NULL,
                token_set BLOB NOT NULL,
                domain_scores TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE entries_fts USING fts5(
                competition_slug, title, source, chapter, algo_tags, core_keywords,
                method_keywords, problem_signals, transfer_scenarios, pattern_families,
                trick_highlights, summary, content='', tokenize='unicode61'
            );
            """
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            (
                ("fingerprint", fingerprint),
                ("schema_version", str(INDEX_SCHEMA_VERSION)),
                ("entry_count", str(len(entries))),
            ),
        )
        entry_rows = []
        fts_rows = []
        fts_placeholders = ",".join("?" for _ in range(len(FTS_COLUMNS) + 1))
        fts_statement = f"INSERT INTO entries_fts(rowid, {', '.join(FTS_COLUMNS)}) VALUES ({fts_placeholders})"
        for rowid, entry in enumerate(entries, start=1):
            fields = [" ".join(_fts_tokens(value)) for value, _ in _entry_fields(entry)]
            token_set = set(" ".join(fields).split())
            domains = entry_domain_scores(entry, token_set)
            payload = zlib.compress(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 1)
            facet_entry = {
                key: entry.get(key)
                for key in (
                    "id", "anchor", "title", "competition_slug", "source", "source_type",
                    "catalog_tier", "quality_score", "code_evidence_count", "tricks_count",
                    "algo_tags", "core_keywords",
                )
            }
            facet_entry["summary"] = (entry.get("summary") or "")[:600]
            facet_payload = zlib.compress(
                json.dumps(facet_entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                1,
            )
            token_payload = zlib.compress(" ".join(sorted(token_set)).encode("utf-8"), 1)
            entry_rows.append((rowid, payload, facet_payload, token_payload, json.dumps(domains, ensure_ascii=False)))
            fts_rows.append((rowid, *fields))
            if len(entry_rows) >= 64:
                connection.executemany(
                    "INSERT INTO entries(rowid, payload, facet_payload, token_set, domain_scores) VALUES (?, ?, ?, ?, ?)",
                    entry_rows,
                )
                connection.executemany(fts_statement, fts_rows)
                entry_rows.clear()
                fts_rows.clear()
        if entry_rows:
            connection.executemany(
                "INSERT INTO entries(rowid, payload, facet_payload, token_set, domain_scores) VALUES (?, ?, ?, ?, ?)",
                entry_rows,
            )
            connection.executemany(fts_statement, fts_rows)
        connection.commit()
    except BaseException:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
        connection.close()
    try:
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _prune_legacy_index_caches(cache_dir: Path, keep: Path) -> None:
    cache_dir = cache_dir.resolve()
    if not cache_dir.exists():
        return
    for pattern in (
        "retrieval_index-*.pkl.gz",
        "retrieval_index-*.pkl.gz.tmp",
        "retrieval_index*.sqlite3.tmp",
        "retrieval_index*.sqlite3.*.tmp",
        "retrieval_index.sqlite3",
        "retrieval_index-*.sqlite3",
    ):
        for candidate in cache_dir.glob(pattern):
            if candidate.resolve() != keep.resolve():
                try:
                    candidate.unlink(missing_ok=True)
                except PermissionError:
                    pass


@contextmanager
def _index_build_lock(cache_path: Path, timeout_seconds: float = 180.0):
    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()}\ncreated={time.time()}\n".encode("ascii"))
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > timeout_seconds * 2:
                    lock_path.unlink()
                    continue
            except (FileNotFoundError, PermissionError):
                pass
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError(f"Timed out waiting for retrieval index lock: {lock_path}")
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink(missing_ok=True)
        except PermissionError:
            pass


def load_or_build_index(
    entries_or_paths: Sequence[dict] | Sequence[Path],
    catalog_paths: Sequence[Path] | None = None,
    *,
    cache_path: Path | None = None,
    refresh: bool = False,
) -> BM25Index | SQLiteIndex:
    if catalog_paths is None:
        paths = [Path(path) for path in entries_or_paths]
        entries: Sequence[dict] | None = None
    else:
        paths = list(catalog_paths)
        entries = entries_or_paths  # Backward-compatible caller shape.
    fingerprint = catalog_fingerprint(paths)
    if cache_path is None:
        cache_root = Path(os.environ.get(CACHE_DIR_ENV) or SKILL_DIR / ".cache").expanduser()
        cache_path = cache_root / f"retrieval_index-{fingerprint[:16]}.sqlite3"
    cache_path = cache_path.resolve()
    if not refresh and _sqlite_index_valid(cache_path, fingerprint):
        _prune_legacy_index_caches(cache_path.parent, cache_path)
        return SQLiteIndex(cache_path)
    try:
        with _index_build_lock(cache_path):
            if not refresh and _sqlite_index_valid(cache_path, fingerprint):
                return SQLiteIndex(cache_path)
            if entries is None:
                entries = load_entries(paths)
            _build_sqlite_index(cache_path, entries, fingerprint)
    except (OSError, sqlite3.Error, TimeoutError) as error:
        # Read-only installations still retain a functional in-memory fallback.
        warnings.warn(
            f"Persistent retrieval index unavailable ({type(error).__name__}: {error}); "
            "falling back to a higher-memory in-process BM25 index.",
            RuntimeWarning,
            stacklevel=2,
        )
        if entries is None:
            entries = load_entries(paths)
        return BM25Index(entries)
    _prune_legacy_index_caches(cache_path.parent, cache_path)
    return SQLiteIndex(cache_path)


def load_query_inputs(values: Sequence[str] | None = None, files: Sequence[Path] | None = None) -> list[str]:
    queries = [str(value).strip() for value in values or () if str(value).strip()]
    for path in files or ():
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            payload = json.loads(raw)
            if isinstance(payload, dict):
                payload = payload.get("queries", [])
            if not isinstance(payload, list):
                raise ValueError(f"Query JSON must contain a list or a queries list: {path}")
            queries.extend(str(value).strip() for value in payload if str(value).strip())
        else:
            for line in raw.splitlines():
                query = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line).strip()
                if query and not query.startswith("#"):
                    queries.append(query)
    return list(dict.fromkeys(queries))


def build_query_lenses(
    profile: CompetitionProfile,
    free_query: str | Sequence[str] = "",
) -> list[QueryLens]:
    domains = tuple(profile.domains or ())
    primary = [domain for domain in domains if domain in PRIMARY_DOMAINS]
    if isinstance(free_query, str):
        custom_queries = [free_query.strip()] if free_query.strip() else []
    else:
        custom_queries = [str(value).strip() for value in free_query if str(value).strip()]
    max_custom_queries = int(policy_value("ranking", "max_custom_queries", 20))
    custom_queries = list(dict.fromkeys(custom_queries))[:max_custom_queries]
    common = " ".join((profile.title, profile.description, profile.metric, profile.data, " ".join(custom_queries))).strip()
    lenses: list[QueryLens] = []
    weights = POLICY.get("lens_weights") or {}
    for index, custom_query in enumerate(custom_queries, start=1):
        lenses.append(
            QueryLens(
                f"user_query_{index:02d}",
                custom_query,
                weights.get("user_query", 1.9),
                domains,
            )
        )
    if profile.slug:
        lenses.append(QueryLens("exact_competition", profile.slug, weights.get("exact_competition", 2.4), domains))
    lenses.append(QueryLens("task_shape", common, weights.get("task_shape", 1.5), domains))
    if primary:
        terms = " ".join(DOMAIN_QUERY_TERMS.get(domain, domain) for domain in primary[:2])
        lenses.append(QueryLens("modality_transfer", f"{common} {terms}", weights.get("modality_transfer", 1.25), tuple(primary[:2])))
    if profile.metric:
        lenses.append(QueryLens("metric_behavior", f"{profile.metric} {profile.metric_family} validation threshold calibration", weights.get("metric_behavior", 1.05), domains))
    if profile.validation_risks:
        risk_terms = " ".join(profile.validation_risks)
        lenses.append(QueryLens("validation_risk", f"{common} {risk_terms} split leakage cv lb shift", weights.get("validation_risk", 1.45), tuple(dict.fromkeys((*domains, "feature", "system")))))
    if profile.mechanisms or profile.validation_risks:
        mechanism_terms = " ".join((profile.mechanisms or []) + (profile.validation_risks or []))
        lenses.append(
            QueryLens(
                "mechanism_transfer",
                f"{mechanism_terms} causal mechanism ablation failure conditions transferable pattern",
                weights.get("mechanism_transfer", 1.15),
                tuple(sorted(SUPPORT_DOMAINS)),
            )
        )
    if profile.stage in {"intake", "eda"}:
        lenses.append(QueryLens("data_and_validation_gate", f"{common} prediction unit data usage metric fold leakage duplicate group time", weights.get("data_and_validation_gate", 1.65), tuple(dict.fromkeys((*domains, "feature", "system")))))
    elif profile.stage == "baseline":
        lenses.append(QueryLens("reliable_baseline", f"{common} simple baseline oof reproducible submission assertions", weights.get("reliable_baseline", 1.25), tuple(dict.fromkeys((*domains, "system")))))
    elif profile.stage == "finalize":
        lenses.append(QueryLens("final_inference", f"{common} full train inference packaging runtime memory submission", weights.get("final_inference", 1.35), tuple(dict.fromkeys((*domains, "system")))))
    lenses.append(QueryLens("implementation", f"{common} code implementation training inference reproducible notebook", weights.get("implementation", 0.85), domains))
    ensemble_weight = weights.get("ensemble_stage", 1.25) if profile.stage == "ensemble" else weights.get("ensemble_intake", 0.25) if profile.stage in {"intake", "eda", "baseline"} else weights.get("ensemble_improve", 0.65)
    lenses.append(QueryLens("ensemble_late_game", f"{common} oof blend stacking calibration pseudo label diversity", ensemble_weight, tuple(dict.fromkeys((*domains, "ensemble")))))
    return [lens for lens in lenses if tokenize(lens.text)]


def _source_quality(entry: dict, intent: str | None) -> float:
    quality = float(entry.get("quality_score") or 0)
    code = float(entry.get("code_evidence_count") or 0)
    tricks = float(entry.get("tricks_count") or 0)
    source_type = normalize_text(entry.get("source_type") or "")
    bonus = math.log1p(max(quality, 0)) * 0.55 + min(code, 20) * 0.08 + min(tricks, 20) * 0.06
    if entry.get("catalog_tier") == "curated":
        bonus += float(policy_value("ranking", "curated_bonus", 1.8))
    elif entry.get("catalog_tier") == "learned":
        bonus += float(policy_value("ranking", "learned_bonus", 1.4))
    if intent == "code":
        bonus += min(code, 20) * 0.22 + (1.0 if "analysis" in source_type else 0.0)
    elif intent == "strategy":
        bonus += min(tricks, 20) * 0.14 + (1.2 if "writeup" in source_type else 0.0)
    elif intent == "high_score":
        high_score_text = " ".join((entry.get("title") or "", entry.get("summary") or ""))
        bonus += sum(1.2 for phrase in ("1st", "first place", "winner", "gold", "第一", "金牌") if phrase_present(high_score_text, phrase))
    return bonus


def _facet_score(
    entry: dict,
    profile: CompetitionProfile,
    intent: str | None,
    *,
    domain_scores: Counter[str] | None = None,
    entry_text: str | None = None,
    entry_token_set: set[str] | None = None,
) -> tuple[float, list[str], str]:
    reasons: list[str] = []
    score = _source_quality(entry, intent)
    exact = bool(profile.slug and normalize_text(profile.slug) == normalize_text(entry.get("competition_slug") or ""))
    if exact:
        score += 70.0
        reasons.append("exact-slug")

    requested = set(profile.domains or [])
    requested_primary = requested & PRIMARY_DOMAINS
    domain_scores = domain_scores if domain_scores is not None else entry_domain_scores(entry)
    entry_domains = {domain for domain, value in domain_scores.items() if value >= 2}
    primary_overlap = requested_primary & entry_domains
    support_overlap = requested & entry_domains & SUPPORT_DOMAINS
    if primary_overlap:
        score += 8.0 + sum(min(domain_scores[d], 8) * 0.55 for d in primary_overlap)
        reasons.append("primary:" + ",".join(sorted(primary_overlap)))
    if support_overlap:
        score += 2.5 + len(support_overlap)
        reasons.append("support:" + ",".join(sorted(support_overlap)))

    if entry_token_set is None:
        entry_text = entry_text if entry_text is not None else normalize_text(" ".join(value for value, _ in _entry_fields(entry)))
        entry_token_set = set(tokenize(entry_text))
    risk_hits = [
        risk
        for risk in profile.validation_risks or []
        if any(token_set_matches(entry_token_set, phrase) for phrase in RISK_PATTERNS.get(risk, ()))
    ]
    if risk_hits:
        score += float(policy_value("ranking", "risk_bonus", 3.2)) * len(risk_hits)
        reasons.append("risk:" + ",".join(risk_hits))

    mechanism_hits = [
        mechanism
        for mechanism in profile.mechanisms or []
        if any(token_set_matches(entry_token_set, phrase) for phrase in MECHANISM_PHRASES.get(mechanism, ()))
    ]
    if mechanism_hits:
        score += float(policy_value("ranking", "mechanism_bonus", 2.6)) * len(mechanism_hits)
        reasons.append("mechanism:" + ",".join(mechanism_hits))

    conflicting = (entry_domains & PRIMARY_DOMAINS) - requested_primary
    if requested_primary and not primary_overlap and conflicting:
        if risk_hits or mechanism_hits:
            score -= float(policy_value("ranking", "cross_modal_shared_mechanism_penalty", 0.75))
            bridge = list(dict.fromkeys(mechanism_hits + risk_hits))
            reasons.append("cross-domain-mechanism:" + ",".join(bridge[:4]))
        else:
            score -= float(policy_value("ranking", "cross_modal_penalty", 7.0))
            reasons.append("cross-modal:" + ",".join(sorted(conflicting)[:3]))

    metric_match = False
    if profile.metric:
        metric_match = any(token in entry_token_set for token in tokenize(profile.metric))
        if metric_match:
            score += 3.5
            reasons.append("metric")

    if exact:
        match_level = "exact"
    elif primary_overlap and (risk_hits or mechanism_hits or metric_match):
        match_level = "direct"
    elif primary_overlap:
        match_level = "near"
    elif risk_hits or mechanism_hits or support_overlap:
        match_level = "adjacent"
    else:
        match_level = "analogy"
    return score, reasons, match_level


def _candidate_identity(entry: dict) -> str:
    return _entry_key(entry) or normalize_text(entry.get("anchor") or entry.get("id") or "")


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _diversify(candidates: list[dict], limit: int) -> list[dict]:
    if not candidates:
        return []
    max_score = max(item["score"] for item in candidates) or 1.0
    selected: list[dict] = []
    slug_counts: Counter[str] = Counter()
    remaining = candidates[:]
    while remaining and len(selected) < limit:
        best_index = 0
        best_value = -float("inf")
        for index, item in enumerate(remaining):
            item_tokens = item["diversity_tokens"]
            similarity = max((_jaccard(item_tokens, other["diversity_tokens"]) for other in selected), default=0.0)
            slug = item.get("competition_slug") or item.get("title") or "unknown"
            slug_penalty = 0.13 * slug_counts[slug]
            level_bonus = {"exact": 0.18, "direct": 0.12, "near": 0.06, "adjacent": 0.0, "analogy": -0.04}[item["match_level"]]
            value = 0.78 * (item["score"] / max_score) + 0.22 * (1.0 - similarity) + level_bonus - slug_penalty
            if value > best_value:
                best_value = value
                best_index = index
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        slug_counts[chosen.get("competition_slug") or chosen.get("title") or "unknown"] += 1
    return selected


def retrieve_evidence(
    entries: Sequence[dict] | None,
    profile: CompetitionProfile,
    *,
    query: str | Sequence[str] = "",
    intent: str | None = None,
    recall: int = 80,
    limit: int = 12,
    index: BM25Index | SQLiteIndex | None = None,
) -> dict:
    if index is None:
        if entries is None:
            raise ValueError("Either entries or a retrieval index is required.")
        index = BM25Index(entries)
    if entries is not None and index.entry_count != len(entries):
        raise ValueError("The supplied BM25 index does not match the entry collection.")
    lenses = build_query_lenses(profile, query)
    intent_query = query if isinstance(query, str) else " ".join(str(value) for value in query)
    resolved_intent = infer_intent(" ".join((intent_query, profile.description)), intent)
    aggregate: dict[str, dict] = {}
    rrf_k = float(policy_value("ranking", "rrf_k", 45.0))
    candidate_multiplier = int(policy_value("ranking", "candidate_multiplier", 2))
    minimum_candidate_pool = int(policy_value("ranking", "minimum_candidate_pool", 96))
    facets: dict[int, tuple[float, list[str], str]] = {}

    def add_lens_ranking(lens: QueryLens, ranked: list[tuple[float, int, list[str], str]]) -> None:
        ranked.sort(key=lambda item: item[0], reverse=True)
        for rank, (raw_score, entry_index, reasons, match_level) in enumerate(ranked[:recall], start=1):
            entry = index.get_facet_entry(entry_index)
            identity = _candidate_identity(entry)
            current = aggregate.setdefault(
                identity,
                {
                    "entry_index": entry_index,
                    "facet_entry": entry,
                    "rrf": 0.0,
                    "raw_max": 0.0,
                    "matched_lenses": [],
                    "reasons": [],
                    "match_level": match_level,
                },
            )
            if raw_score > current["raw_max"]:
                current["entry_index"] = entry_index
                current["facet_entry"] = entry
            current["rrf"] += lens.weight / (rrf_k + rank)
            current["raw_max"] = max(current["raw_max"], raw_score)
            current["matched_lenses"].append(lens.name)
            current["reasons"].extend(reasons)
            level_order = {"analogy": 0, "adjacent": 1, "near": 2, "direct": 3, "exact": 4}
            if level_order[match_level] > level_order[current["match_level"]]:
                current["match_level"] = match_level

    pool_limit = max(recall * candidate_multiplier, minimum_candidate_pool)
    if isinstance(index, SQLiteIndex):
        # SQLite FTS performs one weighted field-aware recall. Independent lenses then
        # rerank that pool, preserving RRF semantics without repeating disk work.
        lens_counts = [(lens, Counter(tokenize(lens.text))) for lens in lenses]
        combined_counts: Counter[str] = Counter()
        for lens, counts in lens_counts:
            for token, count in counts.items():
                combined_counts[token] += max(1.0, count * lens.weight)
        lexical_pool = index.rank_counts(combined_counts, pool_limit)
        pool: list[tuple[float, int, set[str]]] = []
        for lexical, entry_index in lexical_pool:
            entry = index.get_facet_entry(entry_index)
            token_set = index.get_token_set(entry_index)
            if entry_index not in facets:
                facets[entry_index] = _facet_score(
                    entry,
                    profile,
                    resolved_intent,
                    domain_scores=index.get_domain_scores(entry_index),
                    entry_token_set=token_set,
                )
            pool.append((lexical, entry_index, token_set))
        for lens, query_counts in lens_counts:
            denominator = sum(1.0 + math.log1p(count) for count in query_counts.values()) or 1.0
            ranked: list[tuple[float, int, list[str], str]] = []
            for combined_lexical, entry_index, token_set in pool:
                overlap = sum(
                    1.0 + math.log1p(count)
                    for token, count in query_counts.items()
                    if token in token_set
                )
                if overlap <= 0:
                    continue
                lexical = combined_lexical * 0.25 + overlap + 4.0 * overlap / denominator
                facet, reasons, match_level = facets[entry_index]
                if lexical + facet > 0:
                    ranked.append((lexical + facet, entry_index, reasons, match_level))
            add_lens_ranking(lens, ranked)
    else:
        for lens in lenses:
            ranked = []
            query_counts = Counter(tokenize(lens.text))
            for lexical, entry_index in index.rank_counts(query_counts, pool_limit):
                entry = index.get_facet_entry(entry_index)
                if entry_index not in facets:
                    facets[entry_index] = _facet_score(
                        entry,
                        profile,
                        resolved_intent,
                        domain_scores=index.get_domain_scores(entry_index),
                        entry_token_set=index.get_token_set(entry_index),
                    )
                facet, reasons, match_level = facets[entry_index]
                if lexical + facet > 0:
                    ranked.append((lexical + facet, entry_index, reasons, match_level))
            add_lens_ranking(lens, ranked)

    scored_references: list[dict] = []
    for current in aggregate.values():
        level_multiplier = {"exact": 1.25, "direct": 1.12, "near": 1.04, "adjacent": 0.95, "analogy": 0.82}[current["match_level"]]
        score = (current["rrf"] * 1000.0 + math.log1p(current["raw_max"]) * 6.0) * level_multiplier
        scored_references.append({
                "entry_index": current["entry_index"],
                "score": round(score, 3),
                "match_level": current["match_level"],
                "matched_lenses": sorted(set(current["matched_lenses"])),
                "reasons": list(dict.fromkeys(current["reasons"]))[:8],
            })
    scored_references.sort(key=lambda item: item["score"], reverse=True)

    # Facet scoring touches hundreds of candidates, but full evidence payloads can be large.
    # Materialize only the pool needed for diversification and mechanism bridges.
    materialize_limit = max(recall, limit * 6, 40)
    candidates: list[dict] = []
    for reference in scored_references[:materialize_limit]:
        entry = index.get_entry(reference["entry_index"])
        evidence_text = " ".join(
            [
                entry.get("title") or "",
                entry.get("summary") or "",
                " ".join(entry.get("trick_highlights") or []),
            ]
        )
        candidates.append(
            {
                "score": reference["score"],
                "match_level": reference["match_level"],
                "matched_lenses": reference["matched_lenses"],
                "reasons": reference["reasons"],
                "title": entry.get("title"),
                "chapter": entry.get("chapter"),
                "competition_slug": entry.get("competition_slug"),
                "competition_url": entry.get("competition_url"),
                "source": entry.get("source"),
                "source_url": entry.get("source_url"),
                "source_type": entry.get("source_type"),
                "catalog_tier": entry.get("catalog_tier"),
                "provenance_status": entry.get("provenance_status") or "unknown",
                "trust_level": entry.get("trust_level") or "untrusted_external",
                "source_license": entry.get("source_license") or "unknown",
                "source_content_sha256": entry.get("source_content_sha256") or "",
                "code_evidence_status": entry.get("code_evidence_status") or "unknown",
                "evidence_risk_flags": evidence_risk_flags(evidence_text),
                "anchor": entry.get("anchor"),
                "algo_tags": entry.get("algo_tags") or [],
                "core_keywords": (entry.get("core_keywords") or [])[:14],
                "method_keywords": (entry.get("method_keywords") or [])[:14],
                "problem_signals": (entry.get("problem_signals") or [])[:12],
                "transfer_scenarios": (entry.get("transfer_scenarios") or [])[:8],
                "pattern_families": (entry.get("pattern_families") or [])[:8],
                "trick_highlights": (entry.get("trick_highlights") or [])[:10],
                "summary": (entry.get("summary") or "")[:1000],
                "tricks_count": entry.get("tricks_count"),
                "code_evidence_count": entry.get("code_evidence_count"),
                "quality_score": entry.get("quality_score"),
                "diversity_tokens": set(tokenize(" ".join((entry.get("title") or "", " ".join(entry.get("core_keywords") or []), " ".join(entry.get("algo_tags") or []))))),
            }
        )
    selected = _diversify(candidates[: max(recall, limit * 6)], limit)
    selected_ids = {
        (item.get("anchor"), item.get("competition_slug"), item.get("source"))
        for item in selected
    }
    bridge_limit = int(policy_value("ranking", "mechanism_bridge_limit", 3))
    mechanism_bridges = []
    for item in candidates:
        identity = (item.get("anchor"), item.get("competition_slug"), item.get("source"))
        if identity in selected_ids:
            continue
        if not any(reason.startswith("cross-domain-mechanism:") for reason in item.get("reasons") or []):
            continue
        bridge = dict(item)
        bridge.pop("diversity_tokens", None)
        mechanism_bridges.append(bridge)
        if len(mechanism_bridges) >= bridge_limit:
            break
    for item in selected:
        item.pop("diversity_tokens", None)

    coverage = evidence_coverage(selected, profile)
    return {
        "intent": resolved_intent,
        "lenses": [asdict(lens) for lens in lenses],
        "candidate_count": len(scored_references),
        "materialized_candidate_count": len(candidates),
        "coverage": coverage,
        "results": selected,
        "mechanism_bridges": mechanism_bridges,
    }


def evidence_coverage(results: Sequence[dict], profile: CompetitionProfile) -> dict:
    direct = sum(1 for item in results if item.get("match_level") in {"exact", "direct", "near"})
    code = sum(
        1
        for item in results
        if (item.get("code_evidence_count") or 0) > 0 and item.get("code_evidence_status") == "cited"
    )
    derived_code = sum(
        1
        for item in results
        if (item.get("code_evidence_count") or 0) > 0 and item.get("code_evidence_status") != "cited"
    )
    writeup = sum(1 for item in results if "writeup" in normalize_text(item.get("source_type") or ""))
    validation = sum(1 for item in results if any(reason.startswith("risk:") for reason in item.get("reasons") or []))
    source_links = sum(1 for item in results if safe_public_url(item.get("source_url") or ""))
    reviewed = sum(1 for item in results if item.get("provenance_status") == "reviewed")
    risky = sum(1 for item in results if item.get("evidence_risk_flags"))
    unique_competitions = len({item.get("competition_slug") or item.get("title") for item in results})
    has_primary = bool(set(profile.domains or []) & PRIMARY_DOMAINS)
    if (
        direct >= 4
        and code >= 2
        and source_links >= 4
        and unique_competitions >= 4
        and (validation >= 1 or not profile.validation_risks)
    ):
        confidence = "high"
    elif direct >= 2 and unique_competitions >= 2 and has_primary:
        confidence = "medium"
    else:
        confidence = "low"
    gaps: list[str] = []
    if code == 0:
        gaps.append("no hash-cited code evidence in selected hits")
    if source_links == 0:
        gaps.append("no public source link in selected hits")
    if writeup == 0:
        gaps.append("no write-up evidence in selected hits")
    if profile.validation_risks and validation == 0:
        gaps.append("validation risks are not covered by retrieved evidence")
    if direct < 2:
        gaps.append("too few direct or near-domain cases")
    return {
        "confidence": confidence,
        "direct_or_near": direct,
        "code_hits": code,
        "derived_code_claim_hits": derived_code,
        "writeup_hits": writeup,
        "validation_hits": validation,
        "source_link_hits": source_links,
        "reviewed_hits": reviewed,
        "risk_flagged_hits": risky,
        "unique_competitions": unique_competitions,
        "gaps": gaps,
    }


def validation_contract(profile: CompetitionProfile) -> list[dict]:
    risks = set(profile.validation_risks or [])
    checks: list[dict] = [
        {
            "gate": "metric_reproduction",
            "action": "Implement the official metric locally and verify it on a tiny hand-checked example.",
            "pass_condition": "The local metric matches the official definition and handles edge cases.",
        },
        {
            "gate": "submission_alignment",
            "action": "Validate ID order, row count, missing values, ranges, dtypes and sample-submission columns.",
            "pass_condition": "A baseline submission passes every structural assertion.",
        },
    ]
    if "group_leakage" in risks or "spatial_leakage" in risks:
        checks.append({
            "gate": "group_disjoint_cv",
            "action": "Build folds that keep entities/patients/recordings/scenes disjoint and compare against random CV.",
            "pass_condition": "The chosen split reflects the test prediction unit; leakage-sensitive gaps are explained.",
        })
    if "temporal_leakage" in risks:
        checks.append({
            "gate": "temporal_cv",
            "action": "Use forward or blocked temporal validation; fit every transform using past/training data only.",
            "pass_condition": "No future-derived feature or statistic crosses the split boundary.",
        })
    if "duplicate_leakage" in risks:
        checks.append({
            "gate": "deduplication_audit",
            "action": "Hash exact and near-duplicate samples before folding and keep duplicate clusters together.",
            "pass_condition": "Duplicate clusters do not appear on both sides of a fold.",
        })
    if "distribution_shift" in risks:
        checks.append({
            "gate": "shift_audit",
            "action": "Compare train/test distributions and run adversarial validation without target leakage.",
            "pass_condition": "Major shift drivers are identified and reflected in validation or robust features.",
        })
    if "class_imbalance" in risks or profile.metric_family == "threshold_classification":
        checks.append({
            "gate": "threshold_protocol",
            "action": "Tune thresholds using OOF predictions only and report per-class/fold stability.",
            "pass_condition": "Threshold choices are reproducible and not fitted on public LB feedback.",
        })
    return checks


def experiment_candidates(
    profile: CompetitionProfile,
    evidence: Sequence[dict],
    budget: str = "standard",
    *,
    allowed_claims: set[tuple[str, str]] | None = None,
) -> list[dict]:
    limits = {"quick": 5, "standard": 8, "deep": 12}
    max_items = limits.get(budget, limits["standard"])
    experiments: list[dict] = []
    experiments.append({
        "priority": "P0",
        "component": "validation",
        "hypothesis": "A metric-correct, leakage-resistant split is more valuable than early model complexity.",
        "change": "Implement the validation contract and a deterministic baseline with saved OOF predictions.",
        "evidence_anchors": [],
        "expected_signal": "Reliable fold variance and a reproducible reference score.",
        "stop_condition": "Do not proceed if metric, split, or submission assertions fail.",
        "cost": "low",
    })
    seen_changes: set[str] = set()
    component_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for source_limit in (1, 2):
        for hit in evidence:
            tricks = hit.get("trick_highlights") or []
            source_key = hit.get("anchor") or hit.get("source") or "unknown"
            if source_counts[source_key] >= source_limit:
                continue
            for trick in tricks:
                normalized = normalize_text(trick)
                if len(normalized) < 12 or normalized in seen_changes:
                    continue
                claim_key = (hit.get("competition_slug") or "", normalized)
                if allowed_claims is not None and claim_key not in allowed_claims:
                    continue
                component = infer_component(trick)
                cost = infer_cost(trick)
                if profile.stage in {"intake", "eda", "baseline"} and component == "ensemble":
                    continue
                if budget == "quick" and cost == "high":
                    continue
                if component_counts[component] >= 2:
                    continue
                seen_changes.add(normalized)
                source_counts[source_key] += 1
                component_counts[component] += 1
                experiments.append({
                    "priority": "P1" if hit.get("match_level") in {"exact", "direct"} else "P2",
                    "component": component,
                    "hypothesis": f"Historical pattern to validate under current conditions: {trick}",
                    "change": "Read the full anchor, deep-dive the source competition, verify transfer conditions, then implement the smallest isolated change.",
                    "evidence_anchors": [hit.get("anchor")],
                    "source_competition": hit.get("competition_slug"),
                    "deep_dive_required": True,
                    "expected_signal": component_expected_signal(component),
                    "stop_condition": "Discard if the mean gain is negligible, fold variance worsens materially, or runtime exceeds budget.",
                    "cost": cost,
                })
                break
            if len(experiments) >= max_items:
                return experiments
    return experiments


def component_expected_signal(component: str) -> str:
    signals = {
        "validation": "A more realistic split, lower unexplained fold variance, or removal of a leakage-sensitive gain.",
        "features": "Consistent OOF gain in the slices targeted by the new representation without leakage.",
        "model": "Mean OOF gain with stable folds and acceptable prediction diversity/runtime.",
        "training": "Improved convergence or target slices without degraded calibration or fold stability.",
        "inference": "OOF or held-out improvement from postprocessing/TTA with measured runtime cost.",
        "ensemble": "OOF gain explained by complementary residuals, not only model count.",
        "system": "Equivalent score with improved reproducibility, latency, memory or failure rate.",
        "pipeline": "A reproducible diagnostic change in mean, variance, slices or resource usage.",
    }
    return signals.get(component, signals["pipeline"])


def infer_component(text: str) -> str:
    mapping = {
        "validation": ("fold", "cv", "split", "leak", "验证", "分组", "时序"),
        "features": ("feature", "encoding", "aggregation", "特征", "编码", "聚合"),
        "model": ("model", "backbone", "lightgbm", "catboost", "transformer", "unet", "模型"),
        "training": ("loss", "optimizer", "augment", "sampling", "训练", "损失", "增强"),
        "inference": ("tta", "inference", "postprocess", "threshold", "推理", "后处理", "阈值"),
        "ensemble": ("blend", "stack", "oof", "ensemble", "融合", "集成"),
        "system": ("memory", "speed", "cache", "package", "runtime", "内存", "加速", "环境"),
    }
    for component, phrases in mapping.items():
        if any(phrase_present(text, phrase) for phrase in phrases):
            return component
    return "pipeline"


def infer_cost(text: str) -> str:
    if any(phrase_present(text, phrase) for phrase in ("multi gpu", "pretrain", "self play", "large model", "多卡", "预训练", "自博弈")):
        return "high"
    if any(phrase_present(text, phrase) for phrase in ("ensemble", "tta", "cross validation", "transformer", "集成", "多折")):
        return "medium"
    return "low"


def json_ready(value):
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, set):
        return sorted(value)
    return value
