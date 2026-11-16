#!/bin/sh
# build.sh: Queen.app (shown as Queen) + axread inside it. swiftc straight, no Xcode. Run ONLY by GitHub
# (.github/workflows/build.yml, SIGN=- NO_INSTALL=1): nothing is compiled on Marko's Mac (MANTRA_MANIFEST android-app.md §0).
# On the Mac the release zip is downloaded, unpacked into /Applications and signed "Mantra Apps" (install.sh).
set -e
cd "$(dirname "$0")"
V=$(sed -n 's/^let VERSION = \([0-9]*\)/\1/p' app/App.swift)
NAME="Queen"
DISPLAY="Queen"
APP="build/$NAME.app"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -swift-version 5 -parse-as-library -o "$APP/Contents/MacOS/GroqAIStudio" app/*.swift app/core/*.swift
# Phase A: Queen's system prompt comes from app.py (helper in the bundle, run on the installed app.py; this copy is the fallback)
python3 tools/gen_prompt.py ../qwen_app/app.py > "$APP/Contents/Resources/queen_prompt.json"
cp tools/gen_prompt.py "$APP/Contents/Resources/gen_prompt.py"
swiftc -O -swift-version 5 -o "$APP/Contents/MacOS/axread" axread/main.swift
[ -x "$APP/Contents/MacOS/GroqAIStudio" ] && [ -x "$APP/Contents/MacOS/axread" ] || { echo "the app did not build"; exit 1; }
cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>$DISPLAY</string>
<key>CFBundleDisplayName</key><string>$DISPLAY</string>
<key>CFBundleIdentifier</key><string>community.auroville.groqaistudio</string>
<key>CFBundleExecutable</key><string>GroqAIStudio</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$V</string>
<key>CFBundleVersion</key><string>$V</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PL
I=build/AppIcon.iconset; rm -rf $I; mkdir -p $I
for s in 16 32 128 256 512; do
  sips -z $s $s icon/six_1024.png --out $I/icon_${s}x${s}.png >/dev/null
  sips -z $((s*2)) $((s*2)) icon/six_1024.png --out $I/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns $I -o "$APP/Contents/Resources/AppIcon.icns"
/usr/libexec/PlistBuddy -c "Add :CFBundleIconFile string AppIcon" "$APP/Contents/Info.plist"
codesign --force -s "${SIGN:-Mantra Apps}" "$APP/Contents/MacOS/axread"
codesign --force -s "${SIGN:-Mantra Apps}" "$APP"
echo "built $APP (v$V)"
