#!/bin/sh
# install.sh: the Latest release from GitHub into /Applications, signed "Mantra Apps" (no compile on the Mac).
# Usage: ./install.sh [vN]
set -e
REPO=markoboskoauroville/groq_ai_studio
NAME="Queen"
D="${TMPDIR:-/tmp}/groq-ai-studio-mac"
rm -rf "$D"; mkdir -p "$D"
gh release download $1 --repo "$REPO" --pattern app.zip -D "$D" --clobber
osascript -e "tell application \"Queen\" to quit" 2>/dev/null || true
sleep 1
rm -rf "/Applications/$NAME.app" "/Applications/Groq AI Studio (Mantra).app" "/Applications/Groq Queen AI Studio (Mantra).app"
ditto -x -k "$D/app.zip" /Applications
xattr -dr com.apple.quarantine "/Applications/$NAME.app" 2>/dev/null || true
codesign --force -s "Mantra Apps" "/Applications/$NAME.app/Contents/MacOS/axread"
codesign --force -s "Mantra Apps" "/Applications/$NAME.app"
mkdir -p "$HOME/.local/bin" && ln -sf "/Applications/$NAME.app/Contents/MacOS/axread" "$HOME/.local/bin/axread"
codesign -dv "/Applications/$NAME.app" 2>&1 | grep -E "Authority|Identifier" || true
echo "installed /Applications/$NAME.app"
