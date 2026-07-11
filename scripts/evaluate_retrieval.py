from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from grandmaster_core import (
    build_profile,
    configure_policy,
    default_catalog_paths,
    load_or_build_index,
    normalize_text,
    retrieve_evidence,
)


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CASES = SKILL_DIR / "tests" / "retrieval_benchmark.json"


def values(case: dict, plural: str, singular: str = "") -> list[str]:
    raw = case.get(plural)
    if raw is None and singular:
        raw = case.get(singular)
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw if str(item)]


def percentile(samples: list[float], fraction: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999999)))
    return ordered[index]


def rank_of(slugs: list[str], expected: list[str]) -> int | None:
    expected_set = set(expected)
    return next((rank for rank, slug in enumerate(slugs, start=1) if slug in expected_set), None)


def evaluate_case(case: dict, index, limit: int) -> dict:
    profile = build_profile(
        slug=case.get("slug", ""),
        title=case.get("title", ""),
        description=case.get("description", ""),
        metric=case.get("metric", ""),
        data=case.get("data", ""),
        constraints=case.get("constraints", ""),
        stage=case.get("stage", "intake"),
        explicit_domain=case.get("explicit_domain"),
    )
    started = perf_counter()
    retrieval = retrieve_evidence(
        None,
        profile,
        query=case.get("query", ""),
        intent=case.get("intent", "strategy"),
        limit=limit,
        recall=int(case.get("recall", 80)),
        index=index,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0
    results = retrieval["results"]
    top_text = normalize_text(
        " ".join(
            " ".join(
                [
                    item.get("title") or "",
                    item.get("summary") or "",
                    " ".join(item.get("core_keywords") or []),
                    " ".join(item.get("method_keywords") or []),
                    " ".join(item.get("pattern_families") or []),
                    " ".join(item.get("trick_highlights") or []),
                ]
            )
            for item in results
        )
    )
    expected_domains = values(case, "expected_domains", "expected_domain")
    expected_terms = values(case, "expected_terms")
    expected_slugs = values(case, "expected_slugs", "expected_slug")
    forbidden_slugs = set(values(case, "forbidden_slugs"))
    slugs = [str(item.get("competition_slug") or "") for item in results]
    term_hits = [term for term in expected_terms if normalize_text(term) in top_text]
    expected_rank = rank_of(slugs, expected_slugs)
    domain_ok = not expected_domains or bool(set(expected_domains) & set(profile.domains or []))
    terms_ok = not expected_terms or len(term_hits) >= int(case.get("min_term_hits", 1))
    max_rank = int(case.get("max_expected_rank", limit))
    slug_ok = not expected_slugs or (expected_rank is not None and expected_rank <= max_rank)
    forbidden_hits = [slug for slug in slugs if slug in forbidden_slugs]
    direct_ratio = sum(
        1 for item in results if item["match_level"] in {"exact", "direct", "near"}
    ) / max(len(results), 1)
    source_link_ratio = retrieval["coverage"]["source_link_hits"] / max(len(results), 1)
    direct_ok = direct_ratio >= float(case.get("min_direct_ratio", 0.6))
    source_ok = source_link_ratio >= float(case.get("min_source_link_ratio", 0.6))
    passed = domain_ok and terms_ok and slug_ok and not forbidden_hits and direct_ok and source_ok
    return {
        "name": case["name"],
        "passed": passed,
        "domains": profile.domains,
        "domain_ok": domain_ok,
        "term_hits": term_hits,
        "terms_ok": terms_ok,
        "expected_rank": expected_rank,
        "slug_ok": slug_ok,
        "forbidden_hits": forbidden_hits,
        "direct_ratio": round(direct_ratio, 3),
        "source_link_ratio": round(source_link_ratio, 3),
        "confidence": retrieval["coverage"]["confidence"],
        "risk_flagged_hits": retrieval["coverage"]["risk_flagged_hits"],
        "elapsed_ms": round(elapsed_ms, 3),
        "candidate_count": retrieval["candidate_count"],
        "materialized_candidate_count": retrieval["materialized_candidate_count"],
        "top_competitions": slugs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ranked, provenance-aware retrieval regression benchmarks.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--catalog", type=Path, action="append", default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-p95-ms", type=float, default=2500.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any quality or latency failure.")
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--refresh-index", action="store_true")
    args = parser.parse_args()

    configure_policy(args.policy)
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    catalog_paths = args.catalog or default_catalog_paths()
    index = load_or_build_index(catalog_paths, refresh=args.refresh_index)
    try:
        results = [evaluate_case(case, index, args.limit) for case in cases]
    finally:
        close = getattr(index, "close", None)
        if close:
            close()

    ranked = [result for result in results if result["expected_rank"] is not None]
    expected_slug_cases = [case for case in cases if values(case, "expected_slugs", "expected_slug")]
    latencies = [result["elapsed_ms"] for result in results]
    p95_ms = percentile(latencies, 0.95)
    payload = {
        "schema_version": 2,
        "case_count": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "pass_rate": round(sum(1 for result in results if result["passed"]) / max(len(results), 1), 4),
        "mrr": round(sum(1.0 / result["expected_rank"] for result in ranked) / max(len(expected_slug_cases), 1), 4),
        "recall_at_k": round(len(ranked) / max(len(expected_slug_cases), 1), 4),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 3),
            "p95": round(p95_ms, 3),
            "max": round(max(latencies, default=0.0), 3),
            "budget_p95": args.max_p95_ms,
            "passed": p95_ms <= args.max_p95_ms,
        },
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"retrieval benchmark: {payload['passed']}/{payload['case_count']} "
            f"({payload['pass_rate']:.1%}), MRR={payload['mrr']:.3f}, "
            f"R@{args.limit}={payload['recall_at_k']:.3f}, P95={p95_ms:.1f}ms"
        )
        for result in results:
            marker = "PASS" if result["passed"] else "FAIL"
            print(
                f"{marker} {result['name']}: domains={','.join(result['domains'])} "
                f"rank={result['expected_rank'] or '-'} direct={result['direct_ratio']:.1%} "
                f"sources={result['source_link_ratio']:.1%} latency={result['elapsed_ms']:.1f}ms"
            )
    if args.strict and (payload["passed"] != payload["case_count"] or not payload["latency_ms"]["passed"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
