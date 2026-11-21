#!/bin/sh
# Install the tracked git hooks (Linux / macOS / Git Bash).
#
#   sh scripts/install_hooks.sh

set -eu
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

echo "core.hooksPath = $(git config core.hooksPath)"
echo ""
echo "Enabled hooks:"
echo "  commit-msg  enforce Conventional Commits in English"
echo "  pre-commit  compile, english-only, line limit, ruff, tests + coverage"
echo ""
echo "Bypass when you really need to: git commit --no-verify"
