#!/bin/bash
set -e  # Exit on first error

echo "🔍 Running linters..."

# Check Python formatting
echo "→ Checking Python formatting with ruff..."
uv run ruff format --check .

# Check Python linting
echo "→ Checking Python code quality with ruff..."
uv run ruff check .

# Run codespell to find common misspellings
echo "→ Checking for common misspellings with codespell..."
uv run codespell

echo "✅ All checks passed!"
