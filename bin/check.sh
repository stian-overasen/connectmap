#!/bin/bash
set -e

echo "🔍 Linting all code..."
./bin/lint.sh

echo ""
echo "🎨 Formatting all code..."
./bin/format.sh

echo ""
echo "✅ All checks and formatting complete!"
