#!/bin/bash
# Builds Yaping.app into ./build. Pass "install" to copy it to /Applications and launch it.
set -euo pipefail
cd "$(dirname "$0")"

APP=build/Yaping.app
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "→ Compiling…"
swiftc -O -swift-version 5 -parse-as-library \
    -target "$(uname -m)-apple-macos14.0" \
    Sources/Yaping/*.swift \
    -o "$APP/Contents/MacOS/Yaping"

cp Resources/Info.plist "$APP/Contents/"
[ -f Resources/AppIcon.icns ] && cp Resources/AppIcon.icns "$APP/Contents/Resources/"

# Use a stable signing identity when there is one so macOS permissions survive rebuilds:
# an Apple Development cert, or a self-signed "Yaping Local" code-signing cert (see README).
IDENTITY=$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Apple Development|Developer ID Application/ {print $2; exit}')
if [ -z "$IDENTITY" ] && security find-identity -p codesigning 2>/dev/null | grep -q '"Yaping Local"'; then
    IDENTITY="Yaping Local"
fi
echo "→ Signing with ${IDENTITY:-ad-hoc identity}…"
codesign --force --options runtime \
    --entitlements Resources/Yaping.entitlements \
    --sign "${IDENTITY:--}" "$APP"

echo "✓ Built $APP"

if [ "${1:-}" = "install" ]; then
    pkill -x Yaping 2>/dev/null || true
    rm -rf /Applications/Yaping.app
    mv "$APP" /Applications/   # move, so only one copy exists
    open /Applications/Yaping.app
    echo "✓ Installed to /Applications and launched"
fi
