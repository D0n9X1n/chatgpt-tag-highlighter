#!/usr/bin/env bash
# publish.sh
# Build Chrome + Firefox bundles from the same src/ directory, and sync version in manifests.

set -euo pipefail

# -------- Config: adjust if your names differ --------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$ROOT_DIR/src"
DIST_DIR="$ROOT_DIR/dist"

MANIFEST_CHROME="$SRC_DIR/manifest.chrome.json"
MANIFEST_FIREFOX="$SRC_DIR/manifest.firefox.json"

EXT_NAME="chatgpt-tag-highlighter"
# -----------------------------------------------------

usage() {
  cat <<EOF
Usage:
  ./publish.sh --version X.Y.Z

Outputs:
  dist/${EXT_NAME}-chrome-X.Y.Z.zip
  dist/${EXT_NAME}-firefox-X.Y.Z.xpi

Expected structure:
  src/
    content.js
    manifest.chrome.json
    manifest.firefox.json
    (optional) icons/, images/, etc...
EOF
}

VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -v|--version)
      VERSION="${2:-}"; shift 2;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage; exit 1;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "Error: --version is required (e.g. 0.1.0)" >&2
  usage
  exit 1
fi

# Basic semver-ish check (allows 1.2.3, 1.2.3-beta.1, etc.)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([\-+][0-9A-Za-z\.-]+)?$ ]]; then
  echo "Error: version '$VERSION' doesn't look like SemVer (e.g. 0.1.0 or 0.1.0-beta.1)" >&2
  exit 1
fi

command -v python3 >/dev/null 2>&1 || { echo "Error: python3 not found." >&2; exit 1; }
command -v zip >/dev/null 2>&1 || { echo "Error: zip not found." >&2; exit 1; }

[[ -d "$SRC_DIR" ]] || { echo "Error: src dir not found: $SRC_DIR" >&2; exit 1; }
[[ -f "$MANIFEST_CHROME" ]] || { echo "Error: missing $MANIFEST_CHROME" >&2; exit 1; }
[[ -f "$MANIFEST_FIREFOX" ]] || { echo "Error: missing $MANIFEST_FIREFOX" >&2; exit 1; }

# Write manifest.json with updated version (robust JSON edit)
write_manifest_with_version() {
  local in_file="$1"
  local out_file="$2"
  local ver="$3"

  python3 - "$in_file" "$out_file" "$ver" <<'PY'
import json, sys

in_file, out_file, ver = sys.argv[1], sys.argv[2], sys.argv[3]

with open(in_file, "r", encoding="utf-8") as f:
    data = json.load(f)

data["version"] = ver

with open(out_file, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PY
}

# Copy everything from src -> target, excluding manifest templates
stage_dir() {
  local target="$1"
  rm -rf "$target"
  mkdir -p "$target"

  # Copy all files/dirs under src except manifest.*.json
  # Works on macOS/Linux (no GNU-only flags).
  (cd "$SRC_DIR" && \
    find . -mindepth 1 \
      ! -name "manifest.chrome.json" \
      ! -name "manifest.firefox.json" \
      -print0 | \
    while IFS= read -r -d '' p; do
      if [[ -d "$SRC_DIR/$p" ]]; then
        mkdir -p "$target/$p"
      else
        mkdir -p "$(dirname "$target/$p")"
        cp -f "$SRC_DIR/$p" "$target/$p"
      fi
    done)
}

build_one() {
  local flavor="$1"       # chrome|firefox
  local manifest_tpl="$2" # path to manifest template
  local out_ext="$3"      # zip|xpi

  local stage="$DIST_DIR/$flavor"
  stage_dir "$stage"

  write_manifest_with_version "$manifest_tpl" "$stage/manifest.json" "$VERSION"

  local out_file="$DIST_DIR/${EXT_NAME}-${flavor}-${VERSION}.${out_ext}"
  rm -f "$out_file"

  (cd "$stage" && zip -r -q "$out_file" .)

  echo "✅ Built: $out_file"
}

mkdir -p "$DIST_DIR"

build_one "chrome"  "$MANIFEST_CHROME"  "zip"
build_one "firefox" "$MANIFEST_FIREFOX" "xpi"

echo "🎉 Done. Artifacts are in: $DIST_DIR"

