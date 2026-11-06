"""Strict, bounded file formats and non-overwriting output helpers."""
import hashlib
import json
from pathlib import Path


class StudyError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise StudyError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise StudyError(f"Non-finite JSON number: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def read_json(path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise StudyError(f"File too large: {path.name}")
    return strict_json(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if len(line) > 2_000_000:
                raise StudyError(f"Oversized JSONL line {number}")
            if line.strip():
                try:
                    rows.append(strict_json(line))
                except ValueError as error:
                    raise StudyError(f"Invalid JSONL line {number}: {error}") from error
    return rows


def write_new(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_json(path, value):
    write_new(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_jsonl(path, values):
    write_new(path, "".join(canonical(value) + "\n" for value in values))
