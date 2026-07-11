from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "assets" / "knowledge-pack-manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def selected_files() -> list[tuple[Path, str, bool]]:
    files = [
        (ROOT / "book" / "book.md", "curated_book", True),
        (ROOT / "book" / "book.pdf", "reading_edition", False),
        (ROOT / "book_full" / "book.md", "full_archive", False),
        (ROOT / "assets" / "kaggle_book_catalog.json", "curated_catalog", True),
        (ROOT / "assets" / "kaggle_book_catalog_full.json", "full_catalog", False),
        (ROOT / "assets" / "learned_experience_catalog.json", "learned_catalog", True),
        (ROOT / "CONTENT_LICENSE.md", "license_boundary", True),
    ]
    for path in sorted((ROOT / "knowledge_base" / "experience_cards").glob("*.*")):
        if path.suffix.lower() in {".json", ".md"}:
            files.append((path, "reviewed_experience_card", True))
    return files


def build_manifest() -> dict:
    files = []
    for path, role, required in selected_files():
        if not path.exists():
            if required:
                raise FileNotFoundError(path)
            continue
        files.append({
            "path": path.relative_to(ROOT).as_posix(),
            "role": role,
            "required_for_core": required,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return {
        "schema_version": 1,
        "pack_name": "kaggle-grandmaster-playbook-knowledge",
        "portability": {
            "paths": "relative_to_skill_root",
            "catalog_override_env": "KAGGLE_GM_CATALOGS",
            "book_override_env": "KAGGLE_GRANDMASTER_BOOK",
            "knowledge_base_override_env": "KAGGLE_GM_KNOWLEDGE_BASE",
            "cache_override_env": "KAGGLE_GM_CACHE_DIR",
        },
        "distribution": {
            "github_single_blob_hard_limit_bytes": 100000000,
            "release_or_lfs_recommended_from_bytes": 90000000,
            "full_archive_is_optional": True,
        },
        "files": files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or verify the portable knowledge-pack manifest.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_manifest()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not args.out.exists() or args.out.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Knowledge-pack manifest is missing or stale; rebuild it without --check.")
        print(f"OK: {len(payload['files'])} knowledge-pack files verified")
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"OK: wrote {len(payload['files'])} files to {args.out}")


if __name__ == "__main__":
    main()
