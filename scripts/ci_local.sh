#!/bin/sh
# Run the same checks CI runs, locally. Run this before pushing.
#
#   sh scripts/ci_local.sh
#
# Requires python and git. Installs ruff / pytest / pytest-cov unless
# SKIP_INSTALL=1 is set.

set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
    echo "not inside a git repository" >&2
    exit 1
}
cd "$ROOT" || exit 1

PY=""
for p in python python3; do
    if command -v "$p" >/dev/null 2>&1; then PY="$p"; break; fi
done
[ -z "$PY" ] && { echo "python not found" >&2; exit 1; }

fail=0
step() { printf '\n=== %s ===\n' "$1"; }

if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    step "install check tools"
    $PY -m pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple \
        ruff pytest pytest-cov pyyaml 2>&1 | tail -2
fi

step "byte-compile"
$PY -m compileall -q sdr tools scripts tests || fail=1

step "ruff check"
$PY -m ruff check . || fail=1

step "ruff format --check"
$PY -m ruff format --check . || fail=1

step "english only (no CJK in sources)"
$PY scripts/check_no_chinese.py || fail=1

step "file line limit"
$PY scripts/check_file_lines.py || fail=1

step "unit tests with coverage"
$PY -m pytest -q tests --cov=sdr --cov-report=term-missing \
    --cov-fail-under=85 || fail=1

step "CI workflow syntax"
$PY - <<'PY' || fail=1
import yaml
d = yaml.safe_load(open('.github/workflows/ci.yml', encoding='utf-8'))
jobs = d.get('jobs') or {}
assert jobs, "no jobs defined"
print("jobs:", ", ".join(jobs))
PY

step "commit messages"
if git rev-parse --verify HEAD >/dev/null 2>&1; then
    $PY scripts/check_commit_msg.py --range HEAD || fail=1
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "[OK] all local checks passed"
else
    echo "[FAIL] some checks failed, fix them before pushing"
fi
exit "$fail"
