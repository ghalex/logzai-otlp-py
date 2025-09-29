#!/usr/bin/env bash
set -euo pipefail

# Release helper for building and uploading this package to PyPI or TestPyPI.
# Usage:
#   scripts/release.sh          # build and upload to PyPI
#   scripts/release.sh --test   # build and upload to TestPyPI
#

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

REPOSITORY_ARGS=()
if [[ "${1-}" == "--test" ]]; then
  REPOSITORY_ARGS=(--repository testpypi)
fi

echo "[release] Ensuring build tooling is installed..."
python -m pip install --upgrade pip >/dev/null
python -m pip install --upgrade build twine >/dev/null

echo "[release] Cleaning previous build artifacts..."
rm -rf dist build ./*.egg-info ./.eggs

echo "[release] Building sdist and wheel..."
python -m build

echo "[release] Verifying artifacts..."
twine check dist/*

echo "[release] Uploading artifacts with Twine..."
twine upload "${REPOSITORY_ARGS[@]}" dist/*

echo "[release] Done."


