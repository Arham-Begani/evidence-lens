"""Human semantic review, checked against exact prompts and captured responses."""
import csv
import io
import random
from pathlib import Path
from statistics import mean

from .io import StudyError, canonical, digest, read_jsonl, strict_json, write_new, write_json
from .runner import parse_answer
from .study import verify_export

RATINGS = ("a_retained", "b_retained", "citations_supported", "false_independence", "unsupported_claim")
FIELDS = ("task_id", "task_sha256", "response_sha256", "a_reference", "b_reference", "b_expected",
          "evidence_json", "answer_json", "reviewer", *RATINGS, "notes")


def checked_responses(tasks, path):
    expected = {t["task_id"]: t for t in tasks}
    responses = {}
    for row in read_jsonl(path):
        tid = row.get("task_id")
        if tid not in expected or tid in responses:
            raise StudyError("Unknown or duplicate response task")
        if row.get("task_sha256") != expected[tid]["task_sha256"]:
            raise StudyError("Response belongs to a different prompt")
        if digest({k: v for k, v in row.items() if k != "response_sha256"}) != row.get("response_sha256"):
            raise StudyError("Response hash mismatch")
        if row.get("status") != "ok":
            raise StudyError("Run contains a failed generation; resolve it in a new run before scoring")
        answer = parse_answer(row.get("raw_response", ""))
        if answer != row.get("answer"):
            raise StudyError("Parsed and raw answers disagree")
        responses[tid] = row
    if responses.keys() != expected.keys():
        raise StudyError("Incomplete response set; all exported tasks are required")
    identities = {(r.get("backend"), r.get("model")) for r in responses.values()}
    if len(identities) != 1:
        raise StudyError("Mixed backends or models; use separate runs")
    if next(iter(identities))[0] not in {"engineering_fixture", "ollama_local"}:
        raise StudyError("Unrecognized response backend")
    if next(iter(identities))[0] == "ollama_local":
        run_identities = set()
        for row in responses.values():
            identity = row.get("model_identity")
            if not isinstance(identity, dict) or digest({k: v for k, v in identity.items() if k != "identity_sha256"}) != identity.get("identity_sha256"):
                raise StudyError("Missing or changed immutable model identity")
            if row.get("task_set_sha256") != digest(tasks):
                raise StudyError("Model run does not match the complete task set")
            if row.get("reported_model") not in {row["model"], identity.get("canonical_model")}:
                raise StudyError("Reported model differs from captured identity")
            run_identities.add((row.get("endpoint"), identity["identity_sha256"]))
        if len(run_identities) != 1:
            raise StudyError("Run mixes endpoints or immutable model identities")
    return responses


def citation_issues(task, answer):
    packet = strict_json(task["prompt"].split("\nEVIDENCE JSON\n", 1)[1])
    known = {d["id"] + ":" + p["id"] for d in packet["documents"] for p in d["passages"]}
    issues = []
    for index, claim in enumerate(answer["claims"]):
        if not claim["citations"]:
            issues.append({"claim_index": index, "problem": "missing_citation"})
        for citation in claim["citations"]:
            if citation not in known:
                issues.append({"claim_index": index, "problem": "unknown_citation", "citation": citation})
    return issues


def review_rows(export, response_path):
    manifest, tasks, keys = verify_export(export)
    responses = checked_responses(tasks, response_path)
    rows = []
    for task in tasks:
        key, response = keys[task["packet_id"]], responses[task["task_id"]]
        public = task["prompt"].split("\nEVIDENCE JSON\n", 1)[1]
        row = {"task_id": task["task_id"], "task_sha256": task["task_sha256"],
               "response_sha256": response["response_sha256"], "a_reference": key["a"],
               "b_reference": key["b"], "b_expected": str(int(key["b_expected"])),
               "evidence_json": public, "answer_json": canonical(response["answer"]),
               "reviewer": "", "notes": ""}
        row.update({field: "" for field in RATINGS})
        rows.append(row)
    random.Random(17).shuffle(rows)  # Hide the repeating method order from reviewers.
    return manifest, tasks, keys, responses, rows


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def create_review(export, response_path, output):
    *_, rows = review_rows(export, response_path)
    write_new(output, csv_text(rows))
    return {"review_rows": len(rows), "status": "awaiting_semantic_review"}


def score_review(export, response_path, review_path, review_pair=None):
    manifest, tasks, keys, responses, expected_rows = review_rows(export, response_path)
    expected = {r["task_id"]: r for r in expected_rows}
    task_map = {t["task_id"]: t for t in tasks}
    csv.field_size_limit(2_000_000)
    with Path(review_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise StudyError("Review columns differ from the generated template")
        rows = list(reader)
    seen, observations, reviewers = set(), [], set()
    fixed = set(FIELDS) - {*RATINGS, "reviewer", "notes"}
    for row in rows:
        tid = row.get("task_id")
        if tid not in expected or tid in seen:
            raise StudyError("Unknown or duplicate review row")
        seen.add(tid)
        if any(row[f] != expected[tid][f] for f in fixed):
            raise StudyError("Review evidence, reference or hash changed")
        if not row["reviewer"].strip() or not row["notes"].strip():
            raise StudyError("Every review needs a reviewer identifier and rationale")
        if any(row[f] not in {"0", "1"} for f in RATINGS):
            raise StudyError("Every semantic rating must be 0 or 1; blanks are not zero")
        values = {f: int(row[f]) for f in RATINGS}
        task = task_map[tid]
        if values["citations_supported"] and citation_issues(task, responses[tid]["answer"]):
            raise StudyError("Citation rating contradicts missing or nonexistent passage citations")
        key = keys[task["packet_id"]]
        if not key["b_expected"] and values["b_retained"] and not values["unsupported_claim"]:
            raise StudyError("B asserted without supplied B must be marked unsupported")
        joint = (values["a_retained"] and values["citations_supported"] and not values["false_independence"]
                 and not values["unsupported_claim"] and values["b_retained"] == int(key["b_expected"]))
        observations.append({"family": key["family"], "method": task["method"], "condition": key["condition"],
                             "order": key["order"], **values, "joint_success": int(joint)})
        reviewers.add(row["reviewer"].strip())
    if seen != expected.keys():
        raise StudyError("Incomplete reviews; every task is required")
    groups = {}
    for obs in observations:
        groups.setdefault((obs["family"], obs["method"], obs["condition"]), []).append(obs)
    family_scores = []
    for (family, method, condition), group in sorted(groups.items()):
        if sorted(o["order"] for o in group) != [0, 1]:
            raise StudyError("Every family/method/condition needs both document orders")
        family_scores.append({"family": family, "method": method, "condition": condition,
                              **{f: mean(o[f] for o in group) for f in (*RATINGS, "joint_success")}})
    summary = []
    for method in manifest["methods"]:
        for condition in manifest["conditions"]:
            group = [s for s in family_scores if s["method"] == method and s["condition"] == condition]
            summary.append({"method": method, "condition": condition, "families": len(group),
                            **{f: mean(s[f] for s in group) for f in (*RATINGS, "joint_success")}})
    changes = []
    index = {(s["family"], s["method"], s["condition"]): s for s in family_scores}
    for family in sorted({s["family"] for s in family_scores}):
        for method in manifest["methods"]:
            get = lambda condition: index[family, method, condition]
            changes.append({"family": family, "method": method,
                            "b_retention_mixed_minus_new": get("mixed")["b_retained"] - get("new")["b_retained"],
                            "false_independence_repeat_minus_base": get("repeat")["false_independence"] - get("base")["false_independence"]})
    backend = next(iter(responses.values()))["backend"]
    review_process = {"kind": "single_review_file", "independence_authenticated": False}
    if review_pair is not None:
        comparison, first, second = compare_review_data(export, response_path, *review_pair)
        final = {r["task_id"]: r for r in rows}
        for tid in first:
            for field in RATINGS:
                if first[tid][field] == second[tid][field] and final[tid][field] != first[tid][field]:
                    raise StudyError("Adjudication changed an agreed rating; revise and preserve the initial reviews explicitly")
        review_process = {"kind": "declared_double_review_adjudication", "independence_authenticated": False,
                          "initial_reviewers": comparison["reviewers"], "comparison": comparison}
    return {"schema_version": 2, "kind": "engineering_fixture" if backend == "engineering_fixture" else "reviewed_model_run",
            "model": next(iter(responses.values()))["model"], "annotation_status": manifest["annotation_status"],
            "reviewers": sorted(reviewers), "task_count": len(tasks), "family_count": manifest["family_count"],
            "export_sha256": digest(manifest), "responses_sha256": digest(list(responses.values())),
            "review_sha256": digest(rows), "summary": summary, "family_scores": family_scores,
            "review_process": review_process,
            "paired_changes": changes,
            "limitations": manifest["limitations"] + ["Descriptive results only; no significance or generalization claim",
                "Orders are averaged within source family; they are not independent samples",
                "Reviewer identities are recorded, not externally authenticated",
                "Review records do not by themselves establish independent human review"]}


def read_review_csv(path):
    csv.field_size_limit(2_000_000)
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def compare_review_data(export, response_path, first_path, second_path):
    first_result = score_review(export, response_path, first_path)
    second_result = score_review(export, response_path, second_path)
    reviewers = [first_result["reviewers"], second_result["reviewers"]]
    if any(len(ids) != 1 for ids in reviewers) or reviewers[0] == reviewers[1]:
        raise StudyError("Two review files need distinct single reviewer identifiers")
    first = {r["task_id"]: r for r in read_review_csv(first_path)}
    second = {r["task_id"]: r for r in read_review_csv(second_path)}
    disagreements = [{"task_id": tid, "fields": [f for f in RATINGS if first[tid][f] != second[tid][f]]}
                     for tid in sorted(first) if any(first[tid][f] != second[tid][f] for f in RATINGS)]
    comparison = {"kind": "review_comparison", "reviewers": [ids[0] for ids in reviewers],
                  "initial_review_sha256": [first_result["review_sha256"], second_result["review_sha256"]],
                  "task_count": len(first), "disagreements": disagreements,
                  "rating_agreement": {f: {"agreed": sum(first[t][f] == second[t][f] for t in first),
                                            "total": len(first)} for f in RATINGS},
                  "independence_authenticated": False}
    return comparison, first, second


def compare_reviews(export, response_path, first_path, second_path, output):
    comparison, first, second = compare_review_data(export, response_path, first_path, second_path)
    root = Path(output)
    if root.exists():
        raise StudyError("Review-comparison directory exists")
    rows = []
    for tid, initial in first.items():
        row = initial.copy()
        for field in RATINGS:
            row[field] = initial[field] if initial[field] == second[tid][field] else ""
        row["reviewer"] = ""
        row["notes"] = ""
        rows.append(row)
    root.mkdir(parents=True)
    write_json(root / "comparison.json", comparison)
    write_new(root / "adjudication-blank.csv", csv_text(rows))
    return comparison
