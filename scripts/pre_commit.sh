#!/usr/bin/env sh
#
# Pre-commit script: run ruff + mypy + a fast test subset.
#
# Install with: ln -s ../../scripts/pre_commit.sh .git/hooks/pre-commit
# (from the reASITIC root)
#
# Skip with: git commit --no-verify
set -e

cd "$(dirname "$0")/.."

echo "==> ruff check"
ruff check .

echo "==> mypy"
mypy

# Run only the fast subset (skip the legacy-binary cross-check)
echo "==> pytest (fast subset)"
pytest --ignore=tests/test_validation_binary.py -q

echo "All pre-commit checks passed."
