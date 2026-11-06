import json

import pytest

from evidence_study.development import development_prompt, validate_development_output
from evidence_study.io import StudyError, canonical, digest, read_json, write_json, write_jsonl, write_new
from evidence_study.study import verify_export
from test_workflow import exported


def make_saved_output(export, directory):
    _, tasks, keys = verify_export(export)
    task = tasks[0]
    answer = {"evidence_record": [], "claims": [], "limitations": "Engineering fixture, not model inference."}
    prompt = development_prompt(task)
    plan = {"requested_model": "test-model", "cli_version": "test-version", "reasoning_effort": "high", "task_ids": [task["task_id"]]}
    usage = {"input_tokens": 30, "output_tokens": 20}
    record = {"task_id": task["task_id"], "original_task_sha256": task["task_sha256"], "actual_prompt_sha256": digest(prompt),
              "method": task["method"], "condition": keys[task["packet_id"]]["condition"],
              **{k: v for k, v in plan.items() if k != "task_ids"}, "returncode": 0, "status": "completed", "response": answer,
              "answer_sha256": digest(answer), "token_usage": usage, "citation_issues": [], "tool_events": 0}
    events = [{"type": "thread.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": canonical(answer)}},
              {"type": "turn.completed", "usage": usage}]
    write_new(directory / "prompt.txt", prompt)
    write_json(directory / "answer.json", answer)
    write_json(directory / "validation.json", record)
    write_jsonl(directory / "events.jsonl", events)
    return task, plan, record, events


def test_saved_output_can_be_reverified_without_calling_a_model(exported, tmp_path):
    directory = tmp_path / "saved"
    task, plan, record, _ = make_saved_output(exported, directory)
    result = validate_development_output(directory, task, plan, record["condition"])
    assert result["reverified"] is True


@pytest.mark.parametrize("change,message", [("prompt", "prompt changed"), ("method", "method"), ("version", "cli_version"),
    ("answer", "disagree"), ("usage", "Token usage"), ("started_tool", "Unexpected tool"), ("incomplete", "completed-turn"),
    ("condition", "condition label")])
def test_corrupted_or_incomplete_saved_outputs_are_rejected(exported, tmp_path, change, message):
    directory = tmp_path / "saved"
    task, plan, record, events = make_saved_output(exported, directory)
    condition = record["condition"]
    if change == "prompt": (directory / "prompt.txt").write_text("different prompt", encoding="utf-8")
    if change == "method": record["method"] = "wrong"
    if change == "version": record["cli_version"] = "different"
    if change == "answer": record["response"]["limitations"] = "changed"
    if change == "usage": record["token_usage"] = {"input_tokens": 999, "output_tokens": 20}
    if change == "started_tool": events.insert(1, {"type": "item.started", "item": {"type": "command_execution", "command": "must not run"}})
    if change == "incomplete": events.pop()
    if change == "condition": condition = "not-this-condition"
    (directory / "validation.json").write_text(json.dumps(record), encoding="utf-8")
    (directory / "events.jsonl").write_text("\n".join(canonical(e) for e in events), encoding="utf-8")
    with pytest.raises(StudyError, match=message):
        validate_development_output(directory, task, plan, condition)


def test_completed_transport_recovery_is_retained_as_a_warning(exported, tmp_path):
    directory = tmp_path / "saved"
    task, plan, record, events = make_saved_output(exported, directory)
    events.insert(1, {"type": "error", "message": "Reconnecting... 2/5 (stream disconnected before completion: No such host is known. (os error 11001))"})
    (directory / "events.jsonl").write_text("\n".join(canonical(e) for e in events), encoding="utf-8")
    result = validate_development_output(directory, task, plan, record["condition"])
    assert len(result["recovered_transport_events"]) == 1


@pytest.mark.parametrize("event", [{"type": "error", "message": "Unauthorized"}, {"type": "turn.failed", "error": "network failure"}])
def test_unknown_and_terminal_errors_are_not_silently_accepted(exported, tmp_path, event):
    directory = tmp_path / "saved"
    task, plan, record, events = make_saved_output(exported, directory)
    events.insert(1, event)
    (directory / "events.jsonl").write_text("\n".join(canonical(e) for e in events), encoding="utf-8")
    with pytest.raises(StudyError, match="error event|Failed-turn"):
        validate_development_output(directory, task, plan, record["condition"])


@pytest.mark.parametrize("usage", [{}, {"input_tokens": 30}, {"output_tokens": 20},
    {"input_tokens": 30, "output_tokens": 20, "cached_input_tokens": 31},
    {"input_tokens": True, "output_tokens": 20}])
def test_matching_but_missing_or_impossible_usage_is_rejected(exported, tmp_path, usage):
    directory = tmp_path / "saved"
    task, plan, record, events = make_saved_output(exported, directory)
    record["token_usage"] = usage
    events[-1]["usage"] = usage
    (directory / "validation.json").write_text(json.dumps(record), encoding="utf-8")
    (directory / "events.jsonl").write_text("\n".join(canonical(e) for e in events), encoding="utf-8")
    with pytest.raises(StudyError, match="Malformed token-usage"):
        validate_development_output(directory, task, plan, record["condition"])


def test_ambiguous_multiple_completed_turns_are_rejected(exported, tmp_path):
    directory = tmp_path / "saved"
    task, plan, record, events = make_saved_output(exported, directory)
    events.insert(1, {"type": "turn.completed", "usage": record["token_usage"]})
    (directory / "events.jsonl").write_text("\n".join(canonical(e) for e in events), encoding="utf-8")
    with pytest.raises(StudyError, match="exactly one completed turn"):
        validate_development_output(directory, task, plan, record["condition"])
