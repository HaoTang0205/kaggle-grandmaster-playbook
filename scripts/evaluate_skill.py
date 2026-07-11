from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter

from audit_pipeline import audit_script
from build_evidence_packet import build_packet
from capture_code_evidence import capture
from competition_memory import analyze_experiment, init_state, plan_ablation, record_experiment
from distill_competition_experience import draft_command, promote_command, review_command
from evidence_safety import BEGIN_MARKER, END_MARKER
from grandmaster_core import build_profile, default_catalog_paths, load_or_build_index, retrieve_evidence
from profile_competition import (
    asset_profiles,
    data_description,
    file_inventory,
    infer_modalities,
    infer_schema_signals,
    summarize_csv,
)


def record_args(workspace: Path, run_id: str, **overrides) -> argparse.Namespace:
    values = {
        "workspace": workspace,
        "run_id": run_id,
        "id": "E00",
        "parent_id": "",
        "ablation_id": "",
        "component": "validation",
        "hypothesis": "verify grouped validation",
        "change": "GroupKFold by customer_id",
        "evidence_anchor": [],
        "research_id": [],
        "status": "success",
        "cv_mean": None,
        "cv_std": None,
        "fold_scores": [],
        "slice_metrics": {},
        "lb_score": None,
        "runtime_minutes": 1.0,
        "peak_memory_mb": 128.0,
        "artifact": "",
        "notes": "",
        "diagnosis": "",
        "code_evidence_file": [],
        "code_version": "",
        "data_version": "",
        "config_hash": "",
        "environment_hash": "",
        "fold_version": "",
        "metric_version": "",
        "seeds": [],
        "params": {},
        "min_delta": 1e-6,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def run_evaluation() -> dict:
    started = perf_counter()
    gates: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="kaggle-gm-e2e-") as temp:
        root = Path(temp)
        data_root = root / "competition_data"
        data_root.mkdir()
        (data_root / "train.csv").write_text(
            "row_id,customer_id,event_time,feature,target\n"
            "1,c1,2026-01-01,0.1,0\n2,c1,2026-01-02,0.2,1\n3,c2,2026-01-03,0.3,1\n",
            encoding="utf-8",
        )
        (data_root / "test.csv").write_text(
            "row_id,customer_id,event_time,feature\n4,c3,2026-02-01,0.4\n",
            encoding="utf-8",
        )
        (data_root / "sample_submission.csv").write_text("row_id,target\n4,0.5\n", encoding="utf-8")
        (data_root / "episode_replay.jsonl").write_text('{"state": 1, "action": 0}\n', encoding="utf-8")

        inventory, suffixes = file_inventory(data_root)
        tables = [
            summarize_csv(data_root / item["file"], data_root, 100)
            for item in inventory
            if Path(item["file"]).suffix.lower() in {".csv", ".tsv"}
        ]
        schema = infer_schema_signals(tables, inventory)
        assets = asset_profiles(data_root, inventory)
        modalities = infer_modalities(suffixes, tables)
        profile = build_profile(
            slug="portable-e2e-demo",
            description="grouped binary tabular prediction with repeated customers and chronological shift",
            metric="AUC",
            data=data_description(modalities, schema, suffixes, assets),
            stage="eda",
        )
        gates["profile"] = {
            "passed": "customer_id" in schema["group_candidates"] and "target" in schema["target_candidates"],
            "modalities": modalities,
            "group_candidates": schema["group_candidates"],
        }

        index = load_or_build_index(default_catalog_paths())
        try:
            retrieval = retrieve_evidence(
                None,
                profile,
                query=["fold-safe target encoding", "public private distribution shift"],
                limit=5,
                recall=80,
                index=index,
            )
        finally:
            close = getattr(index, "close", None)
            if close:
                close()
        anchors = [item["anchor"] for item in retrieval["results"][:2] if item.get("anchor")]
        gates["retrieval"] = {
            "passed": bool(anchors) and retrieval["coverage"]["source_link_hits"] >= 2,
            "anchors": anchors,
            "source_link_hits": retrieval["coverage"]["source_link_hits"],
        }
        brief = {
            "profile": profile.to_dict(),
            "results": retrieval["results"],
            "reading_manifest": {"must_read_anchors": anchors, "support_anchors": []},
        }
        packet = build_packet(brief, anchors, max_chars_per_section=6000, max_total_chars=14000)
        gates["evidence_boundary"] = {
            "passed": packet.count(BEGIN_MARKER) == len(anchors) and packet.count(END_MARKER) == len(anchors),
            "sections": len(anchors),
        }

        pipeline = root / "pipeline.py"
        pipeline.write_text(
            "from sklearn.model_selection import GroupKFold\n"
            "from sklearn.metrics import roc_auc_score\n"
            "splitter = GroupKFold(3)\n"
            "model = Estimator(random_state=42)\n"
            "model.fit(X_train, y_train)\n"
            "score = roc_auc_score(y_valid, model.predict_proba(X_valid)[:, 1])\n",
            encoding="utf-8",
        )
        audit = audit_script(
            pipeline,
            {"profile": profile.to_dict(), "schema_signals": schema, "roles": {}, "data_usage_gate": {}},
        )
        gates["pipeline_audit"] = {"passed": audit["counts"]["blocker"] == 0, "counts": audit["counts"]}

        workspace = root / "workspace"
        run_id = "portable-e2e-run"
        init_state(argparse.Namespace(
            workspace=workspace,
            slug="portable-e2e-demo",
            metric="AUC",
            metric_direction="higher",
            budget_hours=1.0,
            deadline_at="",
            relative_cv_std_threshold=0.025,
            absolute_cv_std_threshold=None,
            minimum_stability_observations=3,
            run_id=run_id,
            force=False,
        ))
        record_experiment(record_args(workspace, run_id))
        record_experiment(record_args(
            workspace,
            run_id,
            id="E01",
            component="baseline",
            hypothesis="reproducible grouped baseline",
            change="GroupKFold CatBoost baseline",
            cv_mean=0.70,
            cv_std=0.01,
            fold_scores=[0.69, 0.70, 0.71],
            runtime_minutes=4.0,
            code_version="demo123",
            data_version="data-v1",
            config_hash="cfg-v1",
            environment_hash="env-v1",
            fold_version="group-v1",
            metric_version="auc-v1",
            seeds=[42],
        ))
        plan_ablation(argparse.Namespace(
            workspace=workspace,
            run_id=run_id,
            id="A001",
            design="ofat",
            parent_experiment="E01",
            component="features",
            factor="fold-safe target encoding",
            control="disabled",
            treatment="enabled",
            fixed_condition=["folds=group-v1", "seed=42"],
            hypothesis="Fold-safe encoding improves repeated-category generalization.",
            expected_signal="OOF AUC improves without higher fold variance.",
            primary_metric="AUC",
            expected_direction="higher",
            research_id=[],
            cost="low",
        ))
        evidence = capture(root, Path("pipeline.py"), 1, 6, symbol="grouped_training_pipeline", lesson_ids=["L001"])
        evidence["id"] = "CE001"
        evidence_path = root / "code_evidence.json"
        evidence_path.write_text(json.dumps({"code_evidence": [evidence]}, ensure_ascii=False), encoding="utf-8")
        record_experiment(record_args(
            workspace,
            run_id,
            id="E02",
            parent_id="E01",
            ablation_id="A001",
            component="features",
            hypothesis="Fold-safe encoding improves repeated-category generalization.",
            change="Enable out-of-fold target encoding inside each group split.",
            cv_mean=0.73,
            cv_std=0.008,
            fold_scores=[0.72, 0.73, 0.74],
            runtime_minutes=5.0,
            code_evidence_file=[evidence_path],
            code_version="demo124",
            data_version="data-v1",
            config_hash="cfg-v2",
            environment_hash="env-v1",
            fold_version="group-v1",
            metric_version="auc-v1",
            seeds=[42],
        ))
        analyze_experiment(argparse.Namespace(
            workspace=workspace,
            run_id=run_id,
            id="E02",
            verdict="supported",
            mechanism="Encoding is fitted inside each group-disjoint training fold, preventing target leakage.",
            confounder=["Needs confirmation on a second seed."],
            slice_finding=["Repeated-category slice improved."],
            resource_tradeoff="One additional preprocessing pass per fold.",
            next_action="Repeat with seed 31415.",
            notes="",
        ))
        experience_dir = workspace / "experience"
        draft_command(argparse.Namespace(
            workspace=workspace,
            run_id=run_id,
            profile=None,
            out_dir=experience_dir,
            title="Portable End-to-End Demo",
            competition_url="https://www.kaggle.com/competitions/portable-e2e-demo",
            final_rank="",
            medal="",
            summary="End-to-end portability and memory workflow fixture.",
            keyword=["group validation", "fold-safe encoding"],
        ))
        review, reviewed = review_command(argparse.Namespace(
            workspace=workspace,
            run_id=run_id,
            card=None,
            reviewer="evaluate-skill",
        ))
        promoted = promote_command(argparse.Namespace(
            workspace=workspace,
            run_id=run_id,
            card=None,
            knowledge_base=root / "knowledge_base",
            catalog=root / "learned_catalog.json",
        )) if reviewed else {}
        reports = workspace / "experiment_reports"
        gates["memory_and_distillation"] = {
            "passed": bool(reviewed and promoted.get("status") == "promoted")
            and (reports / "ablation_matrix.csv").exists()
            and (reports / "experiment_analysis_log.md").exists(),
            "review_score": review.get("score"),
            "code_evidence_count": 1,
        }

    return {
        "schema_version": 1,
        "passed": all(gate.get("passed") for gate in gates.values()),
        "elapsed_seconds": round(perf_counter() - started, 3),
        "gates": gates,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a no-Harness end-to-end Kaggle Grandmaster Playbook evaluation.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    payload = run_evaluation()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"end-to-end skill evaluation: {'PASS' if payload['passed'] else 'FAIL'} ({payload['elapsed_seconds']}s)")
        for name, gate in payload["gates"].items():
            print(f"{'PASS' if gate['passed'] else 'FAIL'} {name}")
    if args.strict and not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
