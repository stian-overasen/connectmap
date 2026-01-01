#!/bin/bash
set -e  # Exit on first error

echo "🎨 Formatting Python code with ruff..."
uv run ruff check --fix .
uv run ruff format .

echo "📝 Formatting Markdown files with prettier..."
npx prettier --write "*.md"

echo "✅ Formatting complete!"
