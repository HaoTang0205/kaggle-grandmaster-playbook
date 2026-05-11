from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = SKILL_DIR / "assets" / "kaggle_book_catalog.json"
BOOK_ENV_VARS = ("KAGGLE_GRANDMASTER_BOOK", "KAGGLE_EXPERIENCE_BOOK")


def env_book_path() -> Path | None:
    for name in BOOK_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


DEFAULT_BOOKS = [
    env_book_path(),
    SKILL_DIR / "book" / "book.md",
    SKILL_DIR / "book_full" / "book.md",
    Path.cwd() / "book" / "book.md",
    Path.cwd() / "book_full" / "book.md",
]


@dataclass
class CatalogEntry:
    id: str
    chapter: str
    chapter_anchor: str
    title: str
    anchor: str
    competition_slug: str
    competition_url: str
    source: str
    source_url: str
    source_type: str
    tricks_count: int | None
    code_evidence_count: int | None
    quality_score: int | None
    algo_tags: list[str]
    core_keywords: list[str]
    trick_highlights: list[str]
    summary: str
    searchable_text: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def first_existing_book() -> Path:
    for path in DEFAULT_BOOKS:
        if path and path.exists():
            return path
    raise FileNotFoundError(
        "Could not find book.md. Set KAGGLE_GRANDMASTER_BOOK to the markdown book path."
    )


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_int(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d+", value.replace(",", ""))
    return int(match.group(0)) if match else None


def strip_md_link(value: str) -> tuple[str, str]:
    match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", value)
    if not match:
        return value.strip(), ""
    return match.group(1).strip(), match.group(2).strip()


def split_csvish(value: str) -> list[str]:
    value = value.replace("，", ",").replace("、", ",")
    return [x.strip() for x in value.split(",") if x.strip()]


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"^\d+\.\s*", "", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:80] or "section"


def split_sections(text: str) -> list[tuple[str, str, int, str]]:
    pattern = re.compile(r"^##\s+(\d+\.\s+.+?)(?:\s+\{#([^}]+)\})?\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: list[tuple[str, str, int, str]] = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_title = match.group(1).strip()
        anchor = (match.group(2) or f"auto-section-{i + 1}-{slugify(raw_title)}").strip()
        sections.append((raw_title, anchor, start, text[start:end]))
    return sections


def chapter_index(text: str) -> list[tuple[int, str, str]]:
    chapter_pattern = re.compile(r"^#\s+(第\d+章\s+.+?)(?:\s+\{#([^}]+)\})?\s*$", re.MULTILINE)
    return [
        (match.start(), match.group(1).strip(), (match.group(2) or "").strip())
        for match in chapter_pattern.finditer(text)
    ]


def chapter_for_position(chapters: list[tuple[int, str, str]], position: int) -> tuple[str, str]:
    current = ("", "")
    for start, title, anchor in chapters:
        if start > position:
            break
        current = (title, anchor)
    return current


def extract_prefixed(section: str, label: str) -> str:
    escaped = re.escape(label)
    match = re.search(rf"^-+\s*{escaped}\s*[:：]\s*(.+)$", section, flags=re.MULTILINE)
    if not match:
        match = re.search(rf"^\s*-\s*{escaped}\s*[:：]\s*(.+)$", section, flags=re.MULTILINE)
    return clean_line(match.group(1)) if match else ""


def parse_metadata(section: str) -> dict[str, str]:
    for line in section.splitlines():
        if line.startswith("> ") and ("比赛：" in line or "比赛:" in line) and ("来源：" in line or "来源:" in line):
            chunks = [x.strip() for x in re.split(r"\s*·\s*", line[2:])]
            result: dict[str, str] = {}
            for chunk in chunks:
                if "：" in chunk:
                    key, value = chunk.split("：", 1)
                elif ":" in chunk:
                    key, value = chunk.split(":", 1)
                else:
                    continue
                result[key.strip()] = value.strip()
            return result

    result: dict[str, str] = {}
    for line in section.splitlines()[:40]:
        match = re.match(r"^\s*-\s*([^:：]+)\s*[:：]\s*(.+?)\s*$", line)
        if not match:
            continue
        key = match.group(1).strip()
        value = match.group(2).strip()
        if key in {"比赛", "来源", "类型", "tricks", "代码证据", "代码证据条数", "质量分"}:
            result[key] = value
    return result


def has_source_metadata(meta: dict[str, str]) -> bool:
    return bool(meta.get("比赛") or meta.get("来源"))


def summarize_section(section: str) -> str:
    candidates = [
        extract_prefixed(section, "摘要"),
        extract_prefixed(section, "essence"),
        extract_prefixed(section, "teaching_takeaway"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate[:1200]

    lines = []
    capture = False
    for line in section.splitlines():
        if line.strip().lower() in {"##### summary", "### summary", "#### summary"}:
            capture = True
            continue
        if capture and line.startswith("##### "):
            break
        if capture and line.strip():
            lines.append(clean_line(line))
        if len(" ".join(lines)) > 1200:
            break
    return " ".join(lines)[:1200]


def extract_tricks(section: str) -> list[str]:
    value = extract_prefixed(section, "重点 trick")
    if value:
        return split_csvish(value)[:20]

    tricks: list[str] = []
    for match in re.finditer(r"^######\s+\d+\)\s+(.+)$", section, flags=re.MULTILINE):
        tricks.append(clean_line(match.group(1)))
        if len(tricks) >= 20:
            break
    return tricks


def parse_entries(text: str) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    chapters = chapter_index(text)
    for raw_title, anchor, section_pos, section in split_sections(text):
        chapter, chapter_anchor = chapter_for_position(chapters, section_pos)
        meta = parse_metadata(section)
        if not has_source_metadata(meta):
            continue

        competition_slug, competition_url = strip_md_link(meta.get("比赛", ""))
        source, source_url = strip_md_link(meta.get("来源", ""))
        source_type = meta.get("类型", "")
        tricks_count = parse_int(meta.get("tricks"))
        code_evidence_count = parse_int(meta.get("代码证据") or meta.get("代码证据条数"))
        quality_score = parse_int(meta.get("质量分"))

        algo_tags = split_csvish(extract_prefixed(section, "算法标签"))
        core_keywords = split_csvish(extract_prefixed(section, "核心关键词"))
        trick_highlights = extract_tricks(section)
        summary = summarize_section(section)

        title = re.sub(r"^\d+\.\s*", "", raw_title).strip()
        entry_id = anchor.removeprefix("section-")
        searchable_parts = [
            chapter,
            title,
            competition_slug,
            source,
            source_type,
            " ".join(algo_tags),
            " ".join(core_keywords),
            " ".join(trick_highlights),
            summary,
        ]
        entries.append(
            CatalogEntry(
                id=entry_id,
                chapter=chapter,
                chapter_anchor=chapter_anchor,
                title=title,
                anchor=anchor,
                competition_slug=competition_slug,
                competition_url=competition_url,
                source=source,
                source_url=source_url,
                source_type=source_type,
                tricks_count=tricks_count,
                code_evidence_count=code_evidence_count,
                quality_score=quality_score,
                algo_tags=algo_tags,
                core_keywords=core_keywords,
                trick_highlights=trick_highlights,
                summary=summary,
                searchable_text=" ".join(searchable_parts).lower(),
            )
        )
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a compact catalog from the Kaggle experience book.")
    parser.add_argument("--book", type=Path, default=None, help="Path to book.md. Defaults to KAGGLE_EXPERIENCE_BOOK or known local book paths.")
    parser.add_argument("--out", type=Path, default=DEFAULT_CATALOG, help="Output catalog JSON path.")
    args = parser.parse_args()

    book = args.book or first_existing_book()
    text = read_text(book)
    entries = parse_entries(text)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at_utc": utc_now(),
        "book_name": book.name,
        "entry_count": len(entries),
        "entries": [asdict(entry) for entry in entries],
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: indexed {len(entries)} book sections")
    print(f"catalog: {args.out}")
    print(f"book: {book}")


if __name__ == "__main__":
    main()
