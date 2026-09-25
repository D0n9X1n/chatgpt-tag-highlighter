#!/usr/bin/env bash
# Self-test for scripts/publish-wiki.sh and scripts/check-wiki.py.
# Uses only temp directories; never touches the real wiki or network.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
publisher="$root/scripts/publish-wiki.sh"
checker="$root/scripts/check-wiki.py"
workflow="$root/.github/workflows/publish-wiki.yml"

fail() { printf 'wiki publish test: %s\n' "$1" >&2; exit 1; }

[[ -x "$publisher" ]] || fail "publisher is missing or not executable"
[[ -x "$checker" ]] || fail "checker is missing or not executable"
[[ -f "$workflow" ]] || fail "workflow is missing"
grep -Eq 'actions/checkout@[0-9a-f]{40}' "$workflow" || fail "workflow checkout is not pinned to a commit SHA"
grep -q 'scripts/publish-wiki.sh' "$workflow" || fail "workflow does not run the publisher"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# ---- publisher ----
source_dir="$tmp/source"
wiki_repo="$tmp/wiki"
mkdir -p "$source_dir"
git init -q -b master "$wiki_repo"
git -C "$wiki_repo" config user.name test
git -C "$wiki_repo" config user.email test@example.invalid
printf '# stale\n' > "$wiki_repo/Stale.md"
printf '# old\n' > "$wiki_repo/Keep.md"
git -C "$wiki_repo" add --all
git -C "$wiki_repo" commit -q -m seed

printf '# home\n' > "$source_dir/Home.md"
printf '# 首页\n' > "$source_dir/Home-zh-CN.md"
printf '# current\n' > "$source_dir/Keep.md"
printf 'not a wiki page\n' > "$source_dir/ignored.txt"

out="$tmp/out1"
GITHUB_OUTPUT="$out" "$publisher" "$source_dir" "$wiki_repo" 0123456789abcdef >/dev/null
[[ "$(<"$out")" == "changed=true" ]] || fail "changed publish did not request a push"
[[ "$(git -C "$wiki_repo" branch --show-current)" == "master" ]] || fail "publisher changed branch"
[[ -f "$wiki_repo/Home-zh-CN.md" ]] || fail "publisher omitted the Chinese page"
[[ "$(<"$wiki_repo/Keep.md")" == "# current" ]] || fail "publisher did not update a page"
[[ ! -e "$wiki_repo/Stale.md" ]] || fail "publisher kept a page deleted from the source"
[[ ! -e "$wiki_repo/ignored.txt" ]] || fail "publisher copied a non-Markdown file"
[[ "$(git -C "$wiki_repo" rev-list --count HEAD)" == "2" ]] || fail "first publish did not create exactly one commit"
[[ "$(git -C "$wiki_repo" log -1 --pretty=%s)" == "Publish wiki from 0123456" ]] || fail "commit does not identify the source SHA"
[[ "$(git -C "$wiki_repo" log -1 --pretty=%an)" == "github-actions[bot]" ]] || fail "commit author is not github-actions[bot]"

out="$tmp/out2"
GITHUB_OUTPUT="$out" "$publisher" "$source_dir" "$wiki_repo" 0123456789abcdef >/dev/null
[[ "$(<"$out")" == "changed=false" ]] || fail "unchanged publish requested a push"
[[ "$(git -C "$wiki_repo" rev-list --count HEAD)" == "2" ]] || fail "unchanged publish created a commit"

git -C "$wiki_repo" checkout -q -b other
if "$publisher" "$source_dir" "$wiki_repo" 0123456789abcdef >/dev/null 2>&1; then fail "publisher accepted a non-master branch"; fi
git -C "$wiki_repo" checkout -q master
if "$publisher" "$tmp/missing" "$wiki_repo" 0123456789abcdef >/dev/null 2>&1; then fail "publisher accepted a missing source"; fi

# ---- checker ----
seed() {
  mkdir -p "$1"
  printf '# Home\n\n[简体中文](Home-zh-CN)\n\n### Pages\n\n- [Page](Page)\n' > "$1/Home.md"
  printf '# 首页\n\n[English](Home)\n\n### 页面\n\n- [页面](Page-zh-CN)\n' > "$1/Home-zh-CN.md"
  printf '# Page\n\n[简体中文](Page-zh-CN)\n\n## Part\n\nBack to [Home](Home).\n' > "$1/Page.md"
  printf '# 页面\n\n[English](Page)\n\n## 部分\n\n返回[首页](Home-zh-CN)。\n' > "$1/Page-zh-CN.md"
}
expect_fail() {  # DIR PATTERN
  if python3 "$checker" "$1" >/dev/null 2>"$tmp/err"; then fail "checker accepted $1"; fi
  grep -q "$2" "$tmp/err" || fail "checker error for $1 lacked: $2 (got: $(cat "$tmp/err"))"
}

seed "$tmp/good"
python3 "$checker" "$tmp/good" | grep -q 'check-wiki: ok (4 pages)' || fail "checker rejected a valid wiki"

seed "$tmp/unpaired"; rm "$tmp/unpaired/Page-zh-CN.md"
expect_fail "$tmp/unpaired" 'missing language counterpart'

seed "$tmp/mdlink"; printf 'See [Page](Page.md).\n' >> "$tmp/mdlink/Home.md"
expect_fail "$tmp/mdlink" 'must omit .md'

seed "$tmp/depth"; printf '\n## Extra\n' >> "$tmp/depth/Page-zh-CN.md"
expect_fail "$tmp/depth" 'heading-depth sequences differ'

seed "$tmp/crosslang"; printf 'See [页面](Page-zh-CN).\n' >> "$tmp/crosslang/Home.md"
expect_fail "$tmp/crosslang" 'must stay in the same language'

seed "$tmp/noindex"; printf '# Home\n\n[简体中文](Home-zh-CN)\n\n### Pages\n' > "$tmp/noindex/Home.md"
expect_fail "$tmp/noindex" 'missing link to Page'

seed "$tmp/fenced"; printf '\n```sh\n# not a heading\n```\n' >> "$tmp/fenced/Page.md"
python3 "$checker" "$tmp/fenced" >/dev/null || fail "checker counted a heading inside a code fence"

printf 'wiki publish test: ok\n'
