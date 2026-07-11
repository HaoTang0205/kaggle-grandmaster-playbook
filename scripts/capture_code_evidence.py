from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def safe_relative_path(root: Path, path: Path) -> tuple[Path, str]:
    root = root.resolve()
    resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError("Code evidence must stay inside --code-root.") from error
    return resolved, relative


def sanitize_excerpt(value: str) -> str:
    value = re.sub(r"(?i)\b(?:sk|hf)[-_][A-Za-z0-9_-]{16,}\b", "<SECRET_KEY>", value)
    value = re.sub(
        r"(?i)\b(?:OPENAI_API_KEY|ANTHROPIC_AUTH_TOKEN|KAGGLE_KEY)\s*[:=]\s*\S+",
        "<SECRET>",
        value,
    )
    return "\n".join(line.rstrip() for line in value.splitlines()).strip()


def capture(
    root: Path,
    path: Path,
    start_line: int,
    end_line: int,
    *,
    symbol: str = "",
    language: str = "",
    lesson_ids: list[str] | None = None,
) -> dict:
    if start_line <= 0 or end_line < start_line or end_line - start_line + 1 > 120:
        raise ValueError("Code evidence line bounds must cover 1-120 lines.")
    resolved, relative = safe_relative_path(root, path)
    raw = resolved.read_bytes()
    if b"\x00" in raw[:8192]:
        raise ValueError("Code evidence must be a text source file.")
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if end_line > len(lines):
        raise ValueError(f"Requested end line {end_line} exceeds file length {len(lines)}.")
    excerpt = sanitize_excerpt("\n".join(lines[start_line - 1 : end_line]))
    if not excerpt:
        raise ValueError("Selected code evidence is empty.")
    return {
        "id": "",
        "path": relative,
        "language": language or resolved.suffix.lower().lstrip(".") or "text",
        "symbol": symbol or "relevant_block",
        "start_line": start_line,
        "end_line": end_line,
        "excerpt": excerpt,
        "content_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "lesson_ids": list(dict.fromkeys(lesson_ids or [])),
    }


def read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("code_evidence") or []
    if not isinstance(payload, list):
        raise ValueError("Existing evidence file must contain a list or a code_evidence list.")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a bounded, hash-verified source excerpt for an experiment.")
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--start-line", type=int, required=True)
    parser.add_argument("--end-line", type=int, required=True)
    parser.add_argument("--symbol", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--lesson-id", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    items = read_existing(args.out) if args.append else []
    item = capture(
        args.code_root,
        args.path,
        args.start_line,
        args.end_line,
        symbol=args.symbol,
        language=args.language,
        lesson_ids=args.lesson_id,
    )
    item["id"] = f"CE{len(items) + 1:03d}"
    items.append(item)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"schema_version": 1, "code_evidence": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(item, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
