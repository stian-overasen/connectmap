#!/bin/bash
set -e

echo "🔍 Linting Python code with ruff..."
uv run ruff check .

echo "✅ Linting complete!"
