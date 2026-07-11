from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from competition_memory import (
    assert_owner,
    find_experiment,
    persist_state,
    read_state,
    state_lock,
    utc_now,
    write_text_atomic,
)
from grandmaster_core import LEARNED_CATALOG, SKILL_DIR, normalize_text, tokenize


DEFAULT_KNOWLEDGE_BASE = SKILL_DIR / "knowledge_base" / "experience_cards"


def dedupe(values) -> list:
    return list(dict.fromkeys(value for value in values if value not in (None, "", [], {})))


def safe_reference(value: str | None) -> str:
    if not value:
        return ""
    normalized = str(value).replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1]


def safe_source_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlsplit(str(value))
    if parsed.scheme not in {"http", "https"}:
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def read_profile(path: Path | None) -> dict:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("profile", payload) if isinstance(payload, dict) else {}


def card_digest(card: dict) -> str:
    payload = dict(card)
    payload.pop("card_hash", None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stamp_card(card: dict) -> dict:
    card["card_hash"] = card_digest(card)
    return card


def code_evidence_errors(card: dict) -> list[str]:
    errors = []
    evidence = card.get("code_evidence") or []
    lesson_ids = {item.get("id") for item in (card.get("validated_lessons") or []) + (card.get("negative_lessons") or [])}
    seen = set()
    for item in evidence:
        evidence_id = str(item.get("id") or "")
        path = str(item.get("path") or "").replace("\\", "/")
        excerpt = str(item.get("excerpt") or "")
        if not evidence_id or evidence_id in seen:
            errors.append(f"code evidence has a missing or duplicate id: {evidence_id or '<missing>'}")
        seen.add(evidence_id)
        if not path or re.match(r"^(?:[A-Za-z]:|/)", path) or ".." in Path(path).parts:
            errors.append(f"code evidence {evidence_id} has an unsafe path")
        if not excerpt.strip():
            errors.append(f"code evidence {evidence_id} has no excerpt")
        expected = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
        if item.get("content_sha256") != expected:
            errors.append(f"code evidence {evidence_id} content hash mismatch")
        if not re.fullmatch(r"[a-f0-9]{64}", str(item.get("source_sha256") or "")):
            errors.append(f"code evidence {evidence_id} needs a SHA-256 hash of its source file")
        if not isinstance(item.get("start_line"), int) or not isinstance(item.get("end_line"), int):
            errors.append(f"code evidence {evidence_id} needs integer line bounds")
        elif item["start_line"] <= 0 or item["end_line"] < item["start_line"]:
            errors.append(f"code evidence {evidence_id} has invalid line bounds")
        unknown_lessons = set(item.get("lesson_ids") or []) - lesson_ids
        if unknown_lessons:
            errors.append(f"code evidence {evidence_id} references unknown lessons: {sorted(unknown_lessons)}")
    evidence_ids = {item.get("id") for item in evidence}
    for lesson in card.get("validated_lessons") or []:
        unknown = set(lesson.get("code_evidence_ids") or []) - evidence_ids
        if unknown:
            errors.append(f"lesson {lesson.get('id')} references unknown code evidence: {sorted(unknown)}")
    return errors


def external_code_provenance_errors(card: dict) -> list[str]:
    if card.get("card_type") != "external_source_competition" or not card.get("code_evidence"):
        return []
    reproduction = card.get("reproducibility") or {}
    errors = []
    if not safe_source_url(reproduction.get("repository") or ""):
        errors.append("external code evidence needs a public repository URL")
    if not re.fullmatch(r"[a-f0-9]{7,64}", str(reproduction.get("code_version") or "").lower()):
        errors.append("external code evidence needs an immutable commit hash")
    if str(reproduction.get("license") or "").strip().lower() in {"", "unknown", "not recorded"}:
        errors.append("external code evidence needs an explicit source license")
    return errors


def card_integrity_errors(card: dict, path: Path | None = None, *, require_promoted: bool = False) -> list[str]:
    errors = []
    if int(card.get("schema_version") or 0) < 1:
        errors.append("schema_version is missing")
    if not card.get("card_id"):
        errors.append("card_id is missing")
    if path and path.stem != card.get("card_id"):
        errors.append("card_id does not match the JSON filename")
    if not card.get("card_hash") or card_digest(card) != card.get("card_hash"):
        errors.append("card_hash is missing or stale")
    if require_promoted and card.get("status") != "promoted":
        errors.append("knowledge-base card is not promoted")
    review = card.get("review") or {}
    if review.get("status") != "reviewed" or review.get("quality_status", review.get("status")) not in {"pass", "reviewed"}:
        errors.append("review gate has not passed")
    if review.get("blockers"):
        errors.append("review gate still has blockers")
    competition = card.get("competition") or {}
    if not competition.get("slug") or not competition.get("metric"):
        errors.append("competition slug or metric is missing")
    if not (card.get("validated_lessons") or card.get("negative_lessons")):
        errors.append("card has no lessons")
    has_sources = bool((card.get("source_provenance") or {}).get("source_urls"))
    has_experiments = bool(
        card.get("best_solution_lineage")
        or any(item.get("experiment_id") for item in (card.get("validated_lessons") or []) + (card.get("negative_lessons") or []))
    )
    if not has_sources and not has_experiments:
        errors.append("card has neither verified sources nor a reproducible experiment lineage")
    if contains_sensitive_data(card):
        errors.append("card contains a credential-like string or private absolute path")
    errors.extend(code_evidence_errors(card))
    errors.extend(external_code_provenance_errors(card))
    if path:
        markdown = path.with_suffix(".md")
        expected_anchor = f"{{#experience-{card.get('card_id')}}}"
        if not markdown.exists():
            errors.append("matching Markdown card is missing")
        elif expected_anchor not in markdown.read_text(encoding="utf-8", errors="replace"):
            errors.append("matching Markdown card has no expected anchor")
    return errors


def analysis_lookup(state: dict) -> dict[str, dict]:
    result = {}
    for analysis in state.get("analysis_logs") or []:
        result[analysis["experiment_id"]] = analysis
    return result


def ablation_lookup(state: dict) -> dict[str, dict]:
    return {item["id"]: item for item in state.get("ablation_plan") or []}


def research_lookup(state: dict) -> dict[str, dict]:
    return {item["id"]: item for item in state.get("research_tasks") or []}


def linked_research(experiment: dict, research: dict[str, dict]) -> list[dict]:
    return [research[item] for item in experiment.get("research_ids") or [] if item in research]


def confidence_for(analysis: dict) -> str:
    snapshot = analysis.get("snapshot") or {}
    fold_count = snapshot.get("fold_count") or 0
    fold_wins = snapshot.get("fold_wins") or 0
    if analysis.get("verdict") == "supported" and fold_count >= 3 and fold_wins / fold_count >= 2 / 3:
        return "high"
    if analysis.get("verdict") in {"supported", "partially_supported"}:
        return "medium"
    return "low"


def lesson_from_analysis(
    experiment: dict,
    analysis: dict,
    ablations: dict[str, dict],
    research: dict[str, dict],
    lesson_id: str,
) -> dict:
    ablation = ablations.get(experiment.get("ablation_id") or "", {})
    sources = linked_research(experiment, research)
    transfer_conditions = list(ablation.get("fixed_conditions") or [])
    transfer_conditions.extend(item.get("transfer_conditions") for item in sources)
    failure_conditions = list(analysis.get("confounders") or [])
    failure_conditions.extend(item.get("failure_conditions") for item in sources)
    source_urls = []
    for item in sources:
        source_urls.extend(item.get("source_urls_checked") or [])
    factor = ablation.get("factor") or experiment.get("component") or "pipeline"
    return {
        "id": lesson_id,
        "title": f"{factor}: {experiment.get('hypothesis') or experiment.get('change')}",
        "verdict": analysis.get("verdict"),
        "confidence": confidence_for(analysis),
        "mechanism": analysis.get("mechanism") or "",
        "implementation": experiment.get("change") or "",
        "control": ablation.get("control") or "",
        "treatment": ablation.get("treatment") or "",
        "fixed_conditions": list(ablation.get("fixed_conditions") or []),
        "effect": analysis.get("snapshot") or {},
        "slice_findings": analysis.get("slice_findings") or [],
        "resource_tradeoff": analysis.get("resource_tradeoff") or "",
        "transfer_conditions": dedupe(transfer_conditions),
        "failure_conditions": dedupe(failure_conditions),
        "minimal_next_test": analysis.get("next_action") or "",
        "experiment_id": experiment.get("id"),
        "ablation_id": experiment.get("ablation_id"),
        "research_ids": experiment.get("research_ids") or [],
        "evidence_anchors": experiment.get("evidence_anchors") or [],
        "source_urls": dedupe(safe_source_url(url) for url in source_urls),
        "artifact_ref": safe_reference(experiment.get("artifact")),
        "code_evidence_ids": [],
    }


def best_lineage(state: dict) -> list[dict]:
    current_id = state.get("best_experiment_id")
    chain = []
    seen = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        experiment = find_experiment(state, current_id)
        chain.append({
            "experiment_id": experiment.get("id"),
            "component": experiment.get("component"),
            "change": experiment.get("change"),
            "cv_mean": experiment.get("cv_mean"),
            "cv_std": experiment.get("cv_std"),
            "artifact_ref": safe_reference(experiment.get("artifact")),
        })
        current_id = experiment.get("parent_id")
    chain.reverse()
    return chain


def reproducibility_snapshot(state: dict) -> dict:
    if not state.get("best_experiment_id"):
        return {}
    best = find_experiment(state, state["best_experiment_id"])
    return {
        "experiment_id": best.get("id"),
        "code_version": best.get("code_version") or "",
        "data_version": best.get("data_version") or "",
        "config_hash": best.get("config_hash") or "",
        "environment_hash": best.get("environment_hash") or "",
        "fold_version": best.get("fold_version") or "",
        "metric_version": best.get("metric_version") or "",
        "seeds": best.get("seeds") or [],
        "params": best.get("params") or {},
        "artifact_ref": safe_reference(best.get("artifact")),
    }


def build_keywords(profile: dict, lessons: list[dict], negatives: list[dict], custom: list[str]) -> list[str]:
    values = []
    values.extend(profile.get("domains") or [])
    values.extend(profile.get("mechanisms") or [])
    values.extend(profile.get("validation_risks") or [])
    values.extend(custom)
    for lesson in lessons + negatives:
        values.extend(tokenize(" ".join(str(lesson.get(key) or "") for key in ("title", "mechanism", "implementation"))))
    return dedupe(values)[:48]


def build_card(state: dict, profile: dict, args: argparse.Namespace) -> dict:
    analyses = analysis_lookup(state)
    ablations = ablation_lookup(state)
    research = research_lookup(state)
    validated = []
    negative = []
    for experiment in state.get("experiments") or []:
        analysis = analyses.get(experiment.get("id"))
        if analysis and analysis.get("verdict") in {"supported", "partially_supported"}:
            validated.append(
                lesson_from_analysis(experiment, analysis, ablations, research, f"L{len(validated) + 1:03d}")
            )
        elif analysis and analysis.get("verdict") in {"not_supported", "inconclusive"}:
            negative.append(
                lesson_from_analysis(experiment, analysis, ablations, research, f"N{len(negative) + 1:03d}")
            )
        elif experiment.get("status") == "failed":
            negative.append({
                "id": f"N{len(negative) + 1:03d}",
                "title": experiment.get("hypothesis") or experiment.get("change") or experiment.get("id"),
                "verdict": "failed",
                "confidence": "high",
                "mechanism": experiment.get("diagnosis") or "execution failure",
                "implementation": experiment.get("change") or "",
                "effect": {},
                "failure_conditions": dedupe([experiment.get("diagnosis"), experiment.get("notes")]),
                "experiment_id": experiment.get("id"),
                "evidence_anchors": experiment.get("evidence_anchors") or [],
                "artifact_ref": safe_reference(experiment.get("artifact")),
                "code_evidence_ids": [],
            })

    lesson_by_experiment = {
        lesson.get("experiment_id"): lesson
        for lesson in validated + negative
        if lesson.get("experiment_id")
    }
    code_evidence = []
    seen_evidence = set()
    for experiment in state.get("experiments") or []:
        lesson = lesson_by_experiment.get(experiment.get("id"))
        for raw in experiment.get("code_evidence") or []:
            item = dict(raw)
            identity = (
                str(item.get("path") or "").replace("\\", "/"),
                item.get("start_line"),
                item.get("end_line"),
                item.get("content_sha256"),
            )
            if identity in seen_evidence:
                continue
            seen_evidence.add(identity)
            item["id"] = item.get("id") or f"CE{len(code_evidence) + 1:03d}"
            item["lesson_ids"] = dedupe((item.get("lesson_ids") or []) + ([lesson["id"]] if lesson else []))
            code_evidence.append(item)
            if lesson:
                lesson["code_evidence_ids"] = dedupe((lesson.get("code_evidence_ids") or []) + [item["id"]])

    slug = state.get("competition_slug") or profile.get("slug") or "unknown-competition"
    existing = state.get("experience_summary") or {}
    suffix = hashlib.sha256(f"{slug}|{state.get('created_at', '')}".encode("utf-8")).hexdigest()[:8]
    card_id = existing.get("card_id") or re.sub(r"[^a-z0-9-]+", "-", f"{slug}-postmortem-{suffix}".lower()).strip("-")
    verified_research = [item for item in state.get("research_tasks") or [] if item.get("status") == "verified"]
    source_urls = dedupe(url for item in verified_research for url in item.get("source_urls_checked") or [])
    card = {
        "schema_version": 1,
        "card_id": card_id,
        "revision": int(existing.get("revision") or 0) + 1,
        "status": "draft",
        "created_at": utc_now(),
        "competition": {
            "slug": slug,
            "title": args.title or profile.get("title") or slug,
            "url": safe_source_url(args.competition_url or profile.get("competition_url") or ""),
            "metric": state.get("metric") or profile.get("metric") or "",
            "metric_direction": state.get("metric_direction") or "higher",
            "final_rank": args.final_rank,
            "medal": args.medal,
        },
        "task_fingerprint": {
            "domains": profile.get("domains") or [],
            "mechanisms": profile.get("mechanisms") or [],
            "metric_family": profile.get("metric_family") or "unknown",
            "validation_risks": profile.get("validation_risks") or [],
            "runtime_constraints": profile.get("runtime_constraints") or [],
            "data": profile.get("data") or "",
        },
        "summary": args.summary or (
            f"Post-competition distillation for {slug}: {len(validated)} validated lessons and "
            f"{len(negative)} negative or inconclusive lessons."
        ),
        "validated_lessons": validated,
        "negative_lessons": negative,
        "best_solution_lineage": best_lineage(state),
        "code_evidence": code_evidence,
        "reproducibility": reproducibility_snapshot(state),
        "source_provenance": {
            "verified_research_ids": [item["id"] for item in verified_research],
            "source_urls": dedupe(safe_source_url(url) for url in source_urls),
            "experiment_ids": [item.get("id") for item in state.get("experiments") or []],
        },
        "retrieval_keywords": build_keywords(profile, validated, negative, args.keyword or []),
        "review": {"status": "pending", "score": None, "blockers": [], "warnings": []},
    }
    return stamp_card(card)


def contains_sensitive_data(card: dict) -> bool:
    text = json.dumps(card, ensure_ascii=False)
    patterns = (
        r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]",
        r"/(?:Users|home)/[^/\s]+/",
        r"\bsk-[A-Za-z0-9]{32,}\b",
        r"\b(?:OPENAI_API_KEY|ANTHROPIC_AUTH_TOKEN|KAGGLE_KEY)\s*[:=]",
        r"https?://[^\s\"']+\?[^\s\"']+",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def quality_gate(card: dict, state: dict) -> dict:
    blockers = []
    warnings = []
    competition = card.get("competition") or {}
    validated = card.get("validated_lessons") or []
    negative = card.get("negative_lessons") or []
    if not competition.get("slug") or competition.get("slug") == "unknown-competition":
        blockers.append("competition slug is missing")
    if not competition.get("metric"):
        blockers.append("official metric is missing")
    if not validated and not negative:
        blockers.append("no validated or negative lesson was distilled")
    pending_analysis = [
        item.get("id")
        for item in state.get("experiments") or []
        if item.get("status") == "success"
        and item.get("component") not in {"validation", "baseline"}
        and item.get("analysis_status") != "complete"
    ]
    if pending_analysis:
        blockers.append("successful diagnostic experiments still need analysis: " + ", ".join(pending_analysis))
    for lesson in validated:
        missing = [key for key in ("mechanism", "implementation", "experiment_id") if not lesson.get(key)]
        if missing:
            blockers.append(f"lesson {lesson.get('id')} is missing: {', '.join(missing)}")
        if not lesson.get("transfer_conditions"):
            warnings.append(f"lesson {lesson.get('id')} has no explicit transfer conditions")
        if not lesson.get("failure_conditions"):
            warnings.append(f"lesson {lesson.get('id')} has no explicit failure boundary")
    if contains_sensitive_data(card):
        blockers.append("card contains a credential-like string or private absolute path")
    blockers.extend(code_evidence_errors(card))
    blockers.extend(external_code_provenance_errors(card))
    pending_research = [item["id"] for item in state.get("research_tasks") or [] if item.get("status") == "pending"]
    if pending_research:
        warnings.append(f"{len(pending_research)} source-research tasks remain pending; reject or resolve used claims")
    reproduction = card.get("reproducibility") or {}
    if card.get("code_evidence") and not reproduction.get("license"):
        warnings.append("code evidence has no recorded license; record ownership or upstream license before redistribution")
    if state.get("best_experiment_id"):
        for key in ("code_version", "data_version", "fold_version", "metric_version", "seeds"):
            if not reproduction.get(key):
                warnings.append(f"best solution reproduction is missing {key}")
    if not (card.get("source_provenance") or {}).get("source_urls"):
        warnings.append("no checked public source URL is recorded")
    score = max(0, 100 - len(blockers) * 25 - len(warnings) * 4)
    return {
        "status": "pass" if not blockers else "fail",
        "score": score,
        "blockers": blockers,
        "warnings": warnings,
        "checked_at": utc_now(),
    }


def format_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "not recorded"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_card(card: dict) -> str:
    competition = card["competition"]
    task = card.get("task_fingerprint") or {}
    lines = [
        f"## 1. {competition.get('title')} {{#experience-{card['card_id']}}}",
        "",
        f"> Competition: `{competition.get('slug')}` | Metric: `{competition.get('metric')}` | Status: `{card.get('status')}`",
        "",
        "### Summary",
        card.get("summary") or "",
        "",
        "### Task Fingerprint",
        f"- Domains: {format_value(task.get('domains'))}",
        f"- Mechanisms: {format_value(task.get('mechanisms'))}",
        f"- Validation risks: {format_value(task.get('validation_risks'))}",
        f"- Runtime constraints: {format_value(task.get('runtime_constraints'))}",
        f"- Metric family: {format_value(task.get('metric_family'))}",
        "",
        "### Validated Lessons",
    ]
    if not card.get("validated_lessons"):
        lines.append("No positive lesson passed the evidence gate. See negative lessons.")
    for lesson in card.get("validated_lessons") or []:
        lines += [
            f"#### {lesson['id']} {lesson['title']}",
            f"- Verdict / confidence: `{lesson.get('verdict')}` / `{lesson.get('confidence')}`",
            f"- Mechanism: {format_value(lesson.get('mechanism'))}",
            f"- Implementation: {format_value(lesson.get('implementation'))}",
            f"- Effect: {format_value(lesson.get('effect'))}",
            f"- Slice findings: {format_value(lesson.get('slice_findings'))}",
            f"- Transfer conditions: {format_value(lesson.get('transfer_conditions'))}",
            f"- Failure conditions: {format_value(lesson.get('failure_conditions'))}",
            f"- Resource tradeoff: {format_value(lesson.get('resource_tradeoff'))}",
            f"- Evidence: experiment `{lesson.get('experiment_id')}`, ablation `{lesson.get('ablation_id')}`",
            "",
        ]
    lines += ["### Negative And Inconclusive Lessons"]
    if not card.get("negative_lessons"):
        lines.append("No negative lesson was recorded.")
    for lesson in card.get("negative_lessons") or []:
        lines += [
            f"#### {lesson['id']} {lesson['title']}",
            f"- Verdict: `{lesson.get('verdict')}`",
            f"- Diagnosis: {format_value(lesson.get('mechanism'))}",
            f"- Failed or uncertain conditions: {format_value(lesson.get('failure_conditions'))}",
            "",
        ]
    if card.get("code_evidence"):
        lines += ["### Code Evidence"]
        for item in card.get("code_evidence") or []:
            language = re.sub(r"[^A-Za-z0-9_+-]", "", str(item.get("language") or "text")) or "text"
            location = f"{item.get('path')}:{item.get('start_line')}-{item.get('end_line')}"
            linked_lessons = ", ".join(item.get("lesson_ids") or [])
            lines += [
                f"#### {item.get('id')} `{location}`",
                f"- Lessons: {linked_lessons or 'general'}",
                f"- Symbol: `{item.get('symbol') or 'relevant_block'}`",
                f"````{language}",
                str(item.get("excerpt") or "").rstrip(),
                "````",
                f"- Excerpt SHA256: `{item.get('content_sha256')}`",
                "",
            ]
    lines += [
        "### Best Solution Lineage",
        "| Experiment | Component | Change | CV Mean | CV Std | Artifact |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in card.get("best_solution_lineage") or []:
        lines.append(
            f"| {item.get('experiment_id')} | {item.get('component')} | {item.get('change')} | "
            f"{item.get('cv_mean')} | {item.get('cv_std')} | {item.get('artifact_ref') or ''} |"
        )
    lines += [
        "",
        "### Reproducibility",
        f"```json\n{json.dumps(card.get('reproducibility') or {}, ensure_ascii=False, indent=2)}\n```",
        "",
        "### Retrieval Index",
        "- Keywords: " + ", ".join(card.get("retrieval_keywords") or []),
        "- Verified sources: " + format_value((card.get("source_provenance") or {}).get("source_urls")),
        "",
        "### Review Gate",
        f"- Status: `{(card.get('review') or {}).get('status')}`",
        f"- Score: `{(card.get('review') or {}).get('score')}`",
        f"- Warnings: {format_value((card.get('review') or {}).get('warnings'))}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_card_bundle(out_dir: Path, card: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_text_atomic(out_dir / "experience_card.json", json.dumps(card, ensure_ascii=False, indent=2) + "\n")
    write_text_atomic(out_dir / "experience_card.md", render_card(card))
    return {"json": "experience_card.json", "markdown": "experience_card.md"}


def load_card(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("card_id"):
        raise ValueError(f"Invalid experience card: {path}")
    return payload


def card_to_catalog_entry(card: dict) -> dict:
    competition = card.get("competition") or {}
    task = card.get("task_fingerprint") or {}
    validated = card.get("validated_lessons") or []
    negative = card.get("negative_lessons") or []
    tricks = []
    for lesson in validated:
        tricks.append(
            f"{lesson.get('title')}: {lesson.get('mechanism')}. Implementation: {lesson.get('implementation')}"
        )
    for lesson in negative:
        tricks.append(f"Negative evidence - {lesson.get('title')}: {lesson.get('mechanism')}")
    transfer = dedupe(
        condition
        for lesson in validated
        for condition in lesson.get("transfer_conditions") or []
    )
    factors = dedupe(
        value
        for lesson in validated + negative
        for value in (lesson.get("mechanism"), lesson.get("title"))
    )
    quality = (card.get("review") or {}).get("score") or 0
    source_urls = (card.get("source_provenance") or {}).get("source_urls") or []
    code_evidence = card.get("code_evidence") or []
    return {
        "id": f"experience-{card['card_id']}",
        "anchor": f"experience-{card['card_id']}",
        "title": f"{competition.get('title') or competition.get('slug')} reviewed competition experience",
        "competition_slug": competition.get("slug"),
        "competition_url": competition.get("url"),
        "source": card["card_id"],
        "source_url": source_urls[0] if source_urls else competition.get("url"),
        "source_type": "reviewed_experience",
        "provenance_status": "reviewed",
        "trust_level": "reviewed_derived_from_untrusted_sources",
        "source_license": (card.get("reproducibility") or {}).get("license") or "unknown",
        "source_content_sha256": card.get("card_hash") or "",
        "code_evidence_status": "cited" if code_evidence else "none",
        "chapter": "Learned Competition Experience",
        "algo_tags": task.get("domains") or [],
        "core_keywords": card.get("retrieval_keywords") or [],
        "method_keywords": factors[:24],
        "problem_signals": task.get("validation_risks") or [],
        "transfer_scenarios": transfer[:20],
        "pattern_families": task.get("mechanisms") or [],
        "trick_highlights": tricks[:16],
        "summary": card.get("summary") or "",
        "quality_score": min(300, quality + len(validated) * 12 + len(negative) * 5),
        "code_evidence_count": len(code_evidence),
        "tricks_count": len(tricks),
        "card_file": f"knowledge_base/experience_cards/{card['card_id']}.md",
    }


def rebuild_catalog(knowledge_base: Path, catalog: Path) -> dict:
    entries = []
    card_ids = set()
    for path in sorted(knowledge_base.glob("*.json")):
        card = load_card(path)
        errors = card_integrity_errors(card, path, require_promoted=True)
        if errors:
            raise ValueError(f"Invalid promoted experience card {path.name}: " + " | ".join(errors))
        if card["card_id"] in card_ids:
            raise ValueError(f"Duplicate promoted experience card id: {card['card_id']}")
        card_ids.add(card["card_id"])
        entries.append(card_to_catalog_entry(card))
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": "reviewed post-competition experience cards",
        "entry_count": len(entries),
        "entries": entries,
    }
    write_text_atomic(catalog, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def draft_command(args: argparse.Namespace) -> dict:
    out_dir = args.out_dir or (args.workspace.resolve() / "experience")
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        card = build_card(state, read_profile(args.profile), args)
        files = write_card_bundle(out_dir, card)
        state["status"] = "postmortem"
        state["experience_summary"] = {
            "status": "draft",
            "card_id": card["card_id"],
            "revision": card["revision"],
            "card_hash": card["card_hash"],
            "updated_at": utc_now(),
        }
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return {"card_id": card["card_id"], "status": "draft", "files": files}


def review_command(args: argparse.Namespace) -> tuple[dict, bool]:
    card_path = args.card or (args.workspace.resolve() / "experience" / "experience_card.json")
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        card = load_card(card_path)
        report = quality_gate(card, state)
        card["review"] = {
            **report,
            "reviewer": args.reviewer,
            "status": "reviewed" if report["status"] == "pass" else "changes_required",
        }
        card["status"] = "reviewed" if report["status"] == "pass" else "draft"
        stamp_card(card)
        write_card_bundle(card_path.parent, card)
        write_text_atomic(card_path.parent / "review_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        summary = state.setdefault("experience_summary", {})
        summary.update({
            "status": "reviewed" if report["status"] == "pass" else "draft",
            "card_id": card["card_id"],
            "revision": card.get("revision"),
            "card_hash": card["card_hash"],
            "updated_at": utc_now(),
        })
        state["status"] = "postmortem"
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return report, report["status"] == "pass"


def promote_command(args: argparse.Namespace) -> dict:
    card_path = args.card or (args.workspace.resolve() / "experience" / "experience_card.json")
    knowledge_base = args.knowledge_base or DEFAULT_KNOWLEDGE_BASE
    catalog = args.catalog or LEARNED_CATALOG
    with state_lock(args.workspace):
        state = read_state(args.workspace)
        assert_owner(state, args)
        summary = state.get("experience_summary") or {}
        if summary.get("status") != "reviewed":
            raise ValueError("Experience card must pass review before promotion.")
        card = load_card(card_path)
        if card_digest(card) != summary.get("card_hash"):
            raise ValueError("Experience card changed after review; review it again before promotion.")
        report = quality_gate(card, state)
        if report["status"] != "pass":
            raise ValueError("Experience card no longer passes the quality gate: " + " | ".join(report["blockers"]))
        card["status"] = "promoted"
        card["promoted_at"] = utc_now()
        stamp_card(card)
        knowledge_base.mkdir(parents=True, exist_ok=True)
        write_text_atomic(knowledge_base / f"{card['card_id']}.json", json.dumps(card, ensure_ascii=False, indent=2) + "\n")
        write_text_atomic(knowledge_base / f"{card['card_id']}.md", render_card(card))
        catalog_payload = rebuild_catalog(knowledge_base, catalog)
        state["status"] = "complete"
        state["experience_summary"] = {
            "status": "promoted",
            "card_id": card["card_id"],
            "revision": card.get("revision"),
            "card_hash": card["card_hash"],
            "catalog_anchor": f"experience-{card['card_id']}",
            "promoted_at": utc_now(),
        }
        state["updated_at"] = utc_now()
        persist_state(args.workspace, state)
    return {
        "card_id": card["card_id"],
        "status": "promoted",
        "catalog_anchor": f"experience-{card['card_id']}",
        "catalog_entries": catalog_payload["entry_count"],
    }


def add_workspace_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run-id", default="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill reviewed post-competition lessons into searchable long-term memory.")
    commands = parser.add_subparsers(dest="command", required=True)

    draft = commands.add_parser("draft")
    add_workspace_args(draft)
    draft.add_argument("--profile", type=Path, default=None)
    draft.add_argument("--out-dir", type=Path, default=None)
    draft.add_argument("--title", default="")
    draft.add_argument("--competition-url", default="")
    draft.add_argument("--final-rank", default="")
    draft.add_argument("--medal", default="")
    draft.add_argument("--summary", default="")
    draft.add_argument("--keyword", action="append", default=[])

    review = commands.add_parser("review")
    add_workspace_args(review)
    review.add_argument("--card", type=Path, default=None)
    review.add_argument("--reviewer", default="agent-and-human-gate")

    promote = commands.add_parser("promote")
    add_workspace_args(promote)
    promote.add_argument("--card", type=Path, default=None)
    promote.add_argument("--knowledge-base", type=Path, default=None)
    promote.add_argument("--catalog", type=Path, default=None)

    rebuild = commands.add_parser("rebuild-index")
    rebuild.add_argument("--knowledge-base", type=Path, default=DEFAULT_KNOWLEDGE_BASE)
    rebuild.add_argument("--catalog", type=Path, default=LEARNED_CATALOG)

    args = parser.parse_args()
    ok = True
    if args.command == "draft":
        payload = draft_command(args)
    elif args.command == "review":
        payload, ok = review_command(args)
    elif args.command == "promote":
        payload = promote_command(args)
    else:
        payload = rebuild_catalog(args.knowledge_base, args.catalog)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
