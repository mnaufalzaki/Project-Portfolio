#!/bin/bash
# Builds Yaping.app and zips it for a GitHub Release → dist/Yaping-<version>.zip
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(/usr/libexec/PlistBuddy -c "Print CFBundleShortVersionString" Resources/Info.plist)
./build.sh

mkdir -p dist
ZIP="dist/Yaping-$VERSION.zip"
rm -f "$ZIP"
# ditto keeps the code signature and bundle metadata intact (plain zip can break them).
ditto -c -k --keepParent build/Yaping.app "$ZIP"
rm -rf build/Yaping.app   # don't leave a second copy around to be launched by accident

echo "✓ $ZIP ($(du -h "$ZIP" | cut -f1))"
echo "  Publish it with: gh release create yaping-v$VERSION $ZIP --title \"Yaping $VERSION\" --notes-file docs/RELEASE_NOTES.md"
