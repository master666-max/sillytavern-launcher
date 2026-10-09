#!/bin/bash
# Ensure the bundled third-party extensions exist and are correctly marked.
# Downloads the latest official zips into assets-src/extensions, forces
# auto_update=false in their manifests (bundled copies are plain folders with
# no .git, so ST's startup auto-update would fail loudly), then applies the
# Simplified-Chinese localization table. Users who install extensions from a
# GIT URL keep full auto-update behavior.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
EXT_DIR="$REPO/assets-src/extensions"
mkdir -p "$EXT_DIR"
cd "$EXT_DIR"

# name -> codeload repo slug
REPOS=(
  "TopInfoBar:SillyTavern/Extension-TopInfoBar"
  "Live2d:SillyTavern/Extension-Live2d"
  "QuickPersona:SillyTavern/Extension-QuickPersona"
  "Objective:SillyTavern/Extension-Objective"
  "TypingIndicator:SillyTavern/Extension-TypingIndicator"
  "WebSearch:SillyTavern/Extension-WebSearch"
  "Notebook:SillyTavern/Extension-Notebook"
  "Dice:SillyTavern/Extension-Dice"
  "EmojiPicker:SillyTavern/Extension-EmojiPicker"
  "Mermaid:SillyTavern/Extension-Mermaid"
  "LaTeX:SillyTavern/Extension-LaTeX"
  "MessageLimit:SillyTavern/Extension-MessageLimit"
)

for entry in "${REPOS[@]}"; do
  name="${entry%%:*}"
  slug="${entry##*:}"
  dir="Extension-$name-main"
  if [ ! -f "$dir/manifest.json" ]; then
    echo "fetch $name <- $slug"
    curl -sfL --retry 3 -o "$name.zip" "https://codeload.github.com/$slug/zip/refs/heads/main"
    unzip -q -o "$name.zip"
    rm -f "$name.zip"
  else
    echo "keep $name (already present)"
  fi
  # bundled copies are not git checkouts: never auto-update them
  if grep -q '"auto_update": true' "$dir/manifest.json"; then
    sed -i 's/"auto_update": true/"auto_update": false/' "$dir/manifest.json"
    echo "  auto_update -> false"
  fi
done

echo "extensions ready: $(ls -d Extension-*/ | wc -l) dirs"

echo "── applying Simplified-Chinese localization ──"
python "$REPO/scripts/localize_extensions.py"
