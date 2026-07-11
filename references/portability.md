# Portability And Isolation

## Purpose

The playbook is a normal agent skill and does not require a Harness adapter, LLM API, daemon, database server, or fixed installation path. Python scripts resolve resources from their own file location. Run commands from the skill root unless an absolute script path is used.

## Runtime

- Required: Python 3.10 or newer with SQLite FTS5 enabled.
- Core workflow: Python standard library only.
- Optional deep profilers: Pillow for additional image formats, PyArrow for Parquet/Feather schemas, and pydicom for DICOM metadata.
- Run `python scripts/skill_doctor.py --strict` after moving or installing the skill.

## Environment Overrides

| Variable | Meaning |
|---|---|
| `KAGGLE_GM_CATALOGS` | Additional catalog JSON paths separated by the platform path separator (`;` on Windows, `:` on Linux/macOS) |
| `KAGGLE_GRANDMASTER_BOOK` | Markdown book used for curated anchor extraction |
| `KAGGLE_EXPERIENCE_BOOK` | Backward-compatible book override |
| `KAGGLE_GM_KNOWLEDGE_BASE` | Directory containing promoted experience-card Markdown files |
| `KAGGLE_GM_CACHE_DIR` | Writable directory for fingerprinted SQLite retrieval indexes |
| `KAGGLE_GM_POLICY` | Retrieval-policy override JSON |
| `KAGGLE_GM_RUN_ID` | Owner token for one competition workspace |

The knowledge-pack manifest at `assets/knowledge-pack-manifest.json` records relative paths, sizes and SHA-256 hashes. The curated book/catalog and learned catalog are the core pack. The full archive and PDF are optional for minimal installations.

## Concurrent Competitions

Use one workspace per competition and agent run. The state file lives inside that workspace, so unrelated competitions never share a state machine.

Recommended layout:

```text
workspaces/
  competition-a/run-2026-07-11-a/
  competition-b/run-2026-07-11-b/
```

`competition_memory.py init` returns a unique `run_id`. Pass `--run-id` on every mutating command. Environment variables are shell-local and may not persist across stateless agent calls, so explicit `--run-id` is the portable default.

PowerShell:

```powershell
$env:KAGGLE_GM_RUN_ID = "returned-run-id"
```

Bash/Zsh:

```bash
export KAGGLE_GM_RUN_ID="returned-run-id"
```

CMD:

```bat
set KAGGLE_GM_RUN_ID=returned-run-id
```

Retrieval indexes are content-fingerprinted and protected by a build lock. Multiple competitions may read the same index concurrently. If the skill directory is read-only, set `KAGGLE_GM_CACHE_DIR` to a writable user cache directory; otherwise the code emits a warning before using the higher-memory in-process fallback.

## Moving The Skill

1. Move or clone the complete folder anywhere.
2. Keep relative subdirectories (`scripts`, `references`, `assets`, `knowledge_base`) together.
3. Run `python scripts/skill_doctor.py --strict`.
4. Run `python scripts/evaluate_skill.py --strict` for a no-Harness end-to-end test.
5. Install or symlink the folder into the agent's skill root only if that agent requires discovery there.

No command should contain the original author's drive letter or user profile path.

## Large Knowledge Pack

GitHub rejects individual blobs at 100 MB. `book_full/book.md` is currently below that boundary but is treated as an optional archive. If any artifact reaches 90 MB, publish it through Git LFS or a versioned release and retain its SHA-256 entry in the manifest. Do not silently truncate the archive to make a push succeed.
