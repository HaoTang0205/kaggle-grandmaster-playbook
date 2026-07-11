from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from evidence_safety import wrap_untrusted_evidence


BOOK_ENV_VARS = ("KAGGLE_GRANDMASTER_BOOK", "KAGGLE_EXPERIENCE_BOOK")
KNOWLEDGE_BASE_ENV = "KAGGLE_GM_KNOWLEDGE_BASE"


def env_book_path() -> Path | None:
    for name in BOOK_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return Path(value)
    return None


DEFAULT_BOOKS = [
    env_book_path(),
    Path(__file__).resolve().parents[1] / "book" / "book.md",
    Path(__file__).resolve().parents[1] / "book_full" / "book.md",
    Path.cwd() / "book" / "book.md",
    Path.cwd() / "book_full" / "book.md",
]


def split_sections(text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"^##\s+\d+\.\s+.+?(?:\s+\{#section-[^}]+\})?\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    sections: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((match.group(0), text[match.start() : end].strip()))
    return sections


def first_existing_book(anchor: str = "") -> Path:
    if anchor.startswith("experience-"):
        card_id = anchor.removeprefix("experience-")
        skill_dir = Path(__file__).resolve().parents[1]
        configured = Path(os.environ[KNOWLEDGE_BASE_ENV]) if os.environ.get(KNOWLEDGE_BASE_ENV) else None
        candidates = [
            configured / f"{card_id}.md" if configured else None,
            skill_dir / "knowledge_base" / "experience_cards" / f"{card_id}.md",
            Path.cwd() / "knowledge_base" / "experience_cards" / f"{card_id}.md",
        ]
        for path in candidates:
            if path and path.exists():
                return path
        raise FileNotFoundError(
            f"Could not find reviewed experience card {card_id}. Set {KNOWLEDGE_BASE_ENV} to its directory."
        )
    candidates = DEFAULT_BOOKS
    if anchor.startswith("auto-section-"):
        skill_dir = Path(__file__).resolve().parents[1]
        candidates = [
            env_book_path(),
            skill_dir / "book_full" / "book.md",
            Path.cwd() / "book_full" / "book.md",
            skill_dir / "book" / "book.md",
            Path.cwd() / "book" / "book.md",
        ]
    for path in candidates:
        if path and path.exists():
            return path
    raise FileNotFoundError("Could not find book.md. Set KAGGLE_GRANDMASTER_BOOK to the markdown book path.")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def extract_by_anchor(text: str, anchor: str) -> str:
    heading = re.compile(rf"^##\s+.+?\s+\{{#{re.escape(anchor)}\}}\s*$", re.MULTILINE)
    match = heading.search(text)
    if not match and anchor.startswith("auto-section-"):
        auto_match = re.match(r"auto-section-(\d+)-", anchor)
        if auto_match:
            index = int(auto_match.group(1)) - 1
            sections = split_sections(text)
            if 0 <= index < len(sections):
                return sections[index][1]
    if not match:
        raise ValueError(f"Anchor not found: {anchor}")
    next_match = re.search(r"^##\s+\d+\.\s+.+?\s+\{#section-[^}]+\}\s*$", text[match.end() :], flags=re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.start() : end].strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract one section from the Kaggle experience book by markdown anchor.")
    parser.add_argument("--anchor", required=True, help="Section anchor returned by search_book_catalog.py.")
    parser.add_argument("--book", type=Path, default=None)
    parser.add_argument("--max-chars", type=int, default=20000)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print unwrapped source text for human inspection only. Agent workflows must use the default boundary.",
    )
    args = parser.parse_args()

    book = args.book or first_existing_book(args.anchor)
    section = extract_by_anchor(read_text(book), args.anchor)
    if args.max_chars and len(section) > args.max_chars:
        section = section[: args.max_chars] + "\n\n[truncated]"
    if not args.raw:
        section = wrap_untrusted_evidence(section, source=book.name, anchor=args.anchor)
    print(section)


if __name__ == "__main__":
    main()
