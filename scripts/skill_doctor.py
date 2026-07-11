from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from distill_competition_experience import card_integrity_errors
from grandmaster_core import CACHE_DIR_ENV, default_catalog_paths, safe_public_url


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets" / "knowledge-pack-manifest.json"
PRIVATE_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:Users|home)/[^/\s]+/)")
CREDENTIAL = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{20,}\b|\b(?:OPENAI_API_KEY|ANTHROPIC_AUTH_TOKEN|KAGGLE_KEY)\s*[:=]\s*[^<\s])"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def result(name: str, status: str, detail) -> dict:
    return {"name": name, "status": status, "detail": detail}


def check_python() -> dict:
    passed = sys.version_info >= (3, 10)
    return result("python", "pass" if passed else "fail", {
        "version": ".".join(map(str, sys.version_info[:3])),
        "minimum": "3.10",
    })


def check_skill_metadata() -> dict:
    path = ROOT / "SKILL.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    valid = bool(
        text.startswith("---\n")
        and re.search(r"(?m)^name:\s*kaggle-grandmaster-playbook\s*$", text)
        and re.search(r"(?m)^description:\s*.+$", text)
    )
    return result("skill_metadata", "pass" if valid else "fail", str(path.relative_to(ROOT)))


def check_fts5() -> dict:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        connection.execute("INSERT INTO probe(text) VALUES ('kaggle evidence')")
        matched = connection.execute("SELECT count(*) FROM probe WHERE probe MATCH 'evidence'").fetchone()[0] == 1
        return result("sqlite_fts5", "pass" if matched else "fail", sqlite3.sqlite_version)
    except sqlite3.Error as error:
        return result("sqlite_fts5", "fail", f"{type(error).__name__}: {error}")
    finally:
        connection.close()


def check_cache() -> dict:
    cache = Path(os.environ.get(CACHE_DIR_ENV) or ROOT / ".cache").expanduser().resolve()
    probe = cache / f".doctor-{os.getpid()}.tmp"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
        return result("cache_writable", "pass", str(cache))
    except OSError as error:
        return result(
            "cache_writable",
            "warn",
            f"{cache}: {type(error).__name__}; retrieval will use the documented in-memory fallback",
        )


def check_catalogs() -> dict:
    summaries = []
    paths = default_catalog_paths()
    failed = not paths
    for path in paths:
        if not path.exists():
            failed = True
            summaries.append({"path": str(path), "error": "missing"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            entries = payload.get("entries") or []
            linked = sum(1 for item in entries if safe_public_url(item.get("source_url") or ""))
            hashed = sum(1 for item in entries if re.fullmatch(r"[a-f0-9]{64}", str(item.get("source_content_sha256") or "")))
            ratio = linked / max(len(entries), 1)
            if not entries or ratio < 0.95 or hashed != len(entries):
                failed = True
            summaries.append({
                "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
                "entries": len(entries),
                "source_link_ratio": round(ratio, 4),
                "content_hash_ratio": round(hashed / max(len(entries), 1), 4),
            })
        except (OSError, json.JSONDecodeError) as error:
            failed = True
            summaries.append({"path": str(path), "error": f"{type(error).__name__}: {error}"})
    return result("catalog_integrity", "fail" if failed else "pass", summaries)


def check_cards() -> dict:
    errors = {}
    cards = sorted((ROOT / "knowledge_base" / "experience_cards").glob("*.json"))
    for path in cards:
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
            problems = card_integrity_errors(card, path, require_promoted=True)
        except (OSError, json.JSONDecodeError) as error:
            problems = [f"{type(error).__name__}: {error}"]
        if problems:
            errors[path.name] = problems
    return result(
        "experience_cards",
        "fail" if errors else "pass",
        {"card_count": len(cards), "errors": errors},
    )


def public_text_files() -> list[Path]:
    files = [
        ROOT / "SKILL.md",
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "CONTENT_LICENSE.md",
    ]
    files.extend((ROOT / "references").glob("*.md"))
    files.extend((ROOT / "agents").glob("*.yaml"))
    files.extend((ROOT / "config").glob("*.json"))
    files.extend((ROOT / "knowledge_base" / "experience_cards").glob("*.*"))
    return [path for path in files if path.exists()]


def check_privacy() -> dict:
    findings = []
    for path in public_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if PRIVATE_PATH.search(line) or CREDENTIAL.search(line):
                findings.append(f"{path.relative_to(ROOT).as_posix()}:{line_number}")
    return result("public_privacy", "fail" if findings else "pass", findings)


def check_manifest() -> dict:
    if not MANIFEST.exists():
        return result("knowledge_manifest", "warn", "not generated")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mismatches = []
    optional_missing = []
    for item in payload.get("files") or []:
        path = ROOT / item["path"]
        if not path.exists():
            target = mismatches if item.get("required_for_core") else optional_missing
            target.append({"path": item["path"], "error": "missing"})
            continue
        if path.stat().st_size != item["size_bytes"] or digest(path) != item["sha256"]:
            mismatches.append({"path": item["path"], "error": "size or SHA-256 mismatch"})
    status = "fail" if mismatches else "warn" if optional_missing else "pass"
    return result("knowledge_manifest", status, {
        "files": len(payload.get("files") or []),
        "mismatches": mismatches,
        "optional_missing": optional_missing,
    })


def check_blob_sizes() -> dict:
    files = [ROOT / "book_full" / "book.md", ROOT / "book" / "book.pdf"]
    oversized = [path.relative_to(ROOT).as_posix() for path in files if path.exists() and path.stat().st_size >= 100_000_000]
    near_limit = [
        {"path": path.relative_to(ROOT).as_posix(), "size_bytes": path.stat().st_size}
        for path in files
        if path.exists() and 90_000_000 <= path.stat().st_size < 100_000_000
    ]
    status = "fail" if oversized else "warn" if near_limit else "pass"
    return result("github_blob_limit", status, {"oversized": oversized, "near_limit": near_limit})


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a relocated Kaggle Grandmaster Playbook skill installation.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    checks = [
        check_python(),
        check_skill_metadata(),
        check_fts5(),
        check_cache(),
        check_catalogs(),
        check_cards(),
        check_privacy(),
        check_manifest(),
        check_blob_sizes(),
    ]
    payload = {
        "schema_version": 1,
        "skill_root": str(ROOT),
        "portable_root_resolution": Path(__file__).resolve().is_relative_to(ROOT),
        "passed": all(item["status"] != "fail" for item in checks),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"skill doctor: {'PASS' if payload['passed'] else 'FAIL'}")
        for item in checks:
            print(f"{item['status'].upper():4} {item['name']}: {item['detail']}")
    if args.strict and not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
