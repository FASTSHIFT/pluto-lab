# -*- coding: utf-8 -*-
"""Architecture boundary checks.

Three rules, enforced by a machine because humans forget:

1. ``tools/<a>`` must not import ``tools/<b>``
2. shared code lives in ``sdr/`` and nothing else
3. ``sdr/`` must not import ``tools/`` or ``scripts/``

Once tools start importing each other the repo degrades into a tangle, and the
"one directory per tool" layout stops meaning anything.
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
SDR = os.path.join(ROOT, "sdr")
SCRIPTS = os.path.join(ROOT, "scripts")

SKIP_DIRS = {"__pycache__", "vendor", "libiio", "web", "tiles"}


def py_files(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def imported_modules(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.add(node.module)
    return mods


def test_tools_do_not_import_each_other():
    problems = []
    for tool in sorted(os.listdir(TOOLS)):
        tdir = os.path.join(TOOLS, tool)
        if not os.path.isdir(tdir) or tool.startswith("__"):
            continue
        for path in py_files(tdir):
            for mod in imported_modules(path):
                if not mod.startswith("tools."):
                    continue
                other = mod.split(".")[1]
                if other != tool:
                    problems.append("%s imports tools.%s" % (os.path.relpath(path, ROOT), other))
    assert not problems, "tools must not depend on each other:\n  " + "\n  ".join(problems)


def test_core_does_not_depend_on_apps():
    problems = []
    for path in py_files(SDR):
        for mod in imported_modules(path):
            top = mod.split(".")[0]
            if top in ("tools", "scripts"):
                problems.append("%s imports %s" % (os.path.relpath(path, ROOT), mod))
    assert not problems, "core must not depend on upper layers:\n  " + "\n  ".join(problems)


def test_every_tool_has_an_entrypoint():
    for tool in sorted(os.listdir(TOOLS)):
        tdir = os.path.join(TOOLS, tool)
        if not os.path.isdir(tdir) or tool.startswith("__"):
            continue
        files = [f for f in os.listdir(tdir) if f.endswith(".py")]
        assert files, "tools/%s has no .py file" % tool


def test_scripts_are_standalone_helpers():
    """scripts/ may use sdr/, but must not pull in tools/."""
    problems = []
    for path in py_files(SCRIPTS):
        for mod in imported_modules(path):
            if mod.startswith("tools"):
                problems.append("%s imports %s" % (os.path.relpath(path, ROOT), mod))
    assert not problems, "scripts must not import tools:\n  " + "\n  ".join(problems)
