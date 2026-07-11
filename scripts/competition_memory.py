from __future__ import annotations

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import uuid
from urllib.parse import urlsplit, urlunsplit


STATE_DIR = ".grandmaster"
STATE_FILE = "state.json"
LOCK_FILE = "state.lock"
RUN_ID_ENV = "KAGGLE_GM_RUN_ID"
REPORT_DIR = "experiment_reports"
CURRENT_STATE_SCHEMA = 4


def safe_source_url(value: str) -> str:
    parsed = urlsplit((value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def paths(workspace: Path) -> tuple[Path, Path]:
    root = workspace.resolve() / STATE_DIR
    return root / STATE_FILE, root / LOCK_FILE


def read_state(workspace: Path) -> dict:
    state_path, _ = paths(workspace)
    if not state_path.exists():
        raise FileNotFoundError(f"No competition state at {state_path}. Run init first.")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    version = int(state.get("schema_version") or 1)
    if version > CURRENT_STATE_SCHEMA:
        raise ValueError(
            f"State schema {version} is newer than this Skill supports ({CURRENT_STATE_SCHEMA}); upgrade the Skill first."
        )
    state["schema_version"] = CURRENT_STATE_SCHEMA
    state.setdefault("research_tasks", [])
    state.setdefault("ablation_plan", [])
    state.setdefault("analysis_logs", [])
    state.setdefault("experience_summary", {"status": "not_started"})
    state.setdefault("budget_hours", 24.0)
    state.setdefault("deadline_at", "")
    state.setdefault("stability_policy", {
        "relative_cv_std_threshold": 0.025,
        "absolute_cv_std_threshold": None,
        "minimum_observations": 3,
    })
    return state


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def write_text_atomic(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding=encoding)
    temp.replace(path)


def csv_text(rows: list[dict], fieldnames: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        serialized = {
            key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
            for key, value in row.items()
        }
        writer.writerow(serialized)
    return "\ufeff" + output.getvalue()


def load_code_evidence(paths: list[Path] | None) -> list[dict]:
    output = []
    seen = set()
    for path in paths or []:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("code_evidence") or []
        if not isinstance(payload, list):
            raise ValueError(f"Code evidence file must contain a list: {path}")
        for raw in payload:
            item = dict(raw)
            reference = str(item.get("path") or "").replace("\\", "/")
            excerpt = str(item.get("excerpt") or "")
            if not reference or re.match(r"^(?:[A-Za-z]:|/)", reference) or ".." in Path(reference).parts:
                raise ValueError(f"Unsafe code evidence path in {path.name}")
            expected = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
            if not excerpt or item.get("content_sha256") != expected:
                raise ValueError(f"Missing or stale code evidence hash in {path.name}")
            identity = (reference, item.get("start_line"), item.get("end_line"), expected)
            if identity in seen:
                continue
            seen.add(identity)
            output.append(item)
    return output


def latest_analyses(state: dict) -> dict[str, dict]:
    result = {}
    for analysis in state.get("analysis_logs") or []:
        result[analysis["experiment_id"]] = analysis
    return result


def sync_reports(workspace: Path, state: dict, out_dir: Path | None = None) -> dict:
    root = (out_dir or (workspace.resolve() / REPORT_DIR)).resolve()
    root.mkdir(parents=True, exist_ok=True)
    analyses = latest_analyses(state)

    ablation_fields = [
        "id", "status", "design", "parent_experiment_id", "experiment_id", "component",
        "factor", "control", "treatment", "fixed_conditions", "hypothesis", "expected_signal",
        "primary_metric", "expected_direction", "research_ids", "cost", "decision", "created_at",
    ]
    ablation_rows = [dict(item) for item in state.get("ablation_plan") or []]
    write_text_atomic(root / "ablation_matrix.csv", csv_text(ablation_rows, ablation_fields), encoding="utf-8")

    experiment_fields = [
        "id", "parent_id", "ablation_id", "component", "hypothesis", "change", "status",
        "code_version", "data_version", "config_hash", "environment_hash", "fold_version",
        "metric_version", "seeds", "params",
        "cv_mean", "cv_std", "fold_scores", "slice_metrics", "lb_score", "runtime_minutes",
        "peak_memory_mb", "improved", "delta_from_previous_best", "research_ids",
        "evidence_anchors", "artifact", "diagnosis", "analysis_verdict", "analysis_version", "recorded_at",
    ]
    experiment_rows = []
    for item in state.get("experiments") or []:
        row = dict(item)
        analysis = analyses.get(item["id"]) or {}
        row["analysis_verdict"] = analysis.get("verdict", "pending")
        row["analysis_version"] = analysis.get("version")
        experiment_rows.append(row)
    write_text_atomic(root / "experiment_results.csv", csv_text(experiment_rows, experiment_fields), encoding="utf-8")

    lines = [
        "# Experiment Result Analysis Log",
        "",
        "> Generated from the isolated competition state. Edit the state through the CLI, then regenerate this view.",
        "",
        f"- Competition: `{state.get('competition_slug') or 'unknown'}`",
        f"- Metric: `{state.get('metric') or 'unknown'}` ({state.get('metric_direction') or 'higher'} is better)",
        f"- Updated: {state.get('updated_at') or ''}",
        "",
    ]
    if not state.get("analysis_logs"):
        lines.append("No analyzed experiments yet. Record an experiment, then run `competition_memory.py analyze`.")
    for analysis in state.get("analysis_logs") or []:
        snapshot = analysis.get("snapshot") or {}
        lines += [
            f"## {analysis['experiment_id']} Analysis v{analysis['version']}",
            "",
            f"- Verdict: **{analysis['verdict']}**",
            f"- Parent: `{snapshot.get('parent_id') or 'none'}`",
            f"- CV delta: {snapshot.get('cv_delta')}",
            f"- CV std delta: {snapshot.get('cv_std_delta')}",
            f"- Fold deltas: {snapshot.get('fold_deltas') or []}",
            f"- Directional fold wins: {snapshot.get('fold_wins')} / {snapshot.get('fold_count')}",
            f"- Slice deltas: {snapshot.get('slice_deltas') or {}}",
            f"- Runtime delta (min): {snapshot.get('runtime_minutes_delta')}",
            f"- Peak memory delta (MB): {snapshot.get('peak_memory_mb_delta')}",
            f"- Mechanism: {analysis.get('mechanism') or 'not resolved'}",
            f"- Confounders: {' | '.join(analysis.get('confounders') or []) or 'none recorded'}",
            f"- Slice findings: {' | '.join(analysis.get('slice_findings') or []) or 'none recorded'}",
            f"- Resource tradeoff: {analysis.get('resource_tradeoff') or 'none recorded'}",
            f"- Next action: {analysis.get('next_action') or 'not set'}",
            f"- Notes: {analysis.get('notes') or ''}",
            "",
        ]
    write_text_atomic(root / "experiment_analysis_log.md", "\n".join(lines).rstrip() + "\n")
    return {
        "report_dir": root.name,
        "files": ["ablation_matrix.csv", "experiment_results.csv", "experiment_analysis_log.md"],
    }


def persist_state(workspace: Path, state: dict) -> None:
    state_path, _ = paths(workspace)
    write_atomic(state_path, state)
    sync_reports(workspace, state)


@contextmanager
def state_lock(workspace: Path, timeout: float = 10.0):
    _, lock_path = paths(workspace)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    descriptor = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, f"pid={os.getpid()} time={utc_now()}".encode("utf-8"))
        except FileExistsError:
            if lock_path.exists() and time.time() - lock_path.stat().st_mtime > 300:
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"State is locked by another process: {lock_path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def supplied_run_id(args: argparse.Namespace) -> str:
    return (getattr(args, "run_id", "") or os.environ.get(RUN_ID_ENV, "")).strip()


def assert_owner(state: dict, args: argparse.Namespace) -> None:
    supplied = supplied_run_id(args)
    expected = state.get("run_id") or ""
    if not supplied:
        raise PermissionError(
            f"Mutation requires --run-id or {RUN_ID_ENV}. This prevents two agent windows from sharing state."
        )
    if supplied != expected:
        raise PermissionError("run_id mismatch: this workspace belongs to another agent run.")


def init_state(args: argparse.Namespace) -> dict:
    workspace = args.workspace.resolve()
    state_path, _ = paths(workspace)
    if state_path.exists() and not args.force:
        raise FileExistsError(f"State already exists: {state_path}. Use a separate workspace or --force intentionally.")
    if state_path.exists() and args.force:
        backup = state_path.with_name(f"state.backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        backup.write_bytes(state_path.read_bytes())
    run_id = args.run_id or str(uuid.uuid4())
    budget_hours = float(args.budget_hours)
    if budget_hours <= 0:
        raise ValueError("--budget-hours must be positive.")
    deadline_at = getattr(args, "deadline", "") or ""
    if deadline_at:
        try:
            datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("--deadline must be an ISO-8601 timestamp.") from error
    relative_threshold = float(getattr(args, "relative_cv_std_threshold", 0.025))
    minimum_observations = int(getattr(args, "minimum_stability_observations", 3))
    if relative_threshold <= 0 or minimum_observations < 2:
        raise ValueError("Stability thresholds must be positive and use at least two observations.")
    state = {
        "schema_version": CURRENT_STATE_SCHEMA,
        "run_id": run_id,
        "competition_slug": args.slug,
        "metric": args.metric,
        "metric_direction": args.metric_direction,
        "stage": "intake",
        "status": "active",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "budget_hours": budget_hours,
        "deadline_at": deadline_at,
        "stability_policy": {
            "relative_cv_std_threshold": relative_threshold,
            "absolute_cv_std_threshold": getattr(args, "absolute_cv_std_threshold", None),
            "minimum_observations": minimum_observations,
        },
        "validation_verified": False,
        "baseline_established": False,
        "best_experiment_id": None,
        "best_cv": None,
        "best_lb": None,
        "experiments": [],
        "research_tasks": [],
        "ablation_plan": [],
        "analysis_logs": [],
        "experience_summary": {"status": "not_started"},
        "lessons": [],
    }
    persist_state(workspace, state)
    return state


def better(candidate: float, incumbent: float | None, direction: str, min_delta: float) -> bool:
    if incumbent is None:
        return True
    if direction == "lower":
        return candidate < incumbent - min_delta
    return candidate > incumbent + min_delta


def record_experiment(args: argparse.Namespace) -> dict:
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        if args.runtime_minutes is not None and args.runtime_minutes < 0:
            raise ValueError("runtime_minutes cannot be negative")
        if any(item["id"] == args.id for item in state["experiments"]):
            raise ValueError(f"Experiment id already exists: {args.id}")
        research_ids = list(dict.fromkeys(getattr(args, "research_id", []) or []))
        parent_id = args.parent_id or state.get("best_experiment_id")
        ablation_id = (getattr(args, "ablation_id", "") or "").strip()
        ablation = None
        if ablation_id:
            ablation = find_ablation(state, ablation_id)
            if ablation.get("status") not in {"planned", "running"}:
                raise ValueError(f"Ablation {ablation_id} is already {ablation.get('status')}.")
            planned_parent = ablation.get("parent_experiment_id")
            if planned_parent and parent_id != planned_parent:
                raise ValueError(
                    f"Experiment parent {parent_id!r} does not match ablation control {planned_parent!r}."
                )
            research_ids = list(dict.fromkeys(research_ids + (ablation.get("research_ids") or [])))
        require_verified_research(state, research_ids)
        incumbent = state.get("best_cv")
        improved = False
        delta = None
        if args.cv_mean is not None and args.status == "success":
            improved = better(args.cv_mean, incumbent, state["metric_direction"], args.min_delta)
            if incumbent is not None:
                delta = args.cv_mean - incumbent
        experiment = {
            "id": args.id,
            "parent_id": parent_id,
            "ablation_id": ablation_id or None,
            "component": args.component,
            "hypothesis": args.hypothesis,
            "change": args.change,
            "evidence_anchors": args.evidence_anchor or [],
            "research_ids": research_ids,
            "status": args.status,
            "code_version": getattr(args, "code_version", ""),
            "data_version": getattr(args, "data_version", ""),
            "config_hash": getattr(args, "config_hash", ""),
            "environment_hash": getattr(args, "environment_hash", ""),
            "fold_version": getattr(args, "fold_version", ""),
            "metric_version": getattr(args, "metric_version", ""),
            "seeds": getattr(args, "seeds", []) or [],
            "params": getattr(args, "params", {}) or {},
            "cv_mean": args.cv_mean,
            "cv_std": args.cv_std,
            "fold_scores": args.fold_scores,
            "slice_metrics": args.slice_metrics,
            "lb_score": args.lb_score,
            "runtime_minutes": args.runtime_minutes,
            "peak_memory_mb": args.peak_memory_mb,
            "artifact": args.artifact,
            "code_evidence": load_code_evidence(getattr(args, "code_evidence_file", []) or []),
            "notes": args.notes,
            "diagnosis": args.diagnosis,
            "analysis_status": "pending",
            "improved": improved,
            "delta_from_previous_best": delta,
            "recorded_at": utc_now(),
        }
        state["experiments"].append(experiment)
        if ablation is not None:
            ablation["experiment_id"] = args.id
            ablation["status"] = {
                "running": "running",
                "success": "completed",
                "failed": "failed",
                "discarded": "discarded",
            }[args.status]
        if args.component == "validation" and args.status == "success":
            state["validation_verified"] = True
        if args.component == "baseline" and args.status == "success":
            state["baseline_established"] = True
        if improved:
            state["best_experiment_id"] = args.id
            state["best_cv"] = args.cv_mean
            if args.lb_score is not None:
                state["best_lb"] = args.lb_score
        state["stage"] = infer_stage(state)
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return experiment


def finalize_experiment(args: argparse.Namespace) -> dict:
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        experiment = find_experiment(state, args.id)
        if args.runtime_minutes is not None and args.runtime_minutes < 0:
            raise ValueError("runtime_minutes cannot be negative")
        if experiment.get("status") != "running":
            raise ValueError(f"Experiment {args.id} is not running.")
        incumbent = state.get("best_cv")
        improved = False
        delta = None
        if args.cv_mean is not None and args.status == "success":
            improved = better(args.cv_mean, incumbent, state["metric_direction"], args.min_delta)
            if incumbent is not None:
                delta = args.cv_mean - incumbent
        result_fields = {
            "status": args.status,
            "cv_mean": args.cv_mean,
            "cv_std": args.cv_std,
            "fold_scores": args.fold_scores,
            "slice_metrics": args.slice_metrics,
            "lb_score": args.lb_score,
            "runtime_minutes": args.runtime_minutes,
            "peak_memory_mb": args.peak_memory_mb,
            "artifact": args.artifact,
            "notes": args.notes,
            "diagnosis": args.diagnosis,
            "improved": improved,
            "delta_from_previous_best": delta,
            "completed_at": utc_now(),
        }
        for key in (
            "code_version", "data_version", "config_hash", "environment_hash", "fold_version", "metric_version"
        ):
            value = getattr(args, key, "")
            if value:
                result_fields[key] = value
        if args.seeds is not None:
            result_fields["seeds"] = args.seeds
        if args.params is not None:
            result_fields["params"] = args.params
        if getattr(args, "code_evidence_file", None) is not None:
            result_fields["code_evidence"] = load_code_evidence(args.code_evidence_file)
        experiment.update(result_fields)
        if experiment.get("ablation_id"):
            ablation = find_ablation(state, experiment["ablation_id"])
            ablation["status"] = {
                "success": "completed",
                "failed": "failed",
                "discarded": "discarded",
            }[args.status]
        if experiment.get("component") == "validation" and args.status == "success":
            state["validation_verified"] = True
        if experiment.get("component") == "baseline" and args.status == "success":
            state["baseline_established"] = True
        if improved:
            state["best_experiment_id"] = experiment["id"]
            state["best_cv"] = args.cv_mean
            if args.lb_score is not None:
                state["best_lb"] = args.lb_score
        state["stage"] = infer_stage(state)
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return experiment


def infer_stage(state: dict) -> str:
    if not state.get("validation_verified"):
        return "validation"
    if not state.get("baseline_established"):
        return "baseline"
    successes = [item for item in state["experiments"] if item["status"] == "success"]
    if len(successes) < 4:
        return "improve"
    if plateau_count(state) >= 3:
        return "explore"
    return "improve"


def plateau_count(state: dict) -> int:
    count = 0
    for item in reversed(state.get("experiments") or []):
        if item.get("status") != "success":
            continue
        if item.get("improved"):
            break
        count += 1
    return count


def budget_status(state: dict) -> dict:
    total_minutes = max(0.0, float(state.get("budget_hours") or 0.0) * 60.0)
    consumed_minutes = sum(
        max(0.0, float(item.get("runtime_minutes") or 0.0))
        for item in state.get("experiments") or []
        if item.get("status") in {"success", "failed", "discarded"}
    )
    remaining_minutes = max(0.0, total_minutes - consumed_minutes)
    deadline_at = state.get("deadline_at") or ""
    deadline_expired = False
    deadline_remaining_minutes = None
    if deadline_at:
        try:
            deadline = datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            deadline_remaining_minutes = (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 60.0
            deadline_expired = deadline_remaining_minutes <= 0
        except ValueError:
            deadline_expired = True
    exhausted = total_minutes > 0 and remaining_minutes <= 0
    low = total_minutes > 0 and not exhausted and remaining_minutes / total_minutes <= 0.1
    return {
        "total_minutes": round(total_minutes, 3),
        "consumed_minutes": round(consumed_minutes, 3),
        "remaining_minutes": round(remaining_minutes, 3),
        "remaining_fraction": round(remaining_minutes / total_minutes, 4) if total_minutes else None,
        "deadline_at": deadline_at,
        "deadline_remaining_minutes": round(deadline_remaining_minutes, 3) if deadline_remaining_minutes is not None else None,
        "deadline_expired": deadline_expired,
        "exhausted": exhausted,
        "low": low,
    }


def stability_diagnostic(state: dict, experiment: dict) -> dict:
    cv_std = experiment.get("cv_std")
    cv_mean = experiment.get("cv_mean")
    observations = max(len(experiment.get("fold_scores") or []), len(experiment.get("seeds") or []))
    policy = state.get("stability_policy") or {}
    minimum = int(policy.get("minimum_observations") or 3)
    if cv_std is None or cv_mean is None or observations < minimum:
        return {
            "unstable": False,
            "reason": "insufficient_observations" if observations < minimum else "missing_mean_or_std",
            "observations": observations,
        }
    absolute_threshold = policy.get("absolute_cv_std_threshold")
    relative_threshold = float(policy.get("relative_cv_std_threshold") or 0.025)
    relative_std = abs(float(cv_std)) / max(abs(float(cv_mean)), 1e-12)
    unstable = (
        abs(float(cv_std)) > float(absolute_threshold)
        if absolute_threshold is not None
        else relative_std > relative_threshold
    )
    return {
        "unstable": unstable,
        "cv_std": float(cv_std),
        "relative_std": round(relative_std, 6),
        "relative_threshold": relative_threshold,
        "absolute_threshold": absolute_threshold,
        "observations": observations,
    }


def next_action(state: dict) -> dict:
    experiments = state.get("experiments") or []
    experience_status = (state.get("experience_summary") or {}).get("status", "not_started")
    if state.get("status") == "postmortem":
        mode = "review_experience" if experience_status == "draft" else "promote_experience"
        return {
            "mode": mode,
            "reason": f"Post-competition experience is {experience_status}; finish the review and knowledge-base gate.",
            "branch": (state.get("experience_summary") or {}).get("card_id", "postmortem"),
        }
    if state.get("status") == "complete":
        return {
            "mode": "complete",
            "reason": "The reviewed post-competition experience has been promoted to long-term memory.",
            "branch": (state.get("experience_summary") or {}).get("catalog_anchor", "complete"),
        }
    budget = budget_status(state)
    if budget["deadline_expired"] or budget["exhausted"]:
        return {
            "mode": "finalize_with_current_best",
            "reason": "The execution deadline or recorded compute budget is exhausted; stop branching and package the best reproducible result.",
            "branch": state.get("best_experiment_id") or "root",
            "budget": budget,
        }
    if not state.get("validation_verified"):
        return {"mode": "validation", "reason": "Validation gates are not verified.", "branch": "root"}
    if not state.get("baseline_established"):
        return {"mode": "baseline", "reason": "No reproducible baseline is recorded.", "branch": "root"}
    if experiments and experiments[-1]["status"] == "failed":
        return {
            "mode": "debug",
            "reason": "The last experiment failed; diagnose the traceback or invariant before branching.",
            "branch": experiments[-1]["id"],
        }
    pending_research = [item for item in state.get("research_tasks") or [] if item.get("status") == "pending"]
    if pending_research:
        return {
            "mode": "source_competition_deep_dive",
            "reason": f"{len(pending_research)} retrieved knowledge points still require source-competition verification.",
            "branch": pending_research[0]["id"],
        }
    latest = experiments[-1] if experiments else None
    if (
        latest
        and latest.get("status") == "success"
        and latest.get("component") not in {"validation", "baseline"}
        and latest.get("analysis_status") != "complete"
    ):
        return {
            "mode": "analyze_experiment",
            "reason": "The latest successful diagnostic experiment has no standardized result analysis.",
            "branch": latest["id"],
        }
    successful = [item for item in experiments if item["status"] == "success"]
    stability = stability_diagnostic(state, successful[-1]) if successful else {"unstable": False}
    if stability["unstable"]:
        return {
            "mode": "stabilize_validation",
            "reason": "Metric-scale-aware fold or seed variation is high; investigate groups, seeds, leakage and stratification.",
            "branch": successful[-1]["id"],
            "stability": stability,
        }
    planned_ablations = [item for item in state.get("ablation_plan") or [] if item.get("status") == "planned"]
    if planned_ablations:
        return {
            "mode": "run_planned_ablation",
            "reason": "A registered ablation is ready and has explicit control, treatment and fixed conditions.",
            "branch": planned_ablations[0]["id"],
        }
    if budget["low"]:
        return {
            "mode": "budget_constrained_refinement",
            "reason": "Less than 10% of the recorded execution budget remains; allow only a cheap decisive check or finalize.",
            "branch": state.get("best_experiment_id") or "root",
            "budget": budget,
        }
    if plateau_count(state) >= 3:
        return {
            "mode": "cross_branch_exploration",
            "reason": "Three successful experiments failed to improve the best score; retrieve a different component or model family.",
            "branch": state.get("best_experiment_id"),
        }
    if successful and successful[-1].get("improved"):
        return {
            "mode": "targeted_refinement",
            "reason": "The last isolated change improved CV; refine or ablate the same component once before moving on.",
            "branch": successful[-1]["id"],
        }
    return {
        "mode": "next_high_information_experiment",
        "reason": "Choose the cheapest experiment that distinguishes between the leading hypotheses.",
        "branch": state.get("best_experiment_id"),
    }


def state_summary(state: dict) -> dict:
    status_counts = {}
    for item in state.get("experiments") or []:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    research_counts = {}
    for item in state.get("research_tasks") or []:
        research_counts[item["status"]] = research_counts.get(item["status"], 0) + 1
    ablation_counts = {}
    for item in state.get("ablation_plan") or []:
        ablation_counts[item["status"]] = ablation_counts.get(item["status"], 0) + 1
    return {
        "competition_slug": state.get("competition_slug"),
        "stage": state.get("stage"),
        "status": state.get("status"),
        "validation_verified": state.get("validation_verified"),
        "baseline_established": state.get("baseline_established"),
        "best_experiment_id": state.get("best_experiment_id"),
        "best_cv": state.get("best_cv"),
        "best_lb": state.get("best_lb"),
        "experiment_count": len(state.get("experiments") or []),
        "experiment_status": status_counts,
        "research_task_count": len(state.get("research_tasks") or []),
        "research_status": research_counts,
        "ablation_count": len(state.get("ablation_plan") or []),
        "ablation_status": ablation_counts,
        "analysis_log_count": len(state.get("analysis_logs") or []),
        "analysis_pending": sum(
            1
            for item in state.get("experiments") or []
            if item.get("component") not in {"validation", "baseline"}
            and item.get("status") == "success"
            and item.get("analysis_status") != "complete"
        ),
        "experience_status": (state.get("experience_summary") or {}).get("status", "not_started"),
        "budget": budget_status(state),
        "plateau_count": plateau_count(state),
        "next_action": next_action(state),
        "updated_at": state.get("updated_at"),
    }


def find_experiment(state: dict, experiment_id: str) -> dict:
    for experiment in state.get("experiments") or []:
        if experiment.get("id") == experiment_id:
            return experiment
    raise KeyError(f"Unknown experiment id: {experiment_id}")


def find_research_task(state: dict, research_id: str) -> dict:
    for task in state.get("research_tasks") or []:
        if task.get("id") == research_id:
            return task
    raise KeyError(f"Unknown research id: {research_id}")


def find_ablation(state: dict, ablation_id: str) -> dict:
    for ablation in state.get("ablation_plan") or []:
        if ablation.get("id") == ablation_id:
            return ablation
    raise KeyError(f"Unknown ablation id: {ablation_id}")


def require_verified_research(state: dict, research_ids: list[str]) -> None:
    for research_id in research_ids:
        task = find_research_task(state, research_id)
        if task.get("status") != "verified":
            raise ValueError(f"Research task {research_id} is not verified.")


def plan_ablation(args: argparse.Namespace) -> dict:
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        plan = state.setdefault("ablation_plan", [])
        if any(item.get("id") == args.id for item in plan):
            raise ValueError(f"Ablation id already exists: {args.id}")
        if args.parent_experiment:
            find_experiment(state, args.parent_experiment)
        research_ids = list(dict.fromkeys(args.research_id or []))
        require_verified_research(state, research_ids)
        ablation = {
            "id": args.id,
            "status": "planned",
            "design": args.design,
            "parent_experiment_id": args.parent_experiment or state.get("best_experiment_id"),
            "experiment_id": None,
            "component": args.component,
            "factor": args.factor,
            "control": args.control,
            "treatment": args.treatment,
            "fixed_conditions": list(dict.fromkeys(args.fixed_condition or [])),
            "hypothesis": args.hypothesis,
            "expected_signal": args.expected_signal,
            "primary_metric": args.primary_metric or state.get("metric"),
            "expected_direction": args.expected_direction or state.get("metric_direction"),
            "research_ids": research_ids,
            "cost": args.cost,
            "decision": "pending",
            "created_at": utc_now(),
        }
        plan.append(ablation)
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return ablation


def analysis_snapshot(state: dict, experiment: dict, parent: dict | None) -> dict:
    parent = parent or {}
    left_folds = parent.get("fold_scores") or []
    right_folds = experiment.get("fold_scores") or []
    fold_deltas = []
    if left_folds and len(left_folds) == len(right_folds):
        fold_deltas = [right - left for left, right in zip(left_folds, right_folds)]
    direction = state.get("metric_direction") or "higher"
    oriented = fold_deltas if direction == "higher" else [-value for value in fold_deltas]
    slice_deltas = {}
    for key in sorted(set(parent.get("slice_metrics") or {}) & set(experiment.get("slice_metrics") or {})):
        left = parent["slice_metrics"][key]
        right = experiment["slice_metrics"][key]
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            slice_deltas[key] = right - left
    return {
        "parent_id": parent.get("id"),
        "cv_delta": numeric_delta(parent, experiment, "cv_mean"),
        "cv_std_delta": numeric_delta(parent, experiment, "cv_std"),
        "lb_delta": numeric_delta(parent, experiment, "lb_score"),
        "runtime_minutes_delta": numeric_delta(parent, experiment, "runtime_minutes"),
        "peak_memory_mb_delta": numeric_delta(parent, experiment, "peak_memory_mb"),
        "fold_deltas": fold_deltas,
        "fold_count": len(fold_deltas),
        "fold_wins": sum(1 for value in oriented if value > 0),
        "fold_ties": sum(1 for value in oriented if value == 0),
        "slice_deltas": slice_deltas,
    }


def analyze_experiment(args: argparse.Namespace) -> dict:
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        experiment = find_experiment(state, args.id)
        parent = find_experiment(state, experiment["parent_id"]) if experiment.get("parent_id") else None
        previous = [item for item in state.get("analysis_logs") or [] if item.get("experiment_id") == args.id]
        analysis = {
            "experiment_id": args.id,
            "version": len(previous) + 1,
            "verdict": args.verdict,
            "snapshot": analysis_snapshot(state, experiment, parent),
            "mechanism": args.mechanism,
            "confounders": list(dict.fromkeys(args.confounder or [])),
            "slice_findings": list(dict.fromkeys(args.slice_finding or [])),
            "resource_tradeoff": args.resource_tradeoff,
            "next_action": args.next_action,
            "notes": args.notes,
            "analyzed_at": utc_now(),
        }
        state.setdefault("analysis_logs", []).append(analysis)
        experiment["analysis_status"] = "complete"
        experiment["analysis_version"] = analysis["version"]
        if experiment.get("ablation_id"):
            ablation = find_ablation(state, experiment["ablation_id"])
            ablation["decision"] = args.verdict
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return analysis


def research_identity(source_slug: str, claim: str, anchor: str | None) -> str:
    normalized_claim = re.sub(r"\s+", " ", (claim or "").strip().lower())
    return "|".join((source_slug.strip().lower(), normalized_claim, (anchor or "").strip().lower()))


def import_research_tasks(args: argparse.Namespace) -> dict:
    payload = json.loads(args.brief.read_text(encoding="utf-8"))
    dossiers = payload.get("competition_deep_dives") or []
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        tasks = state.setdefault("research_tasks", [])
        existing = {
            research_identity(item.get("source_competition", ""), item.get("knowledge_point", ""), item.get("evidence_anchor"))
            for item in tasks
        }
        imported = []
        skipped = 0
        for dossier in dossiers:
            source_slug = dossier.get("competition_slug") or ""
            for point in dossier.get("knowledge_points") or []:
                identity = research_identity(source_slug, point.get("claim", ""), point.get("source_anchor"))
                if identity in existing:
                    skipped += 1
                    continue
                task = {
                    "id": f"R{len(tasks) + 1:03d}",
                    "status": "pending",
                    "source_competition": source_slug,
                    "official_url": dossier.get("official_url"),
                    "knowledge_point": point.get("claim"),
                    "evidence_anchor": point.get("source_anchor"),
                    "source": point.get("source"),
                    "source_url": point.get("source_url"),
                    "verification_queries": point.get("verification_queries") or [],
                    "required_questions": dossier.get("required_questions") or [],
                    "requirements": dossier.get("requirements") or {},
                    "created_at": utc_now(),
                }
                tasks.append(task)
                imported.append(task["id"])
                existing.add(identity)
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return {"imported": imported, "skipped_existing": skipped, "research_status": state_summary(state)["research_status"]}


def resolve_research_task(args: argparse.Namespace) -> dict:
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        task = find_research_task(state, args.id)
        if task.get("status") != "pending":
            raise ValueError(f"Research task {args.id} is already {task.get('status')}.")
        source_records = [dict(item) for item in (getattr(args, "source_record", []) or [])]
        for url in getattr(args, "source_url", []) or []:
            source_records.append({"url": url, "source_type": "unspecified"})
        for path in getattr(args, "source_file", []) or []:
            content = path.read_bytes()
            source_records.append({
                "snapshot_file": path.name,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "source_type": "local_snapshot",
            })
        normalized_records = []
        seen_records = set()
        for record in source_records:
            normalized = dict(record)
            if normalized.get("url"):
                normalized["url"] = safe_source_url(str(normalized["url"]))
                if not normalized["url"]:
                    raise ValueError("Research source URLs must be public HTTP(S) URLs without credentials or query tokens.")
            identity = (
                normalized.get("url") or "",
                normalized.get("content_sha256") or "",
                normalized.get("commit") or "",
            )
            if identity in seen_records:
                continue
            seen_records.add(identity)
            normalized["checked_at"] = utc_now()
            normalized_records.append(normalized)
        source_urls = list(dict.fromkeys(item.get("url") for item in normalized_records if item.get("url")))
        requirements = task.get("requirements") or {}
        if args.status == "verified":
            if not source_urls:
                raise ValueError("Verified research requires at least one public source URL.")
            if requirements.get("multiple_sources") and len(source_urls) < 2 and not getattr(args, "allow_single_source", False):
                raise ValueError("This research task requires at least two independent source URLs.")
            if requirements.get("official_page") and not getattr(args, "official_checked", False):
                raise ValueError("This research task requires an explicit --official-checked confirmation.")
            if not args.transfer_conditions.strip() or not args.failure_conditions.strip():
                raise ValueError("Verified research requires explicit transfer and failure conditions.")
            if not args.implementation_evidence.strip():
                raise ValueError("Verified research requires implementation evidence from code or the source description.")
            immutable = any(item.get("content_sha256") or item.get("commit") for item in normalized_records)
            if not immutable:
                raise ValueError("Verified research requires at least one content hash or immutable source commit.")
        task.update({
            "status": args.status,
            "source_urls_checked": source_urls,
            "source_records": normalized_records,
            "official_checked": bool(getattr(args, "official_checked", False)),
            "provenance_status": "verified" if args.status == "verified" else args.status,
            "conclusion": args.conclusion,
            "transfer_conditions": args.transfer_conditions,
            "failure_conditions": args.failure_conditions,
            "implementation_evidence": args.implementation_evidence,
            "notes": args.notes,
            "resolved_at": utc_now(),
        })
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return task


def numeric_delta(parent: dict, child: dict, field: str) -> float | None:
    left = parent.get(field)
    right = child.get(field)
    if left is None or right is None:
        return None
    return right - left


def compare_experiments(state: dict, parent_id: str, child_id: str) -> dict:
    parent = find_experiment(state, parent_id)
    child = find_experiment(state, child_id)
    return {
        "parent_id": parent_id,
        "child_id": child_id,
        "component": child.get("component"),
        "hypothesis": child.get("hypothesis"),
        "change": child.get("change"),
        "cv_delta": numeric_delta(parent, child, "cv_mean"),
        "cv_std_delta": numeric_delta(parent, child, "cv_std"),
        "lb_delta": numeric_delta(parent, child, "lb_score"),
        "runtime_minutes_delta": numeric_delta(parent, child, "runtime_minutes"),
        "peak_memory_mb_delta": numeric_delta(parent, child, "peak_memory_mb"),
        "parent_fold_scores": parent.get("fold_scores") or [],
        "child_fold_scores": child.get("fold_scores") or [],
        "parent_slice_metrics": parent.get("slice_metrics") or {},
        "child_slice_metrics": child.get("slice_metrics") or {},
        "diagnosis": child.get("diagnosis") or "",
        "reflection_questions": [
            "Did the diagnostic predicted by the hypothesis move?",
            "Is the mean change consistent across folds and important slices?",
            "Did runtime, memory, calibration or robustness regress?",
            "What mechanism is supported, falsified or still confounded?",
        ],
    }


def parse_float_list(value: str) -> list[float]:
    if not value.strip():
        return []
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def parse_int_list(value: str) -> list[int]:
    if not value.strip():
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def parse_json_object(value: str) -> dict:
    payload = json.loads(value) if value.strip() else {}
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("Expected a JSON object.")
    return payload


def print_payload(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}: " + ", ".join(f"{name}={item}" for name, item in value.items()))
        else:
            print(f"{key}: {value}")


def add_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--workspace", type=Path, required=True)
    subparser.add_argument("--json", action="store_true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated competition memory and experiment ledger.")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init")
    add_common(init_parser)
    init_parser.add_argument("--slug", required=True)
    init_parser.add_argument("--metric", default="")
    init_parser.add_argument("--metric-direction", choices=("higher", "lower"), default="higher")
    init_parser.add_argument("--budget-hours", type=float, default=24.0)
    init_parser.add_argument("--deadline", default="", help="Optional ISO-8601 competition or execution deadline.")
    init_parser.add_argument("--relative-cv-std-threshold", type=float, default=0.025)
    init_parser.add_argument("--absolute-cv-std-threshold", type=float, default=None)
    init_parser.add_argument("--minimum-stability-observations", type=int, default=3)
    init_parser.add_argument("--run-id", default="")
    init_parser.add_argument("--force", action="store_true")

    record_parser = commands.add_parser("record")
    add_common(record_parser)
    record_parser.add_argument("--run-id", default="")
    record_parser.add_argument("--id", required=True)
    record_parser.add_argument("--parent-id", default="")
    record_parser.add_argument("--component", required=True)
    record_parser.add_argument("--hypothesis", required=True)
    record_parser.add_argument("--change", default="")
    record_parser.add_argument("--evidence-anchor", action="append", default=[])
    record_parser.add_argument("--research-id", action="append", default=[])
    record_parser.add_argument("--ablation-id", default="")
    record_parser.add_argument("--status", choices=("success", "failed", "discarded", "running"), required=True)
    record_parser.add_argument("--code-version", default="", help="Git commit or immutable source snapshot id.")
    record_parser.add_argument("--data-version", default="", help="Dataset manifest/hash/version.")
    record_parser.add_argument("--config-hash", default="")
    record_parser.add_argument("--environment-hash", default="", help="Lockfile/container/environment fingerprint.")
    record_parser.add_argument("--fold-version", default="")
    record_parser.add_argument("--metric-version", default="")
    record_parser.add_argument("--seeds", type=parse_int_list, default=[])
    record_parser.add_argument("--params", type=parse_json_object, default={})
    record_parser.add_argument("--cv-mean", type=float, default=None)
    record_parser.add_argument("--cv-std", type=float, default=None)
    record_parser.add_argument("--fold-scores", type=parse_float_list, default=[])
    record_parser.add_argument("--slice-metrics", type=parse_json_object, default={})
    record_parser.add_argument("--lb-score", type=float, default=None)
    record_parser.add_argument("--runtime-minutes", type=float, default=None)
    record_parser.add_argument("--peak-memory-mb", type=float, default=None)
    record_parser.add_argument("--artifact", default="")
    record_parser.add_argument("--code-evidence-file", type=Path, action="append", default=[])
    record_parser.add_argument("--notes", default="")
    record_parser.add_argument("--diagnosis", default="")
    record_parser.add_argument("--min-delta", type=float, default=1e-6)

    finalize_parser = commands.add_parser("finalize")
    add_common(finalize_parser)
    finalize_parser.add_argument("--run-id", default="")
    finalize_parser.add_argument("--id", required=True)
    finalize_parser.add_argument("--status", choices=("success", "failed", "discarded"), required=True)
    finalize_parser.add_argument("--cv-mean", type=float, default=None)
    finalize_parser.add_argument("--cv-std", type=float, default=None)
    finalize_parser.add_argument("--fold-scores", type=parse_float_list, default=[])
    finalize_parser.add_argument("--slice-metrics", type=parse_json_object, default={})
    finalize_parser.add_argument("--lb-score", type=float, default=None)
    finalize_parser.add_argument("--runtime-minutes", type=float, default=None)
    finalize_parser.add_argument("--peak-memory-mb", type=float, default=None)
    finalize_parser.add_argument("--artifact", default="")
    finalize_parser.add_argument("--code-evidence-file", type=Path, action="append", default=None)
    finalize_parser.add_argument("--notes", default="")
    finalize_parser.add_argument("--diagnosis", default="")
    finalize_parser.add_argument("--code-version", default="")
    finalize_parser.add_argument("--data-version", default="")
    finalize_parser.add_argument("--config-hash", default="")
    finalize_parser.add_argument("--environment-hash", default="")
    finalize_parser.add_argument("--fold-version", default="")
    finalize_parser.add_argument("--metric-version", default="")
    finalize_parser.add_argument("--seeds", type=parse_int_list, default=None)
    finalize_parser.add_argument("--params", type=parse_json_object, default=None)
    finalize_parser.add_argument("--min-delta", type=float, default=1e-6)

    status_parser = commands.add_parser("status")
    add_common(status_parser)
    next_parser = commands.add_parser("next")
    add_common(next_parser)
    compare_parser = commands.add_parser("compare")
    add_common(compare_parser)
    compare_parser.add_argument("--parent", required=True)
    compare_parser.add_argument("--child", required=True)

    import_research_parser = commands.add_parser("import-research")
    add_common(import_research_parser)
    import_research_parser.add_argument("--run-id", default="")
    import_research_parser.add_argument("--brief", type=Path, required=True)

    resolve_research_parser = commands.add_parser("resolve-research")
    add_common(resolve_research_parser)
    resolve_research_parser.add_argument("--run-id", default="")
    resolve_research_parser.add_argument("--id", required=True)
    resolve_research_parser.add_argument("--status", choices=("verified", "rejected", "uncertain"), required=True)
    resolve_research_parser.add_argument("--source-url", action="append", default=[])
    resolve_research_parser.add_argument("--source-record", type=parse_json_object, action="append", default=[])
    resolve_research_parser.add_argument("--source-file", type=Path, action="append", default=[])
    resolve_research_parser.add_argument("--official-checked", action="store_true")
    resolve_research_parser.add_argument("--allow-single-source", action="store_true")
    resolve_research_parser.add_argument("--conclusion", required=True)
    resolve_research_parser.add_argument("--transfer-conditions", default="")
    resolve_research_parser.add_argument("--failure-conditions", default="")
    resolve_research_parser.add_argument("--implementation-evidence", default="")
    resolve_research_parser.add_argument("--notes", default="")

    research_status_parser = commands.add_parser("research-status")
    add_common(research_status_parser)

    plan_ablation_parser = commands.add_parser("plan-ablation")
    add_common(plan_ablation_parser)
    plan_ablation_parser.add_argument("--run-id", default="")
    plan_ablation_parser.add_argument("--id", required=True)
    plan_ablation_parser.add_argument(
        "--design",
        choices=("ofat", "factorial", "negative_control", "sensitivity"),
        default="ofat",
    )
    plan_ablation_parser.add_argument("--parent-experiment", default="")
    plan_ablation_parser.add_argument("--component", required=True)
    plan_ablation_parser.add_argument("--factor", required=True)
    plan_ablation_parser.add_argument("--control", required=True)
    plan_ablation_parser.add_argument("--treatment", required=True)
    plan_ablation_parser.add_argument("--fixed-condition", action="append", default=[])
    plan_ablation_parser.add_argument("--hypothesis", required=True)
    plan_ablation_parser.add_argument("--expected-signal", required=True)
    plan_ablation_parser.add_argument("--primary-metric", default="")
    plan_ablation_parser.add_argument("--expected-direction", choices=("higher", "lower"), default=None)
    plan_ablation_parser.add_argument("--research-id", action="append", default=[])
    plan_ablation_parser.add_argument("--cost", choices=("low", "medium", "high"), default="low")

    analyze_parser = commands.add_parser("analyze")
    add_common(analyze_parser)
    analyze_parser.add_argument("--run-id", default="")
    analyze_parser.add_argument("--id", required=True)
    analyze_parser.add_argument(
        "--verdict",
        choices=("supported", "partially_supported", "not_supported", "inconclusive"),
        required=True,
    )
    analyze_parser.add_argument("--mechanism", required=True)
    analyze_parser.add_argument("--confounder", action="append", default=[])
    analyze_parser.add_argument("--slice-finding", action="append", default=[])
    analyze_parser.add_argument("--resource-tradeoff", default="")
    analyze_parser.add_argument("--next-action", required=True)
    analyze_parser.add_argument("--notes", default="")

    export_parser = commands.add_parser("export-reports")
    add_common(export_parser)
    export_parser.add_argument("--out-dir", type=Path, default=None)

    args = parser.parse_args()
    if args.command == "init":
        state = init_state(args)
        payload = state_summary(state)
        payload["run_id"] = state["run_id"]
        payload["powershell"] = f"$env:{RUN_ID_ENV} = '{state['run_id']}'"
        payload["shell_exports"] = {
            "powershell": payload["powershell"],
            "bash_zsh": f"export {RUN_ID_ENV}='{state['run_id']}'",
            "cmd": f"set {RUN_ID_ENV}={state['run_id']}",
        }
        payload["stateless_shell"] = f"Pass --run-id {state['run_id']} on every mutating command."
    elif args.command == "record":
        experiment = record_experiment(args)
        state = read_state(args.workspace)
        payload = {"recorded": experiment, "state": state_summary(state)}
    elif args.command == "finalize":
        experiment = finalize_experiment(args)
        payload = {"finalized": experiment, "state": state_summary(read_state(args.workspace))}
    elif args.command == "import-research":
        payload = import_research_tasks(args)
    elif args.command == "resolve-research":
        payload = resolve_research_task(args)
    elif args.command == "research-status":
        state = read_state(args.workspace)
        payload = {
            "research_tasks": state.get("research_tasks") or [],
            "research_status": state_summary(state)["research_status"],
        }
    elif args.command == "plan-ablation":
        payload = {"planned": plan_ablation(args), "state": state_summary(read_state(args.workspace))}
    elif args.command == "analyze":
        payload = {"analysis": analyze_experiment(args), "state": state_summary(read_state(args.workspace))}
    elif args.command == "export-reports":
        payload = sync_reports(args.workspace, read_state(args.workspace), args.out_dir)
    elif args.command == "next":
        payload = next_action(read_state(args.workspace))
    elif args.command == "compare":
        payload = compare_experiments(read_state(args.workspace), args.parent, args.child)
    else:
        payload = state_summary(read_state(args.workspace))
    print_payload(payload, args.json)


if __name__ == "__main__":
    main()
