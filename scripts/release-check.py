#!/usr/bin/env python3
"""Release consistency checks, shared by CI and the release workflow.

  scripts/release-check.py                    both manifests agree, CHANGELOG has the section
  scripts/release-check.py --tag v1.2.3       ...and the tag matches the manifest version
  scripts/release-check.py --tag v1.2.3 --notes notes.md
                                              ...and write that CHANGELOG section to notes.md
  --github-output                             append version=, tag=, prerelease= to $GITHUB_OUTPUT

A tag may carry a prerelease suffix (v1.2.3-rc.1). Chrome manifests must stay
numeric, so the suffix only marks the GitHub Release as a prerelease; the
numeric part must equal the manifest version.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

MANIFESTS = ('src/manifest.chrome.json', 'src/manifest.firefox.json')
# Chrome: 1-4 dot-separated integers, each 0-65535, no leading zeros, not all zero.
PART = r'(?:0|[1-9]\d{0,4})'
CHROME_VERSION = re.compile(rf'{PART}(?:\.{PART}){{0,3}}')
TAG = re.compile(rf'v({PART}\.{PART}\.{PART})(-[0-9A-Za-z.-]+)?')
LINK_DEF = re.compile(r'^\[[^\]]+\]:\s+\S+\s*$', re.M)


def fail(message):
    prefix = '::error::' if os.environ.get('GITHUB_ACTIONS') else 'error: '
    print(prefix + message, file=sys.stderr)
    sys.exit(1)


def changelog_section(text, version):
    """Body of '## [version] ...' up to the next '## ' heading, without link definitions."""
    match = re.search(rf'^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)', text, re.M | re.S)
    if not match:
        return None
    return LINK_DEF.sub('', match.group(1)).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tag', help='release tag to validate, e.g. v1.2.3 or v1.2.3-rc.1')
    parser.add_argument('--notes', help='write the matching CHANGELOG section to this file')
    parser.add_argument('--github-output', action='store_true', help='append outputs to $GITHUB_OUTPUT')
    parser.add_argument('--root', default=Path(__file__).resolve().parent.parent, help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = Path(args.root)

    versions = {}
    for name in MANIFESTS:
        try:
            versions[name] = json.loads((root / name).read_text(encoding='utf-8'))['version']
        except (OSError, ValueError, KeyError) as exc:
            fail(f'cannot read "version" from {name}: {exc}')
    if len(set(versions.values())) != 1:
        fail(f'manifest versions differ: {versions}')
    version = next(iter(versions.values()))
    parts = version.split('.')
    if (not CHROME_VERSION.fullmatch(version) or any(int(p) > 65535 for p in parts)
            or all(int(p) == 0 for p in parts)):
        fail(f'manifest version {version!r} is not a valid Chrome version '
             '(1-4 numbers, each 0-65535, no leading zeros, not all zero)')

    tag, prerelease = f'v{version}', False
    if args.tag:
        match = TAG.fullmatch(args.tag)
        if not match:
            fail(f'tag {args.tag!r} is not vX.Y.Z or vX.Y.Z-suffix')
        if match.group(1) != version:
            fail(f'tag {args.tag} does not match manifest version {version}; bump both manifests first')
        tag, prerelease = args.tag, bool(match.group(2))

    section = changelog_section((root / 'CHANGELOG.md').read_text(encoding='utf-8'), version)
    if not section:
        fail(f'CHANGELOG.md has no non-empty "## [{version}]" section')

    if args.notes:
        Path(args.notes).write_text(section + '\n', encoding='utf-8')
    if args.github_output:
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
            out.write(f'version={version}\ntag={tag}\nprerelease={str(prerelease).lower()}\n')

    print(f'ok: version={version} tag={tag} prerelease={str(prerelease).lower()} '
          f'changelog_lines={len(section.splitlines())}')


if __name__ == '__main__':
    main()
