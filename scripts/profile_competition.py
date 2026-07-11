from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import struct
import wave
import zipfile

from grandmaster_core import build_profile, configure_policy, json_ready


TABLE_SUFFIXES = {".csv", ".tsv", ".parquet", ".feather"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".dcm", ".nii"}
AUDIO_SUFFIXES = {".wav", ".ogg", ".flac", ".mp3", ".m4a"}
TEXT_SUFFIXES = {".txt", ".json", ".jsonl", ".xml", ".md", ".html"}
ARCHIVE_SUFFIXES = {".zip", ".7z", ".tar", ".gz"}
SKIP_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", "node_modules", "build", "dist"}
REPLAY_HINTS = ("replay", "episode", "trajectory", "rollout", "match", "game")


@dataclass
class TableSummary:
    file: str
    delimiter: str
    columns: list[str]
    sampled_rows: int
    missing_fraction: dict[str, float]
    unique_fraction: dict[str, float]


@dataclass
class AssetSummary:
    file: str
    kind: str
    details: dict


def classify_role(path: Path) -> str:
    name = path.stem.lower()
    if "sample" in name and "submission" in name:
        return "sample_submission"
    if name == "train" or name.startswith("train_") or name.endswith("_train"):
        return "train"
    if name == "test" or name.startswith("test_") or name.endswith("_test"):
        return "test"
    if "submission" in name:
        return "submission_related"
    return "auxiliary"


def delimiter_for(path: Path) -> str:
    if path.suffix.lower() == ".tsv":
        return "\t"
    try:
        sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        return ","


def summarize_csv(path: Path, root: Path, max_rows: int) -> TableSummary:
    delimiter = delimiter_for(path)
    missing: Counter[str] = Counter()
    uniques: dict[str, set[str]] = {}
    sampled = 0
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        uniques = {column: set() for column in columns}
        for row in reader:
            sampled += 1
            for column in columns:
                value = (row.get(column) or "").strip()
                if value.lower() in {"", "na", "nan", "null", "none"}:
                    missing[column] += 1
                elif len(uniques[column]) <= max_rows:
                    uniques[column].add(value)
            if sampled >= max_rows:
                break
    denominator = max(sampled, 1)
    return TableSummary(
        file=path.relative_to(root).as_posix(),
        delimiter="TAB" if delimiter == "\t" else delimiter,
        columns=columns,
        sampled_rows=sampled,
        missing_fraction={column: round(missing[column] / denominator, 4) for column in columns if missing[column]},
        unique_fraction={column: round(len(uniques[column]) / denominator, 4) for column in columns},
    )


def summarize_columnar(path: Path, root: Path, max_rows: int) -> tuple[TableSummary | None, str]:
    try:
        if path.suffix.lower() == ".parquet":
            import pyarrow.parquet as parquet  # type: ignore[import-not-found]

            metadata = parquet.read_metadata(path)
            columns = list(metadata.schema.names)
            rows = min(int(metadata.num_rows), max_rows)
            return TableSummary(
                file=path.relative_to(root).as_posix(),
                delimiter="PARQUET",
                columns=columns,
                sampled_rows=rows,
                missing_fraction={},
                unique_fraction={},
            ), ""
        import pyarrow.feather as feather  # type: ignore[import-not-found]

        table = feather.read_table(path, memory_map=True)
        return TableSummary(
            file=path.relative_to(root).as_posix(),
            delimiter="FEATHER",
            columns=list(table.column_names),
            sampled_rows=min(int(table.num_rows), max_rows),
            missing_fraction={},
            unique_fraction={},
        ), ""
    except ImportError:
        return None, f"{path.suffix.lower()} schema inspection needs optional pyarrow"
    except Exception as error:
        return None, f"could not inspect {path.name}: {type(error).__name__}"


def image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image  # type: ignore[import-not-found]

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        pass
    try:
        header = path.read_bytes()[:32]
        if header.startswith(b"\x89PNG\r\n\x1a\n") and len(header) >= 24:
            width, height = struct.unpack(">II", header[16:24])
            return int(width), int(height)
    except OSError:
        pass
    return None


def summarize_image(path: Path, root: Path) -> AssetSummary:
    dimensions = image_dimensions(path)
    details = {"size_bytes": path.stat().st_size}
    if dimensions:
        details.update({"width": dimensions[0], "height": dimensions[1]})
    if path.suffix.lower() == ".dcm":
        details["format_note"] = "DICOM metadata requires optional pydicom for patient/study inspection"
    return AssetSummary(path.relative_to(root).as_posix(), "image", details)


def summarize_audio(path: Path, root: Path) -> AssetSummary:
    details = {"size_bytes": path.stat().st_size}
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as audio:
                frames = audio.getnframes()
                rate = audio.getframerate()
                details.update({
                    "channels": audio.getnchannels(),
                    "sample_rate": rate,
                    "duration_seconds": round(frames / max(rate, 1), 4),
                })
        except (wave.Error, OSError):
            details["inspection_error"] = "invalid WAV header"
    else:
        details["format_note"] = "duration inspection needs an optional audio decoder"
    return AssetSummary(path.relative_to(root).as_posix(), "audio", details)


def summarize_text_asset(path: Path, root: Path, max_chars: int = 200_000) -> AssetSummary:
    text = path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    lines = text.splitlines()
    details = {
        "sampled_characters": len(text),
        "sampled_lines": len(lines),
        "mean_line_length": round(sum(map(len, lines)) / max(len(lines), 1), 3),
    }
    if path.suffix.lower() in {".json", ".jsonl"}:
        first = next((line for line in lines if line.strip()), "")
        try:
            value = json.loads(first if path.suffix.lower() == ".jsonl" else text)
            if isinstance(value, dict):
                details["top_level_keys"] = sorted(map(str, value.keys()))[:40]
            elif isinstance(value, list):
                details["top_level_type"] = "list"
                details["sampled_items"] = len(value)
        except json.JSONDecodeError:
            details["json_parse"] = "partial_or_invalid"
    return AssetSummary(path.relative_to(root).as_posix(), "text", details)


def summarize_archive(path: Path, root: Path) -> AssetSummary:
    details = {"size_bytes": path.stat().st_size}
    if path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                suffixes = Counter(Path(name).suffix.lower() or "<none>" for name in names if not name.endswith("/"))
                details.update({"entry_count": len(names), "entry_suffixes": dict(suffixes.most_common(12))})
        except (OSError, zipfile.BadZipFile):
            details["inspection_error"] = "invalid ZIP archive"
    else:
        details["format_note"] = "archive listing is not available without an optional decoder"
    return AssetSummary(path.relative_to(root).as_posix(), "archive", details)


def asset_profiles(root: Path, inventory: list[dict], max_per_kind: int = 30) -> dict:
    output: dict[str, list[dict]] = {"images": [], "audio": [], "text": [], "replays": [], "archives": []}
    for item in inventory:
        path = root / item["file"]
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES or path.name.lower().endswith(".nii.gz"):
            if len(output["images"]) < max_per_kind:
                output["images"].append(asdict(summarize_image(path, root)))
        elif suffix in AUDIO_SUFFIXES:
            if len(output["audio"]) < max_per_kind:
                output["audio"].append(asdict(summarize_audio(path, root)))
        elif suffix in TEXT_SUFFIXES:
            if len(output["text"]) < max_per_kind:
                summary = asdict(summarize_text_asset(path, root))
                output["text"].append(summary)
                if any(hint in path.name.lower() for hint in REPLAY_HINTS) and len(output["replays"]) < max_per_kind:
                    replay = dict(summary)
                    replay["kind"] = "replay"
                    output["replays"].append(replay)
        elif suffix in ARCHIVE_SUFFIXES:
            if len(output["archives"]) < max_per_kind:
                output["archives"].append(asdict(summarize_archive(path, root)))
    rule_files = [
        item["file"]
        for item in inventory
        if Path(item["file"]).suffix.lower() in {".py", ".rs", ".cpp", ".java", ".js", ".ts"}
        and any(hint in Path(item["file"]).name.lower() for hint in ("rule", "environment", "env", "agent", "simulator"))
    ]
    output["rule_code_candidates"] = rule_files[:50]
    return output


def file_inventory(root: Path) -> tuple[list[dict], Counter[str]]:
    inventory: list[dict] = []
    suffix_counts: Counter[str] = Counter()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") or part.lower() in SKIP_DIRS for part in relative.parts):
            continue
        suffix = path.suffix.lower() or "<none>"
        suffix_counts[suffix] += 1
        inventory.append(
            {
                "file": relative.as_posix(),
                "size_bytes": path.stat().st_size,
                "suffix": suffix,
                "role": classify_role(path),
            }
        )
    inventory.sort(key=lambda item: (item["role"] != "train", item["role"] != "test", -item["size_bytes"]))
    return inventory, suffix_counts


def infer_modalities(suffix_counts: Counter[str], tables: list[TableSummary]) -> list[str]:
    modalities: list[str] = []
    suffixes = set(suffix_counts)
    if tables or suffixes & TABLE_SUFFIXES:
        modalities.append("tabular")
    if suffixes & IMAGE_SUFFIXES:
        modalities.append("image")
    if suffixes & AUDIO_SUFFIXES:
        modalities.append("audio")
    if suffixes & TEXT_SUFFIXES:
        modalities.append("text")
    if suffixes & ARCHIVE_SUFFIXES:
        modalities.append("archives_require_inspection")
    return modalities


def by_role(inventory: list[dict], role: str) -> list[str]:
    return [item["file"] for item in inventory if item["role"] == role]


def first_table(tables: list[TableSummary], inventory: list[dict], role: str) -> TableSummary | None:
    role_files = set(by_role(inventory, role))
    return next((table for table in tables if table.file in role_files), None)


def name_candidates(columns: list[str], patterns: tuple[str, ...]) -> list[str]:
    return [column for column in columns if any(pattern in column.lower() for pattern in patterns)]


def infer_schema_signals(tables: list[TableSummary], inventory: list[dict]) -> dict:
    train = first_table(tables, inventory, "train")
    test = first_table(tables, inventory, "test")
    sample = first_table(tables, inventory, "sample_submission")
    train_columns = set(train.columns if train else [])
    test_columns = set(test.columns if test else [])
    sample_columns = set(sample.columns if sample else [])
    target_candidates = sorted(train_columns - test_columns)
    if sample_columns and test_columns:
        target_candidates = sorted(set(target_candidates) | (sample_columns - test_columns))
    all_columns = sorted(train_columns | test_columns)
    id_candidates = name_candidates(all_columns, ("id", "uuid", "key", "index"))
    group_candidates = name_candidates(
        all_columns,
        ("group", "patient", "customer", "user", "speaker", "recording", "study", "session", "subject", "scene"),
    )
    time_candidates = name_candidates(all_columns, ("time", "date", "timestamp", "year", "month", "day", "week"))
    return {
        "target_candidates": target_candidates,
        "id_candidates": id_candidates,
        "group_candidates": group_candidates,
        "time_candidates": time_candidates,
        "train_only_columns": sorted(train_columns - test_columns),
        "test_only_columns": sorted(test_columns - train_columns),
        "sample_submission_columns": sorted(sample_columns),
    }


def data_description(
    modalities: list[str],
    schema: dict,
    suffix_counts: Counter[str],
    assets: dict | None = None,
) -> str:
    pieces = ["modalities " + " ".join(modalities)]
    for key in ("target_candidates", "id_candidates", "group_candidates", "time_candidates"):
        if schema[key]:
            pieces.append(f"{key} " + " ".join(schema[key]))
    pieces.append("file types " + " ".join(f"{suffix}:{count}" for suffix, count in suffix_counts.most_common(12)))
    if assets:
        pieces.append(
            "asset samples "
            + " ".join(
                f"{name}:{len(values)}"
                for name, values in assets.items()
                if isinstance(values, list) and values
            )
        )
    return "; ".join(pieces)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a competition data directory and create an agent-ready profile.")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--slug", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--metric", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--max-csv-rows", type=int, default=5000)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--policy", type=Path, default=None, help="Optional profile/retrieval policy override JSON.")
    args = parser.parse_args()

    configure_policy(args.policy)

    root = args.data_dir.resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    inventory, suffix_counts = file_inventory(root)
    tables = []
    inspection_issues = []
    for item in inventory:
        path = root / item["file"]
        if path.suffix.lower() in {".csv", ".tsv"}:
            tables.append(summarize_csv(path, root, args.max_csv_rows))
        elif path.suffix.lower() in {".parquet", ".feather"}:
            summary, issue = summarize_columnar(path, root, args.max_csv_rows)
            if summary:
                tables.append(summary)
            if issue:
                inspection_issues.append({"file": item["file"], "issue": issue})
    modalities = infer_modalities(suffix_counts, tables)
    schema = infer_schema_signals(tables, inventory)
    assets = asset_profiles(root, inventory)
    profile = build_profile(
        slug=args.slug,
        title=args.title,
        description=args.description,
        metric=args.metric,
        data=data_description(modalities, schema, suffix_counts, assets),
        constraints=args.constraints,
        stage="eda",
    )
    payload = {
        "profile_version": 1,
        "profile": profile.to_dict(),
        "data_root": root.name,
        "file_count": len(inventory),
        "file_type_counts": dict(suffix_counts),
        "roles": {
            "train": by_role(inventory, "train"),
            "test": by_role(inventory, "test"),
            "sample_submission": by_role(inventory, "sample_submission"),
            "auxiliary": by_role(inventory, "auxiliary"),
        },
        "modalities": modalities,
        "schema_signals": schema,
        "tables": [asdict(table) for table in tables],
        "asset_profiles": assets,
        "inspection_issues": inspection_issues,
        "data_usage_gate": {
            "required_files": [item["file"] for item in inventory],
            "rule": "Every provided source must be used or explicitly documented as irrelevant before finalizing a pipeline.",
        },
    }
    rendered = json.dumps(json_ready(payload), ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
