"""Run tests in a fresh workspace-owned directory and retain machine-readable evidence."""
import subprocess
import sys
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
run_root = (root / ".test-runs").resolve()
assert run_root.parent == root
run_root.mkdir(exist_ok=True)
target = run_root / ("run-" + uuid.uuid4().hex)
assert target.parent == run_root and not target.exists()
report = run_root / (target.name + ".xml")
result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=short", "--basetemp", str(target),
                         "--junitxml", str(report)], cwd=root, capture_output=True, text=True)
log = run_root / (target.name + ".txt")
log.write_text(result.stdout + result.stderr, encoding="utf-8")
print(result.stdout, end="")
print(result.stderr, end="", file=sys.stderr)
print("Test evidence:", log.relative_to(root), report.relative_to(root))
raise SystemExit(result.returncode)
