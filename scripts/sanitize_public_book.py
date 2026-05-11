from __future__ import annotations

import argparse
import re
from pathlib import Path


REPLACEMENTS = [
    (re.compile(r"[A-Za-z]:\\(?:[^\\\r\n]+\\)+[^\\\r\n\s)`'\"]+"), "<LOCAL_PATH>"),
    (re.compile(r"\bOPENAI_API_KEY\s*=\s*[\"'][^\"']+[\"']"), 'OPENAI_API_KEY = "<SECRET>"'),
    (re.compile(r"\b(KAGGLE_KEY|KAGGLE_USERNAME|ANTHROPIC_AUTH_TOKEN)\s*=\s*[\"'][^\"']+[\"']"), r'\1 = "<SECRET>"'),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "<SECRET_KEY>"),
    (re.compile(r"\bhf_[A-Za-z0-9_\-]{16,}"), "<HF_TOKEN>"),
]


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def sanitize(text: str) -> str:
    for pattern, replacement in REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a public-safe copy of a Kaggle playbook markdown file.")
    parser.add_argument("--infile", type=Path, required=True)
    parser.add_argument("--outfile", type=Path, required=True)
    args = parser.parse_args()

    text = read_text(args.infile)
    cleaned = sanitize(text)
    args.outfile.parent.mkdir(parents=True, exist_ok=True)
    args.outfile.write_text(cleaned, encoding="utf-8")
    print(f"OK: wrote sanitized book to {args.outfile}")
    print(f"chars: {len(text)} -> {len(cleaned)}")


if __name__ == "__main__":
    main()
