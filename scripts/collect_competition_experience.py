from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path

from research_competition import detect_signals, family_hypotheses
from search_book_catalog import infer_domains


TEXT_SUFFIXES = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}
CODE_SUFFIXES = {".py", ".ipynb", ".r", ".R", ".sql", ".sh"}
WRITEUP_HINTS = ("writeup", "write-up", "solution", "discussion", "summary", "方案", "复盘")
CODE_HINTS = ("kernel", "notebook", "code", "src", "script", "train", "infer", "submit")


@dataclass
class SourceFile:
    path: Path
    relpath: str
    kind: str
    chars: int
    score: int


def read_text(path: Path, max_chars: int) -> str:
    if path.suffix.lower() == ".ipynb":
        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            parts = []
            for cell in payload.get("cells", []):
                source = cell.get("source", [])
                if isinstance(source, list):
                    source = "".join(source)
                if source:
                    parts.append(str(source))
            return "\n\n".join(parts)[:max_chars]
        except Exception:
            return ""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding, errors="strict")[:max_chars]
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")[:max_chars]


def clean_text(value: str) -> str:
    value = re.sub(r"[A-Za-z]:\\(?:[^\\\r\n]+\\)+[^\\\r\n\s)`'\"]+", "<LOCAL_PATH>", value)
    value = re.sub(r"\b(?:sk|hf)_[A-Za-z0-9_-]{16,}|\bsk-[A-Za-z0-9_-]{16,}", "<SECRET_KEY>", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def classify_file(path: Path) -> str:
    lower = str(path).lower()
    suffix = path.suffix.lower()
    if suffix in CODE_SUFFIXES or any(hint in lower for hint in CODE_HINTS):
        return "code"
    if suffix in TEXT_SUFFIXES or any(hint in lower for hint in WRITEUP_HINTS):
        return "writeup"
    return "other"


def score_file(path: Path, kind: str) -> int:
    lower = str(path).lower()
    score = 20 if kind == "writeup" else 16 if kind == "code" else 0
    score += sum(8 for hint in WRITEUP_HINTS if hint in lower)
    score += sum(5 for hint in CODE_HINTS if hint in lower)
    if any(token in lower for token in ("1st", "first", "winner", "gold", "top", "高分", "第一")):
        score += 10
    return score


def discover_sources(root: Path, max_files: int) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        kind = classify_file(path)
        if kind == "other":
            continue
        try:
            chars = path.stat().st_size
        except OSError:
            chars = 0
        sources.append(SourceFile(path, rel.as_posix(), kind, chars, score_file(path, kind)))
    sources.sort(key=lambda item: (item.score, item.chars), reverse=True)
    return sources[:max_files]


def extract_keywords(text: str, domains: list[str], limit: int = 18) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_+#.-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    stop = {"the", "and", "for", "with", "from", "this", "that", "data", "model", "train", "test", "kaggle", "competition", "using", "use", "notebook", "code"}
    counter = Counter(word for word in words if word not in stop and len(word) <= 32)
    return list(dict.fromkeys(domains + [word for word, _ in counter.most_common(limit * 2)]))[:limit]


def extract_trick_candidates(text: str, limit: int = 12) -> list[str]:
    patterns = [
        r"(?i)(?:trick|tip|insight|key idea|what worked|solution|approach)[:：]\s*(.+?)(?:\.|。|\n)",
        r"(?i)(?:we used|we found|we improved|we solved|we applied)\s+(.+?)(?:\.|\n)",
        r"(?:使用|采用|通过|利用|关键|技巧|方案|提升|解决)(.+?)(?:。|\n)",
    ]
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = clean_text(match.group(1))
            if 12 <= len(candidate) <= 180 and candidate not in hits:
                hits.append(candidate)
            if len(hits) >= limit:
                return hits
    return hits


def markdown_link(label: str, url: str) -> str:
    return f"[{label}]({url})" if url else label


def render_card(args: argparse.Namespace, sources: list[SourceFile], sample_text: str, domains: list[str]) -> str:
    signals = detect_signals(sample_text)
    keywords = extract_keywords(sample_text, domains)
    tricks = extract_trick_candidates(sample_text)
    source_label = args.source or "collected-local-sources"
    source_url = args.source_url or args.competition_url
    quality_score = min(300, 80 + len(tricks) * 8 + sum(1 for s in sources if s.kind == "code") * 4 + sum(1 for s in sources if s.kind == "writeup") * 5)
    heading_slug = re.sub(r"[^a-z0-9]+", "-", f"{args.slug}-{source_label}".lower()).strip("-")[:96] or "new-competition"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"## 1. {source_label} {{#section-{heading_slug}}}",
        "",
        f"> 比赛：{markdown_link(args.slug or args.title or 'unknown-competition', args.competition_url)} · 来源：{markdown_link(source_label, source_url)} · 类型：collected_experience",
        "",
        f"- 算法标签：{', '.join(domains) if domains else 'unclassified'}",
        f"- 核心关键词：{', '.join(keywords)}",
        f"- tricks：{len(tricks)}",
        f"- 代码证据：{sum(1 for s in sources if s.kind == 'code')}",
        f"- 质量分：{quality_score}",
        f"- 收集日期：{timestamp}",
        "",
        "### 摘要",
        clean_text(args.summary or sample_text[:900]) or "待补充：请让分析模型基于 write-up、代码和讨论生成更完整摘要。",
        "",
        "### 题面与风险画像",
        f"- metric: {args.metric or ', '.join(signals.get('metrics', [])) or 'unknown'}",
        f"- data_signals: {args.data or ', '.join(signals.get('data', [])) or 'unknown'}",
        f"- risk_signals: {', '.join(signals.get('risks', [])) or 'unknown'}",
        "",
        "### Algorithm Family Hypotheses",
    ]
    for hyp in family_hypotheses(domains, signals):
        lines.append(f"- {hyp['domain']}: {', '.join(hyp['candidate_families'])}")
    lines += ["", "### 重点 Trick"]
    if tricks:
        lines.extend(f"{i}. {trick}" for i, trick in enumerate(tricks, 1))
    else:
        lines.append("1. 待分析：当前资料已归档，但需要进一步阅读 write-up/code 后提取。")
    lines += ["", "### Source Inventory", "| Kind | File | Size |", "|---|---|---:|"]
    lines.extend(f"| {item.kind} | `{item.relpath}` | {item.chars} |" for item in sources)
    lines += [
        "",
        "### Evidence Notes",
        "- 这是一张机器整理的初版经验卡，适合追加到 playbook 后再由大模型做精读分析。",
        "- 优先精读高分 write-up、最终提交代码、OOF/validation 说明、失败讨论和赛后复盘。",
        "- 若要进入正式书稿，请补充明确的代码证据、验证方式、可迁移条件与失败模式。",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect a new Kaggle competition source folder into a playbook-compatible experience card.")
    parser.add_argument("--source-dir", type=Path, required=True, help="Folder containing write-ups, notebooks, code, discussions, or notes.")
    parser.add_argument("--out", type=Path, required=True, help="Markdown output path for the collected experience card.")
    parser.add_argument("--slug", default="", help="Competition slug.")
    parser.add_argument("--title", default="", help="Competition title.")
    parser.add_argument("--competition-url", default="", help="Competition URL.")
    parser.add_argument("--source", default="", help="Source label, e.g. author/kernel/writeup name.")
    parser.add_argument("--source-url", default="", help="Source URL.")
    parser.add_argument("--metric", default="", help="Evaluation metric.")
    parser.add_argument("--data", default="", help="Data modality or schema notes.")
    parser.add_argument("--summary", default="", help="Optional human/LLM summary.")
    parser.add_argument("--max-files", type=int, default=40)
    parser.add_argument("--max-chars-per-file", type=int, default=12000)
    args = parser.parse_args()

    if not args.source_dir.exists():
        raise FileNotFoundError(args.source_dir)
    sources = discover_sources(args.source_dir, args.max_files)
    samples = []
    for item in sources:
        text = read_text(item.path, args.max_chars_per_file)
        if text:
            samples.append(f"\n\n### {item.relpath}\n{text}")
    sample_text = clean_text(" ".join([args.slug, args.title, args.metric, args.data, args.summary, *samples]))
    domains = infer_domains(sample_text, None, top_k=5)
    card = render_card(args, sources, sample_text, domains)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(card, encoding="utf-8")
    print(f"OK: wrote collected experience card to {args.out}")
    print(f"sources: {len(sources)} | domains: {', '.join(domains) if domains else 'unclassified'}")


if __name__ == "__main__":
    main()
