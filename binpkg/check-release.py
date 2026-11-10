#!/usr/bin/env python3
"""Check that a GitHub release holds exactly what its manifest lists.

    check-release.py MANIFEST ASSETS_JSON

ASSETS_JSON is the release's asset list as returned by
`gh api --paginate repos/OWNER/REPO/releases/ID/assets` (a JSON array, or
several arrays concatenated by --paginate). Every `pkg` line of the manifest
must have an uploaded asset of the same name and size; besides those, the
release may only hold manifest.txt and manifest.txt.sig. Exit status 1 and a
list of problems otherwise.
"""

import json
import sys


def load_assets(text: str) -> dict:
    assets, decoder, pos = {}, json.JSONDecoder(), 0
    text = text.strip()
    while pos < len(text):
        chunk, pos = decoder.raw_decode(text, pos)
        while pos < len(text) and text[pos].isspace():
            pos += 1
        for a in chunk:
            if a.get("state", "uploaded") != "uploaded":
                continue
            assets[a["name"]] = a["size"]
    return assets


def main() -> int:
    manifest_path, assets_path = sys.argv[1:3]
    expected = {}
    for line in open(manifest_path):
        f = line.rstrip("\n").split("\t")
        if f[0] == "pkg":
            expected[f[6]] = int(f[8])
    assets = load_assets(open(assets_path).read())
    problems = []
    for name, size in sorted(expected.items()):
        if name not in assets:
            problems.append(f"missing asset {name}")
        elif assets[name] != size:
            problems.append(f"{name}: {assets[name]} bytes, manifest says {size}")
    extra = set(assets) - set(expected) - {"manifest.txt", "manifest.txt.sig"}
    problems += [f"unexpected asset {n}" for n in sorted(extra)]
    for n in ("manifest.txt", "manifest.txt.sig"):
        if n not in assets:
            problems.append(f"missing {n}")
    for p in problems:
        print(p)
    print(f"{len(expected)} packages expected, {len(assets)} assets, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
