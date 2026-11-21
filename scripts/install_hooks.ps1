# Install the repo's tracked git hooks (Windows PowerShell).
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_hooks.ps1
#
# Points core.hooksPath at .githooks/ so commit-msg and pre-commit are shared
# by everyone working on this repo.

$ErrorActionPreference = "Stop"

$root = git rev-parse --show-toplevel
if (-not $root) { Write-Error "not inside a git repository"; exit 1 }

git config core.hooksPath .githooks

Write-Host "core.hooksPath = $(git config core.hooksPath)"
Write-Host ""
Write-Host "Enabled hooks:"
Write-Host "  commit-msg  enforce Conventional Commits subjects"
Write-Host "  pre-commit  byte-compile + unit tests + boundary check"
Write-Host ""
Write-Host "Try this (it should be rejected):"
Write-Host '  git commit --allow-empty -m "bad message"'
Write-Host ""
Write-Host "Bypass when you really need to: git commit --no-verify"
