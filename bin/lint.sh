#!/bin/bash
set -e  # Exit on first error

echo "🔍 Linting code with pre-commit …"
uv run pre-commit run --all-files
