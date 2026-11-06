import copy
import csv
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from evidence_study.cli import main
from evidence_study.fixture import build_fixture
from evidence_study.io import StudyError, canonical, digest, read_jsonl, write_jsonl
from evidence_study.provenance import resolve_origins
from evidence_study.report import render_report
from evidence_study.review import create_review, csv_text, score_review
from evidence_study.runner import local_endpoint, parse_answer, run_local
from evidence_study.study import export_study, load_dataset, verify_export

DATA = Path(__file__).resolve().parents[1] / "data" / "cases.json"


class ModelMetadataHandler(BaseHTTPRequestHandler):
    model_name = "mock-test"
    model_digest = "a" * 64

    def do_GET(self):
        value = {"version": "test-1"} if self.path == "/api/version" else {
            "models": [{"name": self.model_name, "model": self.model_name, "digest": self.model_digest,
                        "details": {"quantization_level": "MOCK"}}]}
        payload = canonical(value).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)


@pytest.fixture
def exported(tmp_path):
    target = tmp_path / "export"
    export_study(load_dataset(DATA), target)
    return target


def test_export_dimensions_and_no_answer_key_in_prompts(exported):
    manifest, tasks, keys = verify_export(exported)
    assert (manifest["family_count"], manifest["packet_count"], len(tasks)) == (6, 48, 192)
    assert len({t["task_id"] for t in tasks}) == 192
    for task in tasks:
        public = json.loads(task["prompt"].split("\nEVIDENCE JSON\n")[1])
        assert not {"b_expected", "condition", "annotation_status", "split", "locators"} & public.keys()
        assert keys[task["packet_id"]]["b_expected"] == any("Source of this fact:" in p["text"] for d in public["documents"] for p in d["passages"])


def test_no_overwrite(exported):
    original = (exported / "manifest.json").read_bytes()
    with pytest.raises(StudyError, match="already exists"):
        export_study(load_dataset(DATA), exported)
    assert original == (exported / "manifest.json").read_bytes()


def test_changed_export_rejected(exported):
    path = exported / "tasks.jsonl"
    path.write_text(path.read_text().replace("ONLY", "ALSO", 1))
    with pytest.raises(StudyError, match="Changed tasks"):
        verify_export(exported)


def test_source_family_leakage_rejected(tmp_path):
    data = load_dataset(DATA)
    extra = copy.deepcopy(data["families"][0]); extra["id"] = "different_id"; extra["split"] = "evaluation_candidate"
    data["families"].append(extra)
    with pytest.raises(StudyError, match="Duplicate source family"):
        export_study(data, tmp_path / "export")


def test_unreviewed_adjudication_rejected(tmp_path):
    data = load_dataset(DATA)
    data["families"][0]["annotation_status"] = "adjudicated"
    with pytest.raises(StudyError, match="two distinct"):
        export_study(data, tmp_path / "export")


@pytest.mark.parametrize("mode", ["correct", "omit_b", "false_corroboration", "abstain"])
def test_engineered_failure_modes(exported, tmp_path, mode):
    result = build_fixture(exported, tmp_path / mode, mode)
    assert result["kind"] == "engineering_fixture"
    assert len(result["family_scores"]) == 96  # Orders collapse, never count as independent families.
    for row in result["summary"]:
        expected = mode == "correct" or (mode == "omit_b" and row["condition"] in {"base", "repeat"}) or (mode == "false_corroboration" and row["condition"] in {"base", "new"})
        assert row["joint_success"] == int(expected)
        assert row["families"] == 6
    if mode == "abstain":
        assert all(row["false_independence"] == 0 and row["joint_success"] == 0 for row in result["summary"])


def read_csv(path):
    csv.field_size_limit(2_000_000)
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize("mutation,message", [("missing", "Incomplete reviews"), ("duplicate", "duplicate review"),
    ("blank", "Every semantic rating"), ("reference", "Review evidence"), ("hash", "Review evidence")])
def test_review_errors_rejected(exported, tmp_path, mutation, message):
    root = tmp_path / "fixture"
    build_fixture(exported, root)
    rows = read_csv(root / "reviews.csv")
    if mutation == "missing": rows.pop()
    if mutation == "duplicate": rows.append(rows[0])
    if mutation == "blank": rows[0]["a_retained"] = ""
    if mutation == "reference": rows[0]["b_reference"] = "Changed truth"
    if mutation == "hash": rows[0]["response_sha256"] = "0" * 64
    review = tmp_path / "changed.csv"; review.write_text(csv_text(rows), encoding="utf-8")
    with pytest.raises(StudyError, match=message):
        score_review(exported, root / "responses.jsonl", review)


def test_missing_and_changed_response_rejected(exported, tmp_path):
    root = tmp_path / "fixture"; build_fixture(exported, root)
    rows = read_jsonl(root / "responses.jsonl")
    short = tmp_path / "short.jsonl"; write_jsonl(short, rows[:-1])
    with pytest.raises(StudyError, match="Incomplete response"):
        create_review(exported, short, tmp_path / "review.csv")
    rows[0]["raw_response"] = "changed"
    changed = tmp_path / "changed.jsonl"; write_jsonl(changed, rows)
    with pytest.raises(StudyError, match="Response hash"):
        create_review(exported, changed, tmp_path / "review.csv")


def test_empty_review_is_not_a_score(exported, tmp_path):
    root = tmp_path / "fixture"; build_fixture(exported, root)
    review = tmp_path / "blank.csv"
    create_review(exported, root / "responses.jsonl", review)
    assert "ordinary" not in read_csv(review)[0]["evidence_json"]
    with pytest.raises(StudyError, match="reviewer identifier"):
        score_review(exported, root / "responses.jsonl", review)


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost:11434", "http://127.0.0.1.example.com:1234",
    "http://user@127.0.0.1:1234", "http://127.0.0.1:1234/x", "http://127.0.0.1:1234/?q=1", "http://127.0.0.1"])
def test_endpoint_cannot_escape_loopback(url):
    with pytest.raises(StudyError): local_endpoint(url)


def test_response_schema_limits():
    with pytest.raises(StudyError): parse_answer('{"claims": []}')
    with pytest.raises(StudyError): parse_answer(canonical({"evidence_record": [], "claims": [], "limitations": "word " * 251}))
    with pytest.raises(StudyError): parse_answer(canonical({"evidence_record": [], "claims": [{"text":"a", "citations": "d1:p1", "reporting_relationship":"unknown"}], "limitations":""}))


def test_local_adapter_roundtrip_and_resume(exported, tmp_path):
    _, tasks, _ = verify_export(exported)
    tasks = tasks[:2]
    calls = []
    answer = {"evidence_record": [], "claims": [], "limitations": "MOCK HTTP ADAPTER TEST; no model inference."}
    class Handler(ModelMetadataHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            payload = canonical({"model": "mock-test", "response": canonical(answer), "done": True,
                                 "done_reason": "stop", "eval_count": 8, "prompt_eval_count": 20}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    try:
        output = tmp_path / "responses.jsonl"
        run_local(tasks, output, "mock-test", endpoint, limit=1)
        run_local(tasks, output, "mock-test", endpoint, resume=True)
        run_local(tasks, output, "mock-test", endpoint, resume=True)
        assert len(calls) == 2
        assert calls[0][0] == "/api/generate"
        assert calls[0][1]["options"] == {"temperature": 0, "seed": 17, "num_predict": 1500}
        assert len(read_jsonl(output)) == 2
        with pytest.raises(StudyError, match="mismatch"):
            run_local(tasks, output, "different-model", endpoint, resume=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_html_escapes_model_metadata(exported, tmp_path):
    result = build_fixture(exported, tmp_path / "fixture")
    result["model"] = "<script>alert(1)</script>"
    report = tmp_path / "report.html"; render_report(result, report)
    text = report.read_text(encoding="utf-8")
    assert "&lt;script&gt;" in text and "<script>" not in text
    assert "no model results" in text


def test_cli_error_is_nonzero(tmp_path):
    assert main(["validate", str(tmp_path / "missing.json")]) == 2


@pytest.mark.parametrize("failure", ["redirect", "truncated", "invalid_json"])
def test_local_adapter_preserves_failure_and_stops(exported, tmp_path, failure):
    _, tasks, _ = verify_export(exported)
    calls = []
    class Handler(ModelMetadataHandler):
        model_name = "mock-failure"
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            if failure == "redirect":
                self.send_response(302)
                self.send_header("Location", "https://example.invalid/not-allowed")
                self.end_headers()
            else:
                answer = {"evidence_record": [], "claims": [], "limitations": "mock"}
                payload = canonical({"model": self.model_name, "response": "not json" if failure == "invalid_json" else canonical(answer),
                                     "done": True, "done_reason": "length" if failure == "truncated" else "stop"}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    output = tmp_path / "failed.jsonl"
    try:
        result = run_local(tasks[:2], output, "mock-failure", endpoint)
        rows = read_jsonl(output)
        assert len(calls) == 1 and len(rows) == 1
        assert result["errors"] == 1 and not result["complete"] and result["remaining"] == 2
        assert result["remaining_unattempted"] == 1
        assert rows[0]["status"] == "error"
        if failure == "redirect": assert "Redirects are disabled" in rows[0]["error"]
        with pytest.raises(StudyError, match="contains a failure"):
            run_local(tasks[:2], output, "mock-failure", endpoint, resume=True)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)


def test_non_finite_model_json_rejected():
    with pytest.raises(StudyError, match="Non-finite"):
        parse_answer('{"evidence_record": [NaN], "claims": [], "limitations": ""}')
