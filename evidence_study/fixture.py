"""Scripted engineering checks, deliberately never labeled as model evaluations."""
from pathlib import Path

from .io import canonical, digest, write_json, write_jsonl, write_new
from .review import csv_text, review_rows, score_review
from .study import verify_export


def build_fixture(export, output, mode="correct"):
    if mode not in {"correct", "omit_b", "false_corroboration", "abstain"}:
        raise ValueError("Unknown fixture mode")
    _, tasks, keys = verify_export(export)
    root = Path(output)
    if root.exists():
        from .io import StudyError
        raise StudyError("Fixture directory exists; use a new path")
    root.mkdir(parents=True)
    responses = []
    for task in tasks:
        key = keys[task["packet_id"]]
        inflated = mode == "false_corroboration" and key["condition"] in {"repeat", "mixed"}
        claims = [{"text": key["a"], "citations": key["a_citations"],
                   "reporting_relationship": "Two independent observations corroborate this claim." if inflated else
                   "One supplied reporting origin; independent observations are not established."}]
        if key["b_expected"] and mode != "omit_b":
            claims.append({"text": key["b"], "citations": key["b_citations"],
                           "reporting_relationship": "An additional proposition from the same cited reporting."})
        if mode == "abstain":
            claims = []
        answer = {"evidence_record": [], "claims": claims, "limitations": "SCRIPTED ENGINEERING FIXTURE. No model was called."}
        record = {"task_id": task["task_id"], "task_sha256": task["task_sha256"], "backend": "engineering_fixture",
                  "model": "scripted-" + mode, "status": "ok", "raw_response": canonical(answer), "answer": answer}
        record["response_sha256"] = digest(record)
        responses.append(record)
    write_jsonl(root / "responses.jsonl", responses)
    *_, rows = review_rows(export, root / "responses.jsonl")
    task_map = {t["task_id"]: t for t in tasks}
    for row in rows:
        key = keys[task_map[row["task_id"]]["packet_id"]]
        row.update(reviewer="SCRIPTED_FIXTURE_NOT_HUMAN", notes="Known engineered behavior; no semantic human review.",
                   a_retained=str(int(mode != "abstain")),
                   b_retained=str(int(key["b_expected"] and mode not in {"omit_b", "abstain"})),
                   citations_supported="1", unsupported_claim="0",
                   false_independence=str(int(mode == "false_corroboration" and key["condition"] in {"repeat", "mixed"})))
    write_new(root / "reviews.csv", csv_text(rows))
    result = score_review(export, root / "responses.jsonl", root / "reviews.csv")
    write_json(root / "results.json", result)
    return result
