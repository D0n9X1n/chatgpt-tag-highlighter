#!/usr/bin/env python3
"""Validate the repo-sourced wiki: English/-zh-CN page pairs, matching
heading depths, bare same-language page links, and a complete Home index.

Usage: python3 scripts/check-wiki.py [WIKI_DIR]   (default: wiki/)
Adapted from SonicTerm's scripts/check-wiki.py. Python 3 stdlib only.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

CHINESE_SUFFIX = "-zh-CN"
LEGACY_MARKERS = frozenset({"## English", "## 中文"})
HEADING_PATTERN = re.compile(r"^(#{1,6})[ \t]+")
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
FENCE_PATTERN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
EXTERNAL_SCHEMES = frozenset(
    {"data", "ftp", "ftps", "http", "https", "irc", "ircs", "mailto", "news", "ssh", "tel"}
)


def counterpart_stem(stem: str) -> str:
    """Return the other-language page name."""
    return stem.removesuffix(CHINESE_SUFFIX) if stem.endswith(CHINESE_SUFFIX) else stem + CHINESE_SUFFIX


def outside_fences(lines: list[str]):
    """Yield (line_number, line) for lines outside fenced code blocks."""
    fence: str | None = None
    fence_length = 0
    for line_number, line in enumerate(lines, start=1):
        marker = FENCE_PATTERN.match(line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence, fence_length = run[0], len(run)
            elif run[0] == fence and len(run) >= fence_length:
                fence, fence_length = None, 0
            continue
        if fence is None:
            yield line_number, line


def heading_depths(lines: list[str]) -> list[int]:
    """Return heading depths outside fenced code blocks in source order."""
    return [len(m.group(1)) for _, line in outside_fences(lines) if (m := HEADING_PATTERN.match(line))]


def link_targets(lines: list[str]) -> list[tuple[int, str]]:
    """Return inline Markdown link destinations outside fenced code blocks."""
    links: list[tuple[int, str]] = []
    for line_number, line in outside_fences(lines):
        for match in LINK_PATTERN.finditer(line):
            destination = match.group(1).strip()
            if destination.startswith("<") and destination.endswith(">"):
                destination = destination[1:-1].strip()
            links.append((line_number, destination))
    return links


def local_link_stems(lines: list[str]) -> set[str]:
    """Return local page destinations, excluding URLs and same-page anchors."""
    linked: set[str] = set()
    for _, target in link_targets(lines):
        parsed = urlsplit(unquote(target))
        if target.startswith("#") or parsed.scheme or parsed.netloc:
            continue
        linked.add(parsed.path)
    return linked


def validate_links(name: str, stem: str, lines: list[str], page_stems: set[str], errors: list[str]) -> None:
    """Validate bare cross-page links while allowing anchors and URLs."""
    for line_number, raw_target in link_targets(lines):
        target = unquote(raw_target)
        if target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme.lower() in EXTERNAL_SCHEMES or parsed.netloc:
            continue
        page_target = parsed.path
        if page_target.endswith(".md"):
            errors.append(f"{name}:{line_number}: cross-page link must omit .md: {raw_target}")
        elif page_target not in page_stems:
            errors.append(f"{name}:{line_number}: cross-page link target does not exist: {raw_target}")
        elif page_target != counterpart_stem(stem) and page_target.endswith(CHINESE_SUFFIX) != stem.endswith(CHINESE_SUFFIX):
            errors.append(f"{name}:{line_number}: cross-page link must stay in the same language: {raw_target}")


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    wiki = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "wiki"
    if not wiki.is_dir():
        print(f"check-wiki: wiki directory does not exist: {wiki}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for nested in sorted(p for p in wiki.rglob("*.md") if p.parent != wiki):
        errors.append(f"wiki/{nested.relative_to(wiki)}: nested Markdown pages are not allowed")

    pages = sorted(wiki.glob("*.md"))
    if not pages:
        errors.append("wiki: no Markdown pages found")
    page_stems = {p.stem for p in pages}
    lines_by_stem: dict[str, list[str]] = {}

    for path in pages:
        name = f"wiki/{path.name}"
        lines = path.read_text(encoding="utf-8").splitlines()
        lines_by_stem[path.stem] = lines
        for marker in sorted(LEGACY_MARKERS.intersection(lines)):
            errors.append(f"{name}: legacy language marker {marker!r}; use separate files")
        counterpart = counterpart_stem(path.stem)
        if counterpart not in page_stems:
            errors.append(f"{name}: missing language counterpart: {counterpart}")
        if counterpart not in local_link_stems(lines):
            errors.append(f"{name}: missing language-switch link to {counterpart}")
        validate_links(name, path.stem, lines, page_stems, errors)

    for stem, english in lines_by_stem.items():
        if stem.endswith(CHINESE_SUFFIX) or counterpart_stem(stem) not in lines_by_stem:
            continue
        en, zh = heading_depths(english), heading_depths(lines_by_stem[counterpart_stem(stem)])
        if en != zh:
            errors.append(f"wiki/{stem}.md: heading-depth sequences differ from wiki/{counterpart_stem(stem)}.md: English {en}; Chinese {zh}")

    for suffix in ("", CHINESE_SUFFIX):
        home = f"Home{suffix}"
        if home not in lines_by_stem:
            errors.append(f"wiki/{home}.md: required page is missing")
            continue
        same_language = {s for s in page_stems if s.endswith(CHINESE_SUFFIX) == bool(suffix)} - {home}
        for stem in sorted(same_language - local_link_stems(lines_by_stem[home])):
            errors.append(f"wiki/{home}.md: missing link to {stem}")

    if errors:
        for error in sorted(errors):
            print(f"check-wiki: {error}", file=sys.stderr)
        return 1
    print(f"check-wiki: ok ({len(pages)} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
