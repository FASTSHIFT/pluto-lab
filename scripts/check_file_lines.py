#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enforce a maximum line count on first-party sources.

Ported from FPBInject's ``Tools/check_file_lines.py``. Big files are where
unrelated concerns pile up; keeping them small is what makes the
"one directory per tool" layout stay honest.

Files listed in ``EXEMPT`` are allowed to exceed the limit for now, but they
must not grow any further.

    python scripts/check_file_lines.py [--limit N] [path ...]
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_LIMIT = 800

# path -> current line count at the time of exemption
EXEMPT = {}

SCAN_DIRS = ("sdr", "tools", "scripts", "tests")
SKIP_DIRS = {"__pycache__", "vendor", "libiio", "web", "tiles", ".git"}


def iter_py(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def count_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("paths", nargs="*", default=None)
    args = ap.parse_args()

    targets = [os.path.join(ROOT, d) for d in SCAN_DIRS]
    if args.paths:
        targets = args.paths

    bad = []
    for base in targets:
        if os.path.isfile(base):
            files = [base]
        else:
            files = iter_py(base)
        for path in files:
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            n = count_lines(path)
            if rel in EXEMPT:
                if n > EXEMPT[rel]:
                    bad.append((rel, n, EXEMPT[rel], "grew past its exemption"))
                continue
            if n > args.limit:
                bad.append((rel, n, args.limit, "over the limit"))

    if bad:
        print("[FAIL] file line-count check")
        for rel, n, lim, why in bad:
            print("  %-40s %5d lines (%s %d)" % (rel, n, why, lim))
        return 1

    print("[OK] all source files within %d lines" % args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
