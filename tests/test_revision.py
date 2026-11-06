import copy
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from evidence_study.fixture import build_fixture
from evidence_study.io import StudyError, canonical, digest, read_json, read_jsonl, strict_json, write_jsonl
from evidence_study.review import compare_reviews, csv_text, read_review_csv, score_review
from evidence_study.runner import run_local
from evidence_study.study import export_study, load_dataset, verify_export
from test_workflow import DATA, ModelMetadataHandler, exported


def test_prompt_freeze_survives_current_prompt_edits(exported, monkeypatch):
    import evidence_study.study as study
    monkeypatch.setattr(study, "COMMON", "Future common prompt")
    monkeypatch.setattr(study, "METHODS", {"future": "Different method"})
    manifest, tasks, _ = verify_export(exported)
    assert manifest["schema_version"] == 2 and len(tasks) == 192


def test_reproducible_shuffled_execution(exported, tmp_path):
    another = tmp_path / "another"
    export_study(load_dataset(DATA), another)
    first = read_jsonl(exported / "tasks.jsonl")
    assert first == read_jsonl(another / "tasks.jsonl")
    assert len({t["packet_id"] for t in first[:4]}) > 1



def test_actor_context_is_fixed_across_conditions():
    from evidence_study.study import packet, CONDITIONS
    data = load_dataset(DATA.parent / "cases-v2.json")
    for case in data["families"]:
        contexts = []
        for condition in CONDITIONS:
            for order in (0, 1):
                public, _ = packet(case, condition, order)
                assert public["documents"][0]["id"] == "d0"
                contexts.append(public["documents"][0])
        assert all(context == contexts[0] for context in contexts)
        assert contexts[0]["passages"][0]["text"].strip()


@pytest.mark.parametrize("bad_json", ['{"claims": [], "claims": [1]}', '{"x": {"a": 1, "a": 2}}', '{"x": Infinity}'])
def test_ambiguous_json_rejected(bad_json):
    with pytest.raises(StudyError): strict_json(bad_json)


@pytest.mark.parametrize("mutation,message", [("source_url", "source URL"), ("empty_locator", "locators"),
                                             ("same_fact", "distinct proposition"), ("blank_reviewers", "nonempty strings")])
def test_dataset_annotations_have_structural_guards(tmp_path, mutation, message):
    data = load_dataset(DATA)
    case = data["families"][1]
    if mutation == "source_url": case["source"]["url"] = data["families"][0]["source"]["url"] + "#section"
    if mutation == "empty_locator": case["locators"]["b"] = " "
    if mutation == "same_fact": case["b"] = case["a"]
    if mutation == "blank_reviewers": case.update(annotation_status="adjudicated", reviewers=["", " "])
    with pytest.raises(StudyError, match=message): export_study(data, tmp_path / "bad")


def test_nonexistent_citations_cannot_get_passing_review(exported, tmp_path):
    fixture = tmp_path / "fixture"; build_fixture(exported, fixture)
    responses = read_jsonl(fixture / "responses.jsonl")
    responses[0]["answer"]["claims"][0]["citations"] = ["d99:p99"]
    responses[0]["raw_response"] = canonical(responses[0]["answer"])
    responses[0]["response_sha256"] = digest({k: v for k, v in responses[0].items() if k != "response_sha256"})
    changed = tmp_path / "changed.jsonl"; write_jsonl(changed, responses)
    rows = read_review_csv(fixture / "reviews.csv")
    for row in rows:
        if row["task_id"] == responses[0]["task_id"]:
            row["answer_json"] = canonical(responses[0]["answer"])
            row["response_sha256"] = responses[0]["response_sha256"]
    review = tmp_path / "changed.csv"; review.write_text(csv_text(rows), encoding="utf-8")
    with pytest.raises(StudyError, match="Citation rating contradicts"):
        score_review(exported, changed, review)


def test_two_reviews_and_explicit_adjudication(exported, tmp_path):
    fixture = tmp_path / "fixture"; build_fixture(exported, fixture)
    original = read_review_csv(fixture / "reviews.csv")
    first, second = copy.deepcopy(original), copy.deepcopy(original)
    for row in first: row["reviewer"] = "SCRIPTED_REVIEWER_A"
    for row in second: row["reviewer"] = "SCRIPTED_REVIEWER_B"
    second[0]["a_retained"] = "0"
    a = tmp_path / "a.csv"; b = tmp_path / "b.csv"
    a.write_text(csv_text(first), encoding="utf-8"); b.write_text(csv_text(second), encoding="utf-8")
    compare = tmp_path / "compare"
    result = compare_reviews(exported, fixture / "responses.jsonl", a, b, compare)
    assert len(result["disagreements"]) == 1
    final = read_review_csv(compare / "adjudication-blank.csv")
    assert next(row for row in final if row["task_id"] == first[0]["task_id"])["a_retained"] == ""
    for row in final:
        row["reviewer"] = "SCRIPTED_ADJUDICATOR"
        row["notes"] = "Scripted adjudication tests plumbing, not independent human review."
        if row["a_retained"] == "": row["a_retained"] = "1"
    finished = tmp_path / "adjudicated.csv"; finished.write_text(csv_text(final), encoding="utf-8")
    scored = score_review(exported, fixture / "responses.jsonl", finished, [a, b])
    assert scored["review_process"]["kind"] == "declared_double_review_adjudication"
    assert scored["kind"] == "engineering_fixture"
    final[-1]["a_retained"] = "0"
    finished.write_text(csv_text(final), encoding="utf-8")
    with pytest.raises(StudyError, match="changed an agreed rating"):
        score_review(exported, fixture / "responses.jsonl", finished, [a, b])
    with pytest.raises(StudyError, match="distinct single reviewer"):
        compare_reviews(exported, fixture / "responses.jsonl", a, a, tmp_path / "same")


def test_model_digest_change_prevents_resume(exported, tmp_path):
    _, tasks, _ = verify_export(exported)
    calls = []
    class Handler(ModelMetadataHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            calls.append(self.path)
            payload = canonical({"model": self.model_name, "response": canonical({"evidence_record": [], "claims": [], "limitations": "mock"}),
                                 "done": True, "done_reason": "stop"}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    try:
        output = tmp_path / "responses.jsonl"
        run_local(tasks[:2], output, "mock-test", endpoint, limit=1)
        Handler.model_digest = "b" * 64
        with pytest.raises(StudyError, match="identity changed"):
            run_local(tasks[:2], output, "mock-test", endpoint, resume=True)
        assert len(calls) == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=3)
