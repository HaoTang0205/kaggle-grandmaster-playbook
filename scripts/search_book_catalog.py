from __future__ import annotations

import argparse
import json
from pathlib import Path

from grandmaster_core import (
    CURATED_CATALOG,
    DOMAIN_QUERY_TERMS,
    build_profile,
    configure_policy,
    default_catalog_paths,
    infer_domains,
    infer_intent,
    json_ready,
    load_query_inputs,
    load_or_build_index,
    normalize_domain,
    retrieve_evidence,
    tokenize,
)


DEFAULT_CATALOG = CURATED_CATALOG
DOMAIN_TERMS = DOMAIN_QUERY_TERMS
tokens = tokenize


def parse_catalogs(values: list[Path] | None) -> list[Path]:
    return values or default_catalog_paths()


def print_text(payload: dict, total: int) -> None:
    profile = payload["profile"]
    coverage = payload["coverage"]
    print(
        "mode: hybrid-research"
        f" | domains: {', '.join(profile.get('domains') or []) or 'unclassified'}"
        f" | intent: {payload.get('intent') or 'general'}"
        f" | confidence: {coverage['confidence']}"
    )
    print(
        f"matches: {len(payload['results'])} / {total}"
        f" | direct_or_near: {coverage['direct_or_near']}"
        f" | unique_competitions: {coverage['unique_competitions']}"
    )
    if coverage["gaps"]:
        print("coverage gaps: " + " | ".join(coverage["gaps"]))
    for index, item in enumerate(payload["results"], start=1):
        print(f"\n[{index}] score={item['score']} | match={item['match_level']} | {item['title']}")
        print(f"chapter: {item['chapter']}")
        print(
            f"competition: {item['competition_slug']}"
            f" | source: {item['source']}"
            f" | type: {item['source_type']}"
            f" | tier: {item['catalog_tier']}"
        )
        print(f"anchor: {item['anchor']}")
        if item["matched_lenses"]:
            print("lenses: " + ", ".join(item["matched_lenses"]))
        if item["reasons"]:
            print("why: " + "; ".join(item["reasons"]))
        if item["algo_tags"]:
            print("algo_tags: " + ", ".join(item["algo_tags"]))
        if item["core_keywords"]:
            print("keywords: " + ", ".join(item["core_keywords"]))
        if item["trick_highlights"]:
            print("tricks: " + " | ".join(item["trick_highlights"][:4]))
        if item["summary"]:
            print("summary: " + item["summary"])
    if payload.get("mechanism_bridges"):
        print("\nCross-competition mechanism bridges:")
        for item in payload["mechanism_bridges"]:
            print(
                f"- {item.get('competition_slug') or item.get('title')}"
                f" | {item.get('match_level')} | {'; '.join(item.get('reasons') or [])}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hybrid search over curated and full Kaggle Grandmaster Playbook catalogs."
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Free-form task, symptom, mechanism, or question. Repeat to add independent query lenses.",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        action="append",
        default=None,
        help="TXT/Markdown (one query per line) or JSON list of free-form queries.",
    )
    parser.add_argument("--domain", default=None, help="Optional explicit domain.")
    parser.add_argument("--slug", default="", help="Optional exact Kaggle competition slug.")
    parser.add_argument(
        "--intent",
        choices=("code", "strategy", "debug", "baseline", "high_score"),
        default=None,
    )
    parser.add_argument("--auto", action="store_true", help="Infer a competition profile from the query.")
    parser.add_argument("--metric", default="", help="Optional official metric.")
    parser.add_argument("--data", default="", help="Optional data schema or modality description.")
    parser.add_argument("--constraints", default="", help="Optional runtime/submission constraints.")
    parser.add_argument("--recall", type=int, default=80, help="Candidates retained per query lens.")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--catalog",
        type=Path,
        action="append",
        default=None,
        help="Catalog path. Repeat to fuse multiple catalogs; defaults to curated + full.",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--policy", type=Path, default=None, help="Optional retrieval policy override JSON.")
    parser.add_argument("--refresh-index", action="store_true", help="Rebuild the local retrieval cache.")
    args = parser.parse_args()

    configure_policy(args.policy)
    custom_queries = load_query_inputs(args.query, args.query_file)
    query_text = " ".join(custom_queries)

    profile = build_profile(
        slug=args.slug,
        description=query_text,
        metric=args.metric,
        data=args.data,
        constraints=args.constraints,
        explicit_domain=args.domain,
    )
    if not args.auto and not args.domain:
        profile.domains = []
    catalog_paths = parse_catalogs(args.catalog)
    index = load_or_build_index(catalog_paths, refresh=args.refresh_index)
    research = retrieve_evidence(
        None,
        profile,
        query=custom_queries,
        intent=args.intent,
        recall=max(args.recall, args.limit),
        limit=args.limit,
        index=index,
    )
    payload = {
        "mode": "hybrid-research",
        "profile": profile.to_dict(),
        "custom_queries": custom_queries,
        **research,
    }
    if args.json:
        print(json.dumps(json_ready(payload), ensure_ascii=False, indent=2))
    else:
        print_text(payload, index.entry_count)


if __name__ == "__main__":
    main()
