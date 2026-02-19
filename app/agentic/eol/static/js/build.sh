#!/bin/bash
# JavaScript Build and Optimization Script
# Minifies JS files, generates source maps, and validates performance budgets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔧 JavaScript Build & Optimization"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if terser is installed (optional)
if command -v terser &> /dev/null; then
    HAS_TERSER=true
    echo "✅ Found terser for minification"
else
    HAS_TERSER=false
    echo "⚠️  terser not found - install with: npm install -g terser"
    echo "   Skipping minification..."
fi

echo ""

# Function to get file size in KB
get_size_kb() {
    local file=$1
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        stat -f%z "$file" | awk '{printf "%.2f", $1/1024}'
    else
        # Linux
        stat -c%s "$file" | awk '{printf "%.2f", $1/1024}'
    fi
}

# Function to minify a file
minify_file() {
    local input=$1
    local output=$2

    if [ "$HAS_TERSER" = true ]; then
        echo "  Minifying: $input → $output"
        terser "$input" \
            --compress \
            --mangle \
            --source-map "filename='${output}.map',url='$(basename $output).map'" \
            --output "$output" \
            --comments false

        local original_size=$(get_size_kb "$input")
        local minified_size=$(get_size_kb "$output")
        local savings=$(echo "$original_size - $minified_size" | bc)
        local percent=$(echo "scale=1; ($savings / $original_size) * 100" | bc)

        echo "    Original: ${original_size}KB → Minified: ${minified_size}KB (saved ${percent}%)"
    else
        echo "  Copying: $input → $output (terser not available)"
        cp "$input" "$output"
    fi
}

echo "📦 Building ES Modules..."
echo "------------------------"

# ES modules are already optimized, just copy them
if [ -d "modules" ]; then
    echo "  ✅ ES modules found in modules/"

    # List module files
    for file in modules/*.js; do
        if [ -f "$file" ]; then
            size=$(get_size_kb "$file")
            echo "    - $(basename $file): ${size}KB"
        fi
    done
else
    echo "  ⚠️  No modules/ directory found"
fi

echo ""
echo "📊 Calculating Bundle Sizes..."
echo "-----------------------------"

# Calculate total bundle size
total_size=0
file_count=0

echo "Files included in bundle:"
for file in *.js; do
    # Skip .min.js and .bak files
    if [[ ! "$file" =~ \.min\.js$ ]] && [[ ! "$file" =~ \.bak$ ]]; then
        if [ -f "$file" ]; then
            size=$(get_size_kb "$file")
            total_size=$(echo "$total_size + $size" | bc)
            file_count=$((file_count + 1))
            echo "  - $file: ${size}KB"
        fi
    fi
done

echo ""
echo "Total bundle size: ${total_size}KB ($file_count files)"

# Check against budget
BUDGET_KB=500
if (( $(echo "$total_size > $BUDGET_KB" | bc -l) )); then
    echo -e "${RED}❌ OVER BUDGET: ${total_size}KB > ${BUDGET_KB}KB${NC}"
    exit 1
else
    remaining=$(echo "$BUDGET_KB - $total_size" | bc)
    echo -e "${GREEN}✅ WITHIN BUDGET: ${total_size}KB < ${BUDGET_KB}KB (${remaining}KB remaining)${NC}"
fi

echo ""
echo "🎯 Optimization Recommendations"
echo "-------------------------------"
echo "1. ✅ Use ES modules (modules/*.js) for tree-shaking"
echo "2. ✅ Enable gzip compression on web server (~60% savings)"
echo "3. ✅ Use HTTP/2 for multiplexing"
echo "4. 📝 Consider bundling with esbuild for production"
echo "5. 📝 Implement lazy loading for non-critical code"
echo "6. 📝 Use code splitting for different routes"

echo ""
echo "📋 Performance Budget Summary"
echo "----------------------------"
cat performance-budget.json | grep -A 3 '"budgets"' | head -20 || echo "See performance-budget.json for details"

echo ""
echo -e "${GREEN}✅ Build complete!${NC}"
