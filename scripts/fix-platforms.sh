#!/bin/bash
# Fix invalid platform values in Fleet query files
# Valid values: darwin, linux, windows, chrome (comma-separated)

cd "$(dirname "$0")/.." || exit 1

echo "=== All unique platform values ==="
grep -rh "platform:" lib/ --include="*.yml" | sed 's/.*platform:/platform:/' | sort | uniq -c | sort -rn

echo ""
echo "=== Invalid platforms (not darwin/linux/windows/chrome) ==="
INVALID=$(grep -r "platform:" lib/ --include="*.yml" | grep -Ev "darwin|linux|windows|chrome" | grep -v "^#")
if [ -z "$INVALID" ]; then
    echo "None found!"
else
    echo "$INVALID"
    echo ""
    echo "^^^ FIX THESE ^^^"
fi

echo ""
echo "=== Applying known fixes ==="

# Fix posix -> darwin, linux
count=$(grep -r "platform: posix" lib/ --include="*.yml" -l 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 0 ]; then
    for file in $(grep -r "platform: posix" lib/ --include="*.yml" -l 2>/dev/null); do
        sed -i '' 's/platform: posix/platform: darwin, linux/g' "$file"
    done
    echo "Fixed $count files: posix -> darwin, linux"
fi

# Fix gentoo -> linux
count=$(grep -r "platform: gentoo" lib/ --include="*.yml" -l 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 0 ]; then
    for file in $(grep -r "platform: gentoo" lib/ --include="*.yml" -l 2>/dev/null); do
        sed -i '' 's/platform: gentoo/platform: linux/g' "$file"
    done
    echo "Fixed $count files: gentoo -> linux"
fi

# Fix macos -> darwin
count=$(grep -r "platform: macos" lib/ --include="*.yml" -l 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 0 ]; then
    for file in $(grep -r "platform: macos" lib/ --include="*.yml" -l 2>/dev/null); do
        sed -i '' 's/platform: macos/platform: darwin/g' "$file"
    done
    echo "Fixed $count files: macos -> darwin"
fi

# Fix all -> darwin, linux, windows
count=$(grep -r "platform: all" lib/ --include="*.yml" -l 2>/dev/null | wc -l | tr -d ' ')
if [ "$count" -gt 0 ]; then
    for file in $(grep -r "platform: all" lib/ --include="*.yml" -l 2>/dev/null); do
        sed -i '' 's/platform: all/platform: darwin, linux, windows/g' "$file"
    done
    echo "Fixed $count files: all -> darwin, linux, windows"
fi

echo ""
echo "=== Done ==="
