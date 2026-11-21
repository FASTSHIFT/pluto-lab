# -*- coding: utf-8 -*-
"""Commit message validator (Conventional Commits + English only).

Rules, matching the discipline used by FPBInject:

    type(scope): summary

    type    : feat | fix | test | refactor | chore | docs | style | perf | build | ci | revert
    scope   : optional, lowercase letters/digits/._-
    summary : non-empty, imperative, no trailing period, whole line <= 100 chars
    text    : English only - any non-ASCII character is rejected

Auto-generated messages (Merge / Revert / fixup! / squash! / Reapply) are exempt.

Usage:
    python scripts/check_commit_msg.py .git/COMMIT_EDITMSG    # hook mode
    python scripts/check_commit_msg.py --text "feat(adsb): x" # validate one subject
    python scripts/check_commit_msg.py --range origin/main..HEAD   # CI mode
"""

import argparse
import re
import subprocess
import sys

# Hooks may run in a GBK or ASCII console; force UTF-8 and replace on error.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TYPES = ("feat", "fix", "test", "refactor", "chore", "docs", "style", "perf", "build", "ci", "revert")
SUBJECT_RE = re.compile(r"^(%s)(\([a-z0-9._-]+\))?!?: .+" % "|".join(TYPES))
MAX_LEN = 100
EXEMPT_PREFIX = ("Merge ", "Revert ", "fixup! ", "squash! ", "Reapply ")

HELP = """Commit message format:

    type(scope): summary        (scope optional)

  type   : feat | fix | test | refactor | chore | docs | style | perf | build | ci | revert
  scope  : optional, e.g. (adsb), (spectrum), (ci)
  summary: short, imperative, no trailing period, <= 100 chars
  text   : English only (ASCII); non-ASCII characters are rejected

Examples:
    feat(adsb): add tar1090 web backend
    fix(modes): use NL-1 longitude zones for odd CPR frames
    docs: document the antenna length table
"""


def _non_ascii(text):
    return [c for c in text if ord(c) > 127]


def validate_subject(subject):
    """Return (ok, reason) for one subject line."""
    if not subject:
        return False, "empty subject"
    if subject.startswith(EXEMPT_PREFIX):
        return True, ""
    if not SUBJECT_RE.match(subject):
        return False, "does not match 'type(scope): summary'"
    bad = _non_ascii(subject)
    if bad:
        return False, "must be English (non-ASCII: %s)" % "".join(sorted(set(bad))[:5])
    if len(subject) > MAX_LEN:
        return False, "subject exceeds %d chars (%d)" % (MAX_LEN, len(subject))
    if subject.endswith("."):
        return False, "subject should not end with a period"
    return True, ""


def validate_message(text):
    """Validate a whole commit message: subject format plus English-only body."""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    subject = lines[0] if lines else ""
    ok, why = validate_subject(subject)
    if not ok:
        return False, why
    if subject.startswith(EXEMPT_PREFIX):
        return True, ""
    body = "\n".join(lines[1:])
    bad = _non_ascii(body)
    if bad:
        return False, "body must be English (non-ASCII: %s)" % "".join(sorted(set(bad))[:5])
    return True, ""


def check_range(rng):
    try:
        shas = subprocess.check_output(
            ["git", "rev-list", rng], encoding="utf-8", errors="replace", stderr=subprocess.PIPE
        ).split()
    except subprocess.CalledProcessError:
        print("[FAIL] cannot resolve revision range: %s" % rng)
        return 2
    if not shas:
        print("[OK] no commits in range %s" % rng)
        return 0

    # The repository's initial commit has no parent and is not held to the rule.
    try:
        roots = set(
            subprocess.check_output(
                ["git", "rev-list", "--max-parents=0", rng], encoding="utf-8", errors="replace", stderr=subprocess.PIPE
            ).split()
        )
    except subprocess.CalledProcessError:
        roots = set()

    bad = 0
    skipped = 0
    for sha in shas:
        if sha in roots:
            skipped += 1
            continue
        msg = subprocess.check_output(
            ["git", "log", "-1", "--format=%B", sha], encoding="utf-8", errors="replace"
        ).strip()
        ok, why = validate_message(msg)
        if not ok:
            bad += 1
            subject = msg.splitlines()[0] if msg else ""
            print("[FAIL] %s: %s" % (sha[:8], why))
            print("   > %s" % subject)
    if bad:
        print("\n%d commit message(s) rejected\n" % bad)
        print(HELP)
        return 1
    msg = "[OK] %s: %d commit(s) compliant" % (rng, len(shas) - skipped)
    if skipped:
        msg += ", %d root commit(s) skipped" % skipped
    print(msg)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("file", nargs="?", help="commit message file")
    ap.add_argument("--text", help="validate a literal subject")
    ap.add_argument("--range", dest="rng", help="validate a revision range")
    args = ap.parse_args(argv)

    if args.text is not None:
        ok, why = validate_subject(args.text.strip().splitlines()[0] if args.text.strip() else "")
        if ok:
            print("[OK] subject accepted")
            return 0
        print("[FAIL] %s\n   > %s\n" % (why, args.text))
        print(HELP)
        return 1

    if args.rng:
        return check_range(args.rng)

    if not args.file:
        print("usage: check_commit_msg.py <file> | --text <s> | --range <r>", file=sys.stderr)
        return 2

    with open(args.file, encoding="utf-8", errors="replace") as f:
        text = f.read()
    ok, why = validate_message(text)
    if ok:
        return 0
    subject = next((ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")), "")
    print("[FAIL] commit message rejected: %s" % why)
    print("   > %s\n" % (subject or "<empty>"))
    print(HELP)
    return 1


if __name__ == "__main__":
    sys.exit(main())
