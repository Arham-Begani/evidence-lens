"""Validate bounded Codex development outputs independently of the process runner."""
from pathlib import Path
import re

from .io import StudyError, digest, read_json, read_jsonl
from .review import citation_issues
from .runner import parse_answer


def development_prompt(task):
    sentence = "The whole response has the same configured token cap for every method."
    if task["prompt"].count(sentence) != 1:
        raise StudyError("Unexpected source prompt; development adapter must be reviewed")
    return ("This is a bounded development-only inference check. Do not use tools, read files, browse, run commands, or delegate. "
            "Answer only from the supplied evidence.\n\n" + task["prompt"].replace(sentence,
            "Keep the evidence record concise; this development adapter does not enforce a total output-token cap."))


def validate_development_output(directory, task, plan, condition=None):
    directory = Path(directory)
    record = read_json(directory / "validation.json")
    prompt = (directory / "prompt.txt").read_text(encoding="utf-8-sig")
    expected = development_prompt(task)
    if prompt != expected or record.get("actual_prompt_sha256") != digest(expected):
        raise StudyError("Development prompt changed")
    if record.get("task_id") != task["task_id"] or record.get("original_task_sha256") != task["task_sha256"]:
        raise StudyError("Development task identity mismatch")
    if task["task_id"] not in plan["task_ids"] or record.get("method") != task["method"]:
        raise StudyError("Development method or plan membership mismatch")
    if condition is not None and record.get("condition") != condition:
        raise StudyError("Development condition label mismatch")
    for field in ("requested_model", "cli_version", "reasoning_effort"):
        if record.get(field) != plan.get(field):
            raise StudyError(f"Development {field} differs from frozen plan")
    if record.get("returncode") != 0 or record.get("status") != "completed":
        raise StudyError("Development process or validation did not complete successfully")
    events = read_jsonl(directory / "events.jsonl")
    if not events or events[-1].get("type") != "turn.completed":
        raise StudyError("Missing completed-turn evidence")
    if sum(e.get("type") == "turn.completed" for e in events) != 1:
        raise StudyError("Expected exactly one completed turn")
    if any(e.get("type") == "turn.failed" for e in events):
        raise StudyError("Failed-turn event appears in output")
    if any(e.get("item", {}).get("type") != "agent_message" for e in events if "item" in e):
        raise StudyError("Unexpected tool or non-answer event")
    messages = [e["item"]["text"] for e in events if e.get("type") == "item.completed"]
    if len(messages) != 1:
        raise StudyError("Expected exactly one completed answer")
    answer_index = next(i for i, e in enumerate(events) if e.get("type") == "item.completed")
    reconnects = []
    for index, event in enumerate(events):
        if event.get("type") != "error":
            continue
        message = event.get("message", "")
        if index >= answer_index or not re.fullmatch(r"Reconnecting\.\.\. [1-9][0-9]*/[1-9][0-9]* \(stream disconnected before completion: .+\)", message):
            raise StudyError("Unclassified error event in model output")
        reconnects.append({"event_index": index, "message": message})
    answer = parse_answer(messages[0])
    if read_json(directory / "answer.json") != answer or record.get("response") != answer:
        raise StudyError("Answer, event stream and validation record disagree")
    if record.get("answer_sha256") != digest(answer):
        raise StudyError("Development answer hash mismatch")
    usage = events[-1].get("usage", {})
    if (not isinstance(usage, dict) or not {"input_tokens", "output_tokens"}.issubset(usage)
            or any(type(v) is not int or v < 0 for v in usage.values())
            or usage.get("cached_input_tokens", 0) > usage.get("input_tokens", 0)):
        raise StudyError("Malformed token-usage record")
    if usage != record.get("token_usage"):
        raise StudyError("Token usage differs from event stream")
    issues = citation_issues(task, answer)
    if issues != record.get("citation_issues") or record.get("tool_events") != 0:
        raise StudyError("Development validation flags disagree with captured output")
    return {**record, "reverified": True, "recovered_transport_events": reconnects}
