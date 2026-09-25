#!/usr/bin/env bash
# Self-test for scripts/release-check.py against throwaway repo layouts.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
check="$here/release-check.py"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
failures=0

# make <dir> <chrome-version> <firefox-version> <changelog-heading-version>
make() {
  mkdir -p "$1/src"
  printf '{"version": "%s"}\n' "$2" > "$1/src/manifest.chrome.json"
  printf '{"version": "%s"}\n' "$3" > "$1/src/manifest.firefox.json"
  printf '# Changelog\n\n## [%s] - 2026-01-01\n\n### Fixed\n- Something.\n\n## [0.0.1]\n\n- Older.\n\n[%s]: https://example.invalid\n' "$4" "$4" > "$1/CHANGELOG.md"
}

expect() {  # expect <ok|fail> <description> <root> [args...]
  local want="$1" desc="$2" root="$3"; shift 3
  if python3 "$check" --root "$root" "$@" >/dev/null 2>&1; then got=ok; else got=fail; fi
  if [ "$got" = "$want" ]; then
    echo "  pass: $desc"
  else
    echo "  FAIL: $desc (expected $want, got $got)"; failures=$((failures + 1))
  fi
}

make "$tmp/good" 1.2.3 1.2.3 1.2.3
expect ok   "valid version"                        "$tmp/good"
expect ok   "matching tag"                         "$tmp/good" --tag v1.2.3
expect ok   "prerelease tag"                       "$tmp/good" --tag v1.2.3-rc.1
expect fail "tag for another version"              "$tmp/good" --tag v1.2.4
expect fail "tag without v"                        "$tmp/good" --tag 1.2.3
expect fail "tag with leading zero"                "$tmp/good" --tag v01.2.3

make "$tmp/zero-lead" 01.2.3 01.2.3 01.2.3
expect fail "manifest part with leading zero"      "$tmp/zero-lead"
make "$tmp/all-zero" 0.0.0 0.0.0 0.0.0
expect fail "all-zero version"                     "$tmp/all-zero"
make "$tmp/too-big" 1.65536.0 1.65536.0 1.65536.0
expect fail "part above 65535"                     "$tmp/too-big"
make "$tmp/too-long" 1.2.3.4.5 1.2.3.4.5 1.2.3.4.5
expect fail "more than four parts"                 "$tmp/too-long"
make "$tmp/mismatch" 1.2.3 1.2.4 1.2.3
expect fail "manifests disagree"                   "$tmp/mismatch"
make "$tmp/no-section" 1.2.3 1.2.3 9.9.9
expect fail "no CHANGELOG section"                 "$tmp/no-section"

notes="$tmp/notes.md"
python3 "$check" --root "$tmp/good" --tag v1.2.3 --notes "$notes" >/dev/null
if grep -q 'Something' "$notes" && ! grep -qE 'Older|example.invalid' "$notes"; then
  echo "  pass: notes contain only the version's section, without link definitions"
else
  echo "  FAIL: notes extraction"; failures=$((failures + 1))
fi

if [ "$failures" -ne 0 ]; then
  echo "release-check test: $failures failure(s)"; exit 1
fi
echo "release-check test: ok"
