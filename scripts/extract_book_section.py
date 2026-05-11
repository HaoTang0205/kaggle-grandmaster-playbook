from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


BOOK_ENV_VARS = ("KAGGLE_GRANDMASTER_BOOK", "KAGGLE_EXPERIENCE_BOOK")


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


def first_existing_book() -> Path:
    for path in DEFAULT_BOOKS:
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
    args = parser.parse_args()

    book = args.book or first_existing_book()
    section = extract_by_anchor(read_text(book), args.anchor)
    if args.max_chars and len(section) > args.max_chars:
        section = section[: args.max_chars] + "\n\n[truncated]"
    print(section)


if __name__ == "__main__":
    main()
