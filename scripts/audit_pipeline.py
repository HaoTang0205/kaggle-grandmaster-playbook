from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    line: int
    message: str
    action: str


SEVERITY_ORDER = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
UNSAFE_RANDOM_SPLITTERS = {"KFold", "StratifiedKFold", "ShuffleSplit", "StratifiedShuffleSplit", "train_test_split"}
FIT_METHODS = {"fit", "fit_transform", "partial_fit"}


def load_profile(path: Path | None) -> dict:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Profile JSON must contain an object.")
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
    return {
        "profile": profile,
        "schema_signals": payload.get("schema_signals") or {},
        "roles": payload.get("roles") or {},
        "data_usage_gate": payload.get("data_usage_gate") or {},
    }


def call_name(call: ast.Call) -> str:
    function = call.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return ""


def expression_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def identifiers(node: ast.AST) -> set[str]:
    values: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            values.add(child.id.lower())
        elif isinstance(child, ast.Attribute):
            values.add(child.attr.lower())
        elif isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.add(child.value.lower())
    return values


def has_token(values: Iterable[str], token: str) -> bool:
    return any(re.search(rf"(^|[^a-z0-9]){re.escape(token)}([^a-z0-9]|$)", value) for value in values)


def contains_test_reference(node: ast.AST) -> bool:
    return has_token(identifiers(node), "test")


def target_candidates(profile: dict) -> list[str]:
    return [str(value).lower() for value in profile.get("schema_signals", {}).get("target_candidates", [])]


def has_group_risk(profile: dict) -> bool:
    risks = profile.get("profile", {}).get("validation_risks") or []
    groups = profile.get("schema_signals", {}).get("group_candidates") or []
    return "group_leakage" in risks or bool(groups)


def has_time_risk(profile: dict) -> bool:
    risks = profile.get("profile", {}).get("validation_risks") or []
    times = profile.get("schema_signals", {}).get("time_candidates") or []
    return "temporal_leakage" in risks or bool(times)


def source_line(source: str, line: int) -> str:
    lines = source.splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else ""


def audit_ast(tree: ast.AST, source: str, profile: dict) -> list[Finding]:
    findings: list[Finding] = []
    targets = set(target_candidates(profile))
    split_calls: list[tuple[str, int]] = []
    fit_transform_lines: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = call_name(node)
            if name in FIT_METHODS:
                if name == "fit_transform":
                    fit_transform_lines.append(node.lineno)
                if any(contains_test_reference(argument) for argument in node.args):
                    findings.append(
                        Finding(
                            "blocker",
                            "fit-on-test",
                            node.lineno,
                            f"`{name}` receives a test-like object: {source_line(source, node.lineno)}",
                            "Fit every learned transform/model on training-fold data only, then transform test data.",
                        )
                    )
            if name in UNSAFE_RANDOM_SPLITTERS:
                split_calls.append((name, node.lineno))
            if name == "concat" and contains_test_reference(node) and has_token(identifiers(node), "train"):
                findings.append(
                    Finding(
                        "high",
                        "train-test-concat",
                        node.lineno,
                        "Train and test objects are concatenated before modeling/preprocessing.",
                        "Prove the operation is label-free and allowed; otherwise fit preprocessing on training folds only.",
                    )
                )

        if isinstance(node, ast.Subscript):
            values = identifiers(node.value)
            if has_token(values, "test"):
                slice_text = expression_text(node.slice).strip("'\"").lower()
                if slice_text in targets:
                    findings.append(
                        Finding(
                            "blocker",
                            "test-target-access",
                            node.lineno,
                            f"The script accesses target candidate `{slice_text}` from a test-like object.",
                            "Remove test-label access and verify the competition data boundary.",
                        )
                    )

    if has_group_risk(profile):
        for name, line in split_calls:
            findings.append(
                Finding(
                    "high",
                    "group-risk-random-split",
                    line,
                    f"Profile contains entity/group risk, but the script uses `{name}`.",
                    "Use a group-disjoint splitter and assert no group appears on both sides of a fold.",
                )
            )
    if has_time_risk(profile):
        for name, line in split_calls:
            findings.append(
                Finding(
                    "high",
                    "time-risk-random-split",
                    line,
                    f"Profile contains temporal risk, but the script uses `{name}`.",
                    "Use forward/blocked temporal validation and fit transforms using past/training data only.",
                )
            )

    if split_calls and fit_transform_lines:
        first_split = min(line for _, line in split_calls)
        for line in fit_transform_lines:
            if line < first_split:
                findings.append(
                    Finding(
                        "high",
                        "preprocess-before-split",
                        line,
                        "A learned `fit_transform` appears before the first validation split.",
                        "Split first; fit preprocessing independently inside each training fold.",
                    )
                )
    return findings


def audit_data_usage(source: str, profile: dict) -> list[Finding]:
    required = profile.get("data_usage_gate", {}).get("required_files") or []
    if not required:
        return []
    lower = source.lower()
    dynamic_discovery = any(token in lower for token in ("glob(", "rglob(", "os.walk", "listdir(", "iterdir("))
    missing = []
    for value in required:
        path = Path(str(value))
        if path.name.lower() not in lower and str(value).replace("\\", "/").lower() not in lower:
            missing.append(str(value))
    if missing and not dynamic_discovery:
        return [
            Finding(
                "medium",
                "unused-data-sources",
                0,
                "Provided files are not referenced: " + ", ".join(missing[:12]),
                "Use each relevant source or document why it is intentionally excluded.",
            )
        ]
    if missing:
        return [
            Finding(
                "info",
                "dynamic-data-usage",
                0,
                "Some files are not named explicitly, but dynamic file discovery is present.",
                "Log the resolved file manifest at runtime and compare it with the profile inventory.",
            )
        ]
    return []


def audit_reproducibility(source: str, profile: dict) -> list[Finding]:
    lower = source.lower()
    findings: list[Finding] = []
    if not any(token in lower for token in ("random_state", "manual_seed", "seed_everything", "np.random.seed", "random.seed")):
        findings.append(
            Finding(
                "low",
                "seed-not-observed",
                0,
                "No explicit seed or random_state was observed.",
                "Set and record Python/NumPy/framework seeds and deterministic settings where practical.",
            )
        )
    metric = str(profile.get("profile", {}).get("metric") or "").lower()
    metric_tokens = [token for token in re.findall(r"[a-z0-9]+", metric) if len(token) > 1]
    if metric_tokens and not any(token in lower for token in metric_tokens):
        findings.append(
            Finding(
                "medium",
                "metric-not-observed",
                0,
                f"The official metric `{metric}` is not recognizable in the script.",
                "Implement or import the official metric and test it on a hand-checked example.",
            )
        )
    if "to_csv" in lower and "sample_submission" not in lower and "sample submission" not in lower:
        findings.append(
            Finding(
                "medium",
                "submission-template-not-observed",
                0,
                "The script writes CSV output without an obvious sample-submission template check.",
                "Build the submission from the official template and assert IDs, order, columns and row count.",
            )
        )
    return findings


def deduplicate(findings: list[Finding]) -> list[Finding]:
    unique = {(item.severity, item.rule, item.line, item.message): item for item in findings}
    return sorted(unique.values(), key=lambda item: (SEVERITY_ORDER[item.severity], item.line, item.rule))


def audit_script(path: Path, profile: dict) -> dict:
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as error:
        finding = Finding(
            "blocker",
            "syntax-error",
            error.lineno or 0,
            error.msg,
            "Fix syntax before any training or submission attempt.",
        )
        findings = [finding]
    else:
        findings = deduplicate(
            audit_ast(tree, source, profile)
            + audit_data_usage(source, profile)
            + audit_reproducibility(source, profile)
        )
    counts = {severity: sum(1 for item in findings if item.severity == severity) for severity in SEVERITY_ORDER}
    status = "fail" if counts["blocker"] else "review" if counts["high"] or counts["medium"] else "pass"
    return {
        "script": path.name,
        "status": status,
        "counts": counts,
        "findings": [asdict(item) for item in findings],
        "disclaimer": "Static heuristics can miss semantic leakage and may flag intentional transductive steps; review every finding in competition context.",
    }


def render_text(payload: dict) -> str:
    lines = [f"pipeline audit: {payload['status']} | script={payload['script']}"]
    lines.append("counts: " + ", ".join(f"{key}={value}" for key, value in payload["counts"].items()))
    for finding in payload["findings"]:
        location = f"line {finding['line']}" if finding["line"] else "global"
        lines.append(f"\n[{finding['severity'].upper()}] {finding['rule']} ({location})")
        lines.append(finding["message"])
        lines.append("action: " + finding["action"])
    lines.append("\n" + payload["disclaimer"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Static leakage, validation, data-usage and reproducibility audit for a generated ML script.")
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--profile", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on blocker findings.")
    args = parser.parse_args()

    if not args.script.exists():
        raise FileNotFoundError(args.script)
    payload = audit_script(args.script, load_profile(args.profile))
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else render_text(payload))
    if args.strict and payload["counts"]["blocker"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
