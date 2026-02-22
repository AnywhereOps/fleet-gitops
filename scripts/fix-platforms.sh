#!/bin/bash
# Fix invalid platform values in Fleet query files
# Valid values: darwin, linux, windows, chrome (comma-separated)

cd "$(dirname "$0")/.." || exit 1

echo "=== Checking for invalid platform values ==="

# Find all invalid platforms
echo ""
echo "Files with 'platform: posix' (should be 'darwin, linux'):"
grep -r "platform: posix" lib/ --include="*.yml" -l 2>/dev/null | while read -r file; do
    echo "  - $file"
done

echo ""
echo "Files with 'platform: all' (should be 'darwin, linux, windows'):"
grep -r "platform: all" lib/ --include="*.yml" -l 2>/dev/null | while read -r file; do
    echo "  - $file"
done

echo ""
echo "Files with 'platform: macos' (should be 'darwin'):"
grep -r "platform: macos" lib/ --include="*.yml" -l 2>/dev/null | while read -r file; do
    echo "  - $file"
done

echo ""
echo "=== Fixing invalid platform values ==="

# Fix posix -> darwin, linux
count=0
for file in $(grep -r "platform: posix" lib/ --include="*.yml" -l 2>/dev/null); do
    sed -i '' 's/platform: posix/platform: darwin, linux/g' "$file"
    ((count++))
done
echo "Fixed $count files with 'posix' -> 'darwin, linux'"

# Fix all -> darwin, linux, windows
count=0
for file in $(grep -r "platform: all" lib/ --include="*.yml" -l 2>/dev/null); do
    sed -i '' 's/platform: all/platform: darwin, linux, windows/g' "$file"
    ((count++))
done
echo "Fixed $count files with 'all' -> 'darwin, linux, windows'"

# Fix macos -> darwin
count=0
for file in $(grep -r "platform: macos" lib/ --include="*.yml" -l 2>/dev/null); do
    sed -i '' 's/platform: macos/platform: darwin/g' "$file"
    ((count++))
done
echo "Fixed $count files with 'macos' -> 'darwin'"

echo ""
echo "=== Done ==="
