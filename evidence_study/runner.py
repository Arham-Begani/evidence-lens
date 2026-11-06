"""Loopback-only Ollama adapter; never downloads models or uses credentials."""
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from .io import StudyError, canonical, digest, read_jsonl, strict_json


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise StudyError("Redirects are disabled for local model calls")


def local_endpoint(value):
    parsed = urlparse(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise StudyError("Only a literal loopback HTTP server is supported, e.g. http://127.0.0.1:11434")
    try:
        port = parsed.port
    except ValueError as error:
        raise StudyError("Invalid port") from error
    if port is None or port == 0:
        raise StudyError("Specify the local server port")
    return value.rstrip("/") + "/api/generate"


def parse_answer(raw):
    answer = strict_json(raw)
    if not isinstance(answer, dict) or set(answer) != {"evidence_record", "claims", "limitations"}:
        raise StudyError("Response must have evidence_record, claims and limitations only")
    if not isinstance(answer["evidence_record"], list) or not isinstance(answer["limitations"], str):
        raise StudyError("Invalid evidence_record or limitations")
    if not isinstance(answer["claims"], list) or len(answer["claims"]) > 4:
        raise StudyError("Expected at most four claims")
    for claim in answer["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"text", "citations", "reporting_relationship"}:
            raise StudyError("Invalid claim fields")
        if not all(isinstance(claim[k], str) for k in ("text", "reporting_relationship")):
            raise StudyError("Claim text and reporting relationship must be strings")
        if not isinstance(claim["citations"], list) or not all(isinstance(c, str) for c in claim["citations"]):
            raise StudyError("Citations must be strings")
    words = " ".join(c["text"] + " " + c["reporting_relationship"] for c in answer["claims"]) + " " + answer["limitations"]
    if len(words.split()) > 250:
        raise StudyError("Assessment exceeds 250 words")
    return answer


def model_identity(opener, endpoint, model, timeout):
    """Resolve an installed model tag without pulling it or inspecting credentials."""
    base = local_endpoint(endpoint).rsplit("/", 1)[0]
    def fetch(path):
        with opener.open(base + path, timeout=timeout) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise StudyError("Model metadata response too large")
        return strict_json(payload)
    models = fetch("/tags").get("models", [])
    candidates = [m for m in models if model in {m.get("name"), m.get("model")}
                  or (":" not in model and model + ":latest" in {m.get("name"), m.get("model")})]
    if len(candidates) != 1:
        raise StudyError("Requested model is not uniquely installed; no download was attempted")
    item = candidates[0]
    if "cloud" in model.lower() or item.get("remote_host") or item.get("remote_model"):
        raise StudyError("Cloud-backed models are outside this local-only runner")
    if not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", item.get("digest", "")):
        raise StudyError("Installed model has no valid immutable digest")
    version = fetch("/version").get("version")
    if not isinstance(version, str) or not version:
        raise StudyError("Ollama version is missing")
    identity = {"model_digest": item["digest"], "canonical_model": item.get("name") or item.get("model"),
                "model_details": item.get("details", {}), "ollama_version": version}
    identity["identity_sha256"] = digest(identity)
    return identity


def run_local(tasks, output, model, endpoint="http://127.0.0.1:11434", timeout=120, resume=False, limit=None):
    url = local_endpoint(endpoint)
    if not model.strip() or not 1 <= timeout <= 3600:
        raise StudyError("Model and valid timeout are required")
    if limit is not None and limit < 1:
        raise StudyError("Limit must be positive")
    path = Path(output)
    if path.exists() and not resume:
        raise StudyError("Response file exists; explicit --resume is required")
    expected = {t["task_id"]: t for t in tasks}
    if not tasks or len(expected) != len(tasks):
        raise StudyError("Expected a nonempty unique task set")
    opener = build_opener(ProxyHandler({}), NoRedirects())
    task_set_sha256 = digest(tasks)
    seen = set()
    previous_identity = None
    if path.exists():
        for row in read_jsonl(path):
            tid = row.get("task_id")
            if tid not in expected or tid in seen:
                raise StudyError("Unknown or duplicate completed task")
            if row.get("backend") != "ollama_local" or row.get("model") != model or row.get("endpoint") != endpoint:
                raise StudyError("Resume backend/model/endpoint mismatch")
            if row.get("task_sha256") != expected[tid]["task_sha256"]:
                raise StudyError("Resume prompt mismatch")
            content = {k: v for k, v in row.items() if k != "response_sha256"}
            if digest(content) != row.get("response_sha256"):
                raise StudyError("Changed response file")
            if row.get("status") != "ok":
                raise StudyError("Previous run contains a failure; preserve it and start a new response file")
            if parse_answer(row.get("raw_response", "")) != row.get("answer"):
                raise StudyError("Resume raw and parsed answers differ")
            if row.get("task_set_sha256") != task_set_sha256 or not row.get("model_identity"):
                raise StudyError("Resume task set or model identity missing/mismatched")
            if previous_identity is not None and row["model_identity"] != previous_identity:
                raise StudyError("Resume file mixes model identities")
            previous_identity = row["model_identity"]
            seen.add(tid)
    pending = [t for t in tasks if t["task_id"] not in seen]
    if limit is not None:
        pending = pending[:limit]
    if not pending:
        return {"attempted": 0, "previously_recorded": len(seen), "errors": 0, "remaining": 0,
                "remaining_unattempted": 0, "complete": True}
    identity = model_identity(opener, endpoint, model, timeout)
    if previous_identity is not None and previous_identity != identity:
        raise StudyError("Installed model identity changed since the previous run")
    path.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    errors = 0
    with path.open("a" if resume else "x", encoding="utf-8", newline="\n") as stream:
        for task in pending:
            record = {"task_id": task["task_id"], "task_sha256": task["task_sha256"], "backend": "ollama_local",
                      "model": model, "endpoint": endpoint, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                      "model_identity": identity, "task_set_sha256": task_set_sha256}
            started = time.monotonic()
            try:
                if model_identity(opener, endpoint, model, timeout) != identity:
                    raise StudyError("Installed model identity changed before generation")
                body = {"model": model, "prompt": task["prompt"], "stream": False, "format": "json",
                        "options": {"temperature": task["temperature"], "seed": task["seed"], "num_predict": task["max_output_tokens"]}}
                request = Request(url, data=canonical(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
                with opener.open(request, timeout=timeout) as response:
                    payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise StudyError("Model response too large")
                parsed = strict_json(payload)
                record["raw_response"] = parsed.get("response", "")
                record["reported_model"] = parsed.get("model")
                record["token_usage"] = {k: parsed.get(k) for k in ("prompt_eval_count", "eval_count")}
                if record["reported_model"] not in {model, identity["canonical_model"]}:
                    raise StudyError("Response reported a different model")
                if model_identity(opener, endpoint, model, timeout) != identity:
                    raise StudyError("Installed model identity changed during generation")
                if parsed.get("done") is not True or parsed.get("done_reason") == "length":
                    raise StudyError("Generation incomplete or truncated")
                record["answer"] = parse_answer(record["raw_response"])
                record["status"] = "ok"
            except Exception as error:
                record["status"] = "error"
                record["error"] = f"{type(error).__name__}: {error}"
                errors += 1
            record["elapsed_seconds"] = round(time.monotonic() - started, 6)
            record["response_sha256"] = digest(record)
            stream.write(canonical(record) + "\n")
            stream.flush()
            completed += 1
            print(f"{completed}/{len(pending)} {task['method']} {record['status']}", flush=True)
            # Preserve the first failure rather than repeating hundreds of failing calls.
            if record["status"] != "ok":
                break
    return {"attempted": completed, "previously_recorded": len(seen), "errors": errors,
            "remaining": len(tasks) - len(seen) - completed + errors,
            "remaining_unattempted": len(tasks) - len(seen) - completed,
            "complete": not errors and len(seen) + completed == len(tasks)}
