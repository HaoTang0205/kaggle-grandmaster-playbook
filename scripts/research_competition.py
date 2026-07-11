from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from grandmaster_core import (
    build_profile,
    configure_policy,
    default_catalog_paths,
    detect_signals,
    experiment_candidates,
    family_hypotheses,
    json_ready,
    load_query_inputs,
    load_or_build_index,
    normalize_text,
    policy_value,
    retrieve_evidence,
    validation_contract,
)


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key}: {stringify(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(stringify(item) for item in value)
    return str(value)


def read_profile(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("--profile JSON must contain an object.")
        profile_payload = payload.get("profile") if isinstance(payload.get("profile"), dict) else payload
        result = {str(key): stringify(value) for key, value in profile_payload.items()}
        schema_signals = payload.get("schema_signals")
        modalities = payload.get("modalities")
        if isinstance(schema_signals, dict):
            result["data"] = " ".join(filter(None, (result.get("data", ""), stringify(schema_signals))))
        if isinstance(modalities, list):
            result["data"] = " ".join(filter(None, (result.get("data", ""), "modalities " + stringify(modalities))))
        return result
    return {"description": raw}


def compact(value: str, limit: int = 2400) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def external_research_queries(profile: dict, custom_queries: list[str] | None = None) -> list[dict]:
    identity = " ".join(filter(None, (profile.get("slug"), profile.get("title")))).strip()
    domains = " ".join(profile.get("domains") or [])
    metric = profile.get("metric") or "competition metric"
    queries = []
    if identity:
        queries.append({
            "purpose": "official-ground-truth",
            "query": f"{identity} official competition rules data evaluation metric",
            "preferred_sources": "Kaggle competition pages and official host documentation",
        })
        queries.append({
            "purpose": "current-community-evidence",
            "query": f"site:kaggle.com/code OR site:kaggle.com/competitions {identity} {metric} public notebook discussion",
            "preferred_sources": "Kaggle notebooks, discussions and author write-ups",
        })
    queries.append({
        "purpose": "current-methods",
        "query": f"{domains} {metric} current state of the art official implementation paper",
        "preferred_sources": "original papers and official repositories",
    })
    for query in custom_queries or []:
        queries.append({
            "purpose": "user-directed",
            "query": query,
            "preferred_sources": "sources appropriate to the question; preserve the query instead of replacing it with a fixed taxonomy",
        })
    return queries


class SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def competition_deep_dives(
    results: list[dict],
    profile: dict,
    custom_queries: list[str] | None = None,
) -> list[dict]:
    competition_limit = int(policy_value("deep_dive", "top_competitions", 4))
    point_limit = int(policy_value("deep_dive", "knowledge_points_per_competition", 3))
    templates = policy_value("deep_dive", "query_templates", [])
    required_questions = policy_value("deep_dive", "required_questions", [])
    current_slug = profile.get("slug") or "current-competition"
    dossiers: dict[str, dict] = {}

    for hit in results:
        slug = (hit.get("competition_slug") or "").strip()
        if not slug:
            continue
        if slug not in dossiers:
            if competition_limit > 0 and len(dossiers) >= competition_limit:
                continue
            reasons = hit.get("reasons") or []
            dossiers[slug] = {
                "status": "pending",
                "competition_slug": slug,
                "official_url": hit.get("competition_url") or f"https://www.kaggle.com/competitions/{slug}",
                "why_selected": "; ".join(reasons) or f"Retrieved as {hit.get('match_level') or 'historical'} evidence.",
                "match_levels": [],
                "evidence_anchors": [],
                "knowledge_points": [],
                "custom_queries": [],
                "required_questions": list(required_questions),
                "requirements": {
                    "official_page": bool(policy_value("deep_dive", "require_official_page", True)),
                    "multiple_sources": bool(policy_value("deep_dive", "require_multiple_sources", True)),
                },
                "completion_gate": (
                    "Do not promote a knowledge point into implementation advice until its original task, "
                    "validation boundary, gain attribution, implementation, failure conditions, and transfer assumptions are checked."
                ),
            }
        dossier = dossiers[slug]
        if hit.get("match_level"):
            dossier["match_levels"].append(hit["match_level"])
        if hit.get("anchor"):
            dossier["evidence_anchors"].append(hit["anchor"])

        if len(dossier["knowledge_points"]) >= point_limit:
            continue

        candidates = list(hit.get("trick_highlights") or [])
        if not candidates:
            keywords = list(hit.get("method_keywords") or []) + list(hit.get("core_keywords") or [])
            if keywords:
                candidates.append("Investigate the source pattern: " + ", ".join(keywords[:6]))
        if not candidates and hit.get("summary"):
            candidates.append(compact(hit["summary"], 360))

        existing = {normalize_text(item["claim"]) for item in dossier["knowledge_points"]}
        for claim in candidates:
            claim = compact(str(claim), 600)
            if not claim or normalize_text(claim) in existing:
                continue
            fields = SafeFormatDict(
                slug=slug,
                knowledge_point=claim,
                current_slug=current_slug,
                current_title=profile.get("title") or current_slug,
                metric=profile.get("metric") or "competition metric",
            )
            verification_queries = list(
                dict.fromkeys(str(template).format_map(fields) for template in templates if str(template).strip())
            )
            dossier["knowledge_points"].append({
                "claim": claim,
                "source_anchor": hit.get("anchor"),
                "source": hit.get("source"),
                "source_url": hit.get("source_url"),
                "verification_queries": verification_queries,
                "verification_status": "pending",
            })
            existing.add(normalize_text(claim))
            if len(dossier["knowledge_points"]) >= point_limit:
                break

    for dossier in dossiers.values():
        slug = dossier["competition_slug"]
        dossier["match_levels"] = list(dict.fromkeys(dossier["match_levels"]))
        dossier["evidence_anchors"] = list(dict.fromkeys(dossier["evidence_anchors"]))
        dossier["custom_queries"] = [
            {"original": query, "scoped_query": f"{slug} {query}"}
            for query in custom_queries or []
        ]
    return list(dossiers.values())


def reading_manifest(results: list[dict]) -> dict:
    direct = [item for item in results if item["match_level"] in {"exact", "direct", "near"}]
    validation = [item for item in results if any(reason.startswith("risk:") for reason in item["reasons"])]
    code = [item for item in results if (item.get("code_evidence_count") or 0) > 0]
    writeup = [item for item in results if "writeup" in (item.get("source_type") or "").lower()]

    def anchors(items: list[dict], count: int) -> list[str]:
        return list(dict.fromkeys(item["anchor"] for item in items if item.get("anchor")))[:count]

    must_read = anchors(direct, 3)
    support = anchors(validation + code + writeup, 5)
    return {
        "must_read_anchors": must_read,
        "support_anchors": [anchor for anchor in support if anchor not in must_read],
        "rule": "Read full sections before turning a retrieved trick into implementation advice.",
    }


def decision_policy(profile: dict, coverage: dict) -> dict:
    unknowns = profile.get("unknowns") or []
    if unknowns:
        next_mode = "inspect"
        reason = "Competition facts required for trustworthy validation are still missing."
    elif coverage["confidence"] == "low":
        next_mode = "research"
        reason = "Historical evidence is too weak for confident transfer."
    elif profile.get("stage") in {"intake", "eda"}:
        next_mode = "baseline"
        reason = "The profile is sufficient to establish validation and a reproducible baseline."
    else:
        next_mode = "experiment"
        reason = "Evidence coverage is adequate for isolated, scored experiments."
    return {
        "next_mode": next_mode,
        "reason": reason,
        "hard_rule": "Change one major pipeline component per diagnostic experiment; preserve the current best artifact.",
    }


def render_markdown(payload: dict) -> str:
    profile = payload["profile"]
    coverage = payload["evidence"]["coverage"]
    lines = ["# Kaggle Grandmaster Decision Brief", ""]
    lines += ["## 1. Competition Contract"]
    for key in ("slug", "title", "stage", "metric", "metric_family", "data", "constraints"):
        value = profile.get(key)
        if value:
            lines.append(f"- {key}: {value}")
    lines.append(f"- inferred_domains: {', '.join(profile.get('domains') or []) or 'unclassified'}")
    lines.append(f"- inferred_mechanisms: {', '.join(profile.get('mechanisms') or []) or 'not yet identified'}")
    lines.append(f"- validation_risks: {', '.join(profile.get('validation_risks') or []) or 'not yet identified'}")
    lines.append(f"- runtime_constraints: {', '.join(profile.get('runtime_constraints') or []) or 'not yet identified'}")
    if profile.get("unknowns"):
        lines.append("- blocking_unknowns: " + " | ".join(profile["unknowns"]))

    lines += ["", "## 2. Validation Gates"]
    for gate in payload["validation_contract"]:
        lines.append(f"- **{gate['gate']}**: {gate['action']}")
        lines.append(f"  Pass: {gate['pass_condition']}")

    lines += ["", "## 3. Evidence Coverage"]
    lines.append(f"- confidence: {coverage['confidence']}")
    lines.append(
        f"- direct_or_near: {coverage['direct_or_near']} | code_hits: {coverage['code_hits']}"
        f" | writeup_hits: {coverage['writeup_hits']} | validation_hits: {coverage['validation_hits']}"
    )
    if coverage["gaps"]:
        lines.append("- gaps: " + " | ".join(coverage["gaps"]))

    lines += ["", "## 4. Historical Evidence Map"]
    lines.append("| Rank | Match | Case | Why | Anchor |")
    lines.append("|---:|---|---|---|---|")
    for index, item in enumerate(payload["evidence"]["results"], start=1):
        why = "; ".join(item.get("reasons") or [])[:260]
        case = item.get("title") or item.get("source") or item.get("competition_slug")
        lines.append(f"| {index} | {item['match_level']} | {case} | {why} | `{item['anchor']}` |")

    bridges = payload["evidence"].get("mechanism_bridges") or []
    if bridges:
        lines += ["", "### Cross-competition mechanism bridges"]
        for item in bridges:
            why = "; ".join(item.get("reasons") or [])
            lines.append(
                f"- **{item.get('competition_slug') or item.get('title')}**: {why} | `{item.get('anchor')}`"
            )

    lines += ["", "## 5. Reading Manifest"]
    lines.append("- Must read: " + ", ".join(f"`{x}`" for x in payload["reading_manifest"]["must_read_anchors"]) if payload["reading_manifest"]["must_read_anchors"] else "- Must read: none")
    lines.append("- Support: " + ", ".join(f"`{x}`" for x in payload["reading_manifest"]["support_anchors"]) if payload["reading_manifest"]["support_anchors"] else "- Support: none")

    lines += ["", "## 6. Source Competition Deep Dives"]
    if not payload["competition_deep_dives"]:
        lines.append("- No source competition could be resolved; keep the evidence provisional and search manually.")
    for index, dossier in enumerate(payload["competition_deep_dives"], start=1):
        lines.append(f"### D{index:02d} {dossier['competition_slug']}")
        lines.append(f"- Status: {dossier['status']}")
        lines.append(f"- Official page: {dossier['official_url']}")
        lines.append(f"- Why selected: {dossier['why_selected']}")
        lines.append(f"- Completion gate: {dossier['completion_gate']}")
        for point_index, point in enumerate(dossier["knowledge_points"], start=1):
            lines.append(f"- Knowledge point D{index:02d}.K{point_index:02d}: {point['claim']}")
            if point.get("source_anchor"):
                lines.append(f"  Source anchor: `{point['source_anchor']}`")
            for query in point["verification_queries"]:
                lines.append(f"  Verify: `{query}`")
        for query in dossier["custom_queries"]:
            lines.append(f"- User query: `{query['original']}`")
            lines.append(f"  Competition-scoped: `{query['scoped_query']}`")
        lines.append("- Required answers: " + " | ".join(dossier["required_questions"]))

    lines += ["", "## 7. Experiment Portfolio"]
    for index, experiment in enumerate(payload["experiments"], start=1):
        anchors = ", ".join(f"`{anchor}`" for anchor in experiment["evidence_anchors"] if anchor) or "validation contract"
        lines.append(f"### E{index:02d} [{experiment['priority']}] {experiment['component']}")
        lines.append(f"- Hypothesis: {experiment['hypothesis']}")
        lines.append(f"- Isolated change: {experiment['change']}")
        lines.append(f"- Evidence: {anchors}")
        lines.append(f"- Expected signal: {experiment['expected_signal']}")
        lines.append(f"- Stop condition: {experiment['stop_condition']}")
        lines.append(f"- Cost: {experiment['cost']}")

    policy = payload["decision_policy"]
    lines += ["", "## 8. Agent Decision"]
    lines.append(f"- next_mode: {policy['next_mode']}")
    lines.append(f"- why: {policy['reason']}")
    lines.append(f"- hard_rule: {policy['hard_rule']}")

    lines += ["", "## 9. Live Research Queries"]
    for query in payload["external_research_queries"]:
        lines.append(f"- {query['purpose']}: `{query['query']}`")
        lines.append(f"  Prefer: {query['preferred_sources']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an evidence-backed Kaggle competition decision brief."
    )
    parser.add_argument("--profile", type=Path, default=None)
    parser.add_argument("--slug", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    parser.add_argument("--metric", default="")
    parser.add_argument("--data", default="")
    parser.add_argument("--constraints", default="")
    parser.add_argument("--stage", choices=("intake", "eda", "baseline", "improve", "ensemble", "finalize"), default=None)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--intent", choices=("code", "strategy", "debug", "baseline", "high_score"), default="strategy")
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Free-form research question. Repeat for multiple questions; no fixed taxonomy is required.",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        action="append",
        default=None,
        help="TXT/Markdown (one query per line) or JSON list of free-form questions.",
    )
    parser.add_argument("--policy", type=Path, default=None, help="Optional retrieval/deep-dive policy override JSON.")
    parser.add_argument("--budget", choices=("quick", "standard", "deep"), default="standard")
    parser.add_argument("--catalog", type=Path, action="append", default=None)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--recall", type=int, default=80)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="Optional output file; stdout is always supported.")
    parser.add_argument("--json-out", type=Path, default=None, help="Optional machine-readable decision payload.")
    parser.add_argument("--refresh-index", action="store_true", help="Rebuild the local retrieval cache.")
    args = parser.parse_args()

    configure_policy(args.policy)
    custom_queries = load_query_inputs(args.query, args.query_file)

    source = read_profile(args.profile)
    for key in ("slug", "title", "description", "metric", "data", "constraints", "stage"):
        value = getattr(args, key)
        if value:
            source[key] = value
    profile = build_profile(
        slug=source.get("slug", ""),
        title=source.get("title", ""),
        description=compact(source.get("description", "")),
        metric=source.get("metric", ""),
        data=compact(source.get("data", "")),
        constraints=compact(source.get("constraints", "")),
        stage=source.get("stage") or "intake",
        explicit_domain=args.domain,
    )
    catalog_paths = args.catalog or default_catalog_paths()
    index = load_or_build_index(catalog_paths, refresh=args.refresh_index)
    evidence = retrieve_evidence(
        None,
        profile,
        query=custom_queries,
        intent=args.intent,
        recall=max(args.recall, args.limit),
        limit=args.limit,
        index=index,
    )
    transferable_evidence = evidence["results"] + evidence.get("mechanism_bridges", [])
    deep_dives = competition_deep_dives(
        transferable_evidence,
        profile.to_dict(),
        custom_queries,
    )
    allowed_claims = {
        (dossier["competition_slug"], normalize_text(point["claim"]))
        for dossier in deep_dives
        for point in dossier["knowledge_points"]
    }
    payload = {
        "mode": "grandmaster-decision-brief-v3",
        "profile": profile.to_dict(),
        "custom_queries": custom_queries,
        "validation_contract": validation_contract(profile),
        "evidence": evidence,
        "reading_manifest": reading_manifest(transferable_evidence),
        "competition_deep_dives": deep_dives,
        "experiments": experiment_candidates(
            profile,
            transferable_evidence,
            args.budget,
            allowed_claims=allowed_claims,
        ),
        "decision_policy": decision_policy(profile.to_dict(), evidence["coverage"]),
        "external_research_queries": external_research_queries(profile.to_dict(), custom_queries),
    }
    rendered = json.dumps(json_ready(payload), ensure_ascii=False, indent=2) if args.json else render_markdown(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
