#!/usr/bin/env bash
set -euo pipefail

# Release helper for building and uploading this package to PyPI or TestPyPI.
# Usage:
#   scripts/release.sh          # build and upload to PyPI
#   scripts/release.sh --test   # build and upload to TestPyPI
#

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

# Load environment variables from .env file if it exists
if [[ -f .env ]]; then
  echo "[release] Loading environment variables from .env..."
  set -a  # automatically export all variables
  source .env
  set +a  # disable automatic export
fi

REPOSITORY_ARGS=()
if [[ "${1-}" == "--test" ]]; then
  REPOSITORY_ARGS=(--repository testpypi)
fi

echo "[release] Ensuring build tooling is installed..."
uv add --dev build twine >/dev/null

echo "[release] Cleaning previous build artifacts..."
rm -rf dist build ./*.egg-info ./.eggs

echo "[release] Building sdist and wheel..."
uv run python -m build

echo "[release] Verifying artifacts..."
uv run twine check dist/*

echo "[release] Uploading artifacts with Twine..."
uv run twine upload "${REPOSITORY_ARGS[@]}" dist/*

echo "[release] Done."


