# -*- coding: utf-8 -*-
"""Reject Chinese (CJK) characters in source files.

Ported from FPBInject's ``Tools/WebServer/tests/scan_chinese.py``. The rule is
simple: code, comments and user-facing strings are English only. Docs
(``*.md``) are exempt.

    python scripts/check_no_chinese.py            # scan the repo
    python scripts/check_no_chinese.py --quiet    # exit code only

Excluded: .git, vendor, libiio, web (third-party tar1090 frontend), caches.
"""

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CJK = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")

SCAN_EXT = {".py", ".sh", ".ps1", ".yml", ".yaml", ".toml", ".js", ".html", ".css", ".cmd"}
SKIP_DIRS = {
    ".git",
    "vendor",
    "libiio",
    "web",
    "tiles",
    "edgeprof",
    "__pycache__",
    ".venv",
    "node_modules",
    ".pytest_cache",
    "htmlcov",
    ".ruff_cache",
}


def scan_file(path):
    findings = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for num, line in enumerate(f, 1):
                if CJK.search(line):
                    findings.append((num, line.rstrip()[:120]))
    except OSError:
        pass
    return findings


def iter_sources(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in SCAN_EXT:
                yield os.path.join(dirpath, name)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("path", nargs="?", default=ROOT)
    args = ap.parse_args(argv)

    results = {}
    for path in iter_sources(args.path):
        f = scan_file(path)
        if f:
            results[os.path.relpath(path, ROOT)] = f

    if not results:
        if not args.quiet:
            print("[OK] no Chinese characters in source files")
        return 0

    total = sum(len(v) for v in results.values())
    print("[FAIL] Chinese text found in %d file(s), %d line(s):" % (len(results), total))
    for rel, items in sorted(results.items()):
        print("\n  %s" % rel)
        for num, line in items[:10]:
            print("    %5d  %s" % (num, line))
        if len(items) > 10:
            print("    ... %d more" % (len(items) - 10))
    print("\nTranslate them to English, or add an exception to the allowlist.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
