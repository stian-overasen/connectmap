#!/bin/bash
set -e

echo "🔍 Linting all code..."
./scripts/lint.sh

echo ""
echo "🎨 Formatting all code..."
./scripts/format.sh

echo ""
echo "✅ All checks and formatting complete!"
