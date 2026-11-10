#!/usr/bin/env python3
"""Build a d77crux binary release directory from one crux.ninja ISO.

    make-binrepo.py --iso ISO --iso-url URL --out DIR --tag TAG PKG...

Copies the named package archives byte for byte out of the ISO, gives each a
public asset name without '#' (the d77crux-kernel convention:
name-version-release.pkg.tar.EXT, since `gh release upload` treats '#' as a
label separator) and writes DIR/TAG/manifest.txt. The manifest maps every
asset back to its CRUX file name and is ordered so that dependencies (from the
ISO's crux/setup.dependencies) come first. Sign it afterwards with signify:

    signify -S -s KEY.sec -m DIR/TAG/manifest.txt -x DIR/TAG/manifest.txt.sig

The layout DIR/TAG/<asset> mirrors a GitHub release download URL
(.../releases/download/TAG/<asset>), so a client only changes its base URL.
"""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

CRUX_NAME = re.compile(r"^(?P<name>.+)#(?P<version>[^#]+)-(?P<release>\d+)\.pkg\.tar\.(?P<ext>gz|bz2|xz|zst|lz)$")


def iso_listing(iso: Path) -> dict:
    out = subprocess.run(["bsdtar", "-tf", str(iso)], check=True, capture_output=True, text=True).stdout
    found = {}
    for path in out.splitlines():
        parts = path.split("/")
        m = CRUX_NAME.match(parts[-1])
        if m and len(parts) == 3 and parts[0] == "crux":
            if m["name"] in found:
                sys.exit(f"duplicate package name in ISO: {m['name']}")
            found[m["name"]] = (path, parts[1], m)
    return found


def dependency_order(iso: Path, names: list) -> list:
    text = subprocess.run(["bsdtar", "-xOf", str(iso), "crux/setup.dependencies"],
                          check=True, capture_output=True, text=True).stdout
    deps = {}
    for line in text.splitlines():
        if ":" in line:
            pkg, rest = line.split(":", 1)
            deps[pkg.strip()] = rest.split()
    wanted, order, seen = set(names), [], set()

    def visit(pkg):
        if pkg in seen:
            return
        seen.add(pkg)
        for dep in deps.get(pkg, []):
            if dep in wanted and dep != pkg:
                visit(dep)
        order.append(pkg)

    for pkg in sorted(names):
        visit(pkg)
    return order


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True, type=Path)
    ap.add_argument("--iso-url", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--series", default="3.8")
    ap.add_argument("--arch", default="x86_64")
    ap.add_argument("packages", nargs="+")
    a = ap.parse_args()

    h = hashlib.sha256()
    with open(a.iso, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    iso_sha = h.hexdigest()
    listing = iso_listing(a.iso)
    missing = [p for p in a.packages if p not in listing]
    if missing:
        sys.exit(f"not in ISO: {' '.join(missing)}")

    dest = a.out / a.tag
    dest.mkdir(parents=True, exist_ok=False)
    lines = [
        "format\td77crux-binpkg 1",
        f"tag\t{a.tag}",
        f"series\t{a.series}",
        f"arch\t{a.arch}",
        f"iso_url\t{a.iso_url}",
        f"iso_sha256\t{iso_sha}",
        "# pkg name version release collection origin asset crux_file size sha256",
    ]
    for name in dependency_order(a.iso, a.packages):
        path, collection, m = listing[name]
        data = subprocess.run(["bsdtar", "-xOf", str(a.iso), path], check=True, capture_output=True).stdout
        asset = f"{m['name']}-{m['version']}-{m['release']}.pkg.tar.{m['ext']}"
        (dest / asset).write_bytes(data)
        lines.append("\t".join(["pkg", name, m["version"], m["release"], collection, "crux.ninja-iso",
                                asset, path.rsplit("/", 1)[-1], str(len(data)),
                                hashlib.sha256(data).hexdigest()]))
    (dest / "manifest.txt").write_text("\n".join(lines) + "\n")
    print(dest / "manifest.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
