#!/usr/bin/env python3
"""
Investigate upstream sources referenced by Pkgfile (CRUX) / spkgbuild (Venom
scratchpkg) build files and bump `version=` (resetting `release=1`) when a
newer upstream version is found.

Design goals:
  - No third-party dependencies (stdlib only) so it runs on a bare
    ubuntu-latest runner without an extra `pip install` step.
  - Conservative: a package is only touched when we are reasonably
    confident about the new version string. Anything ambiguous is skipped
    and reported, never guessed.
  - Works across CRUX's `source=(url1 url2 ...)` and Venom's
    `source="url1 url2"` syntax, and handles both `$version`-templated
    URLs and URLs with the version hardcoded in the filename/path.

Usage:
  check_updates.py --root . --exclude-file .github/autoupdate-exclude.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import quote, urlsplit

TIMEOUT = 20
UA = "d77-version-check-bot/1.0 (+https://github.com/dani-77)"


def http_get(url: str, headers: dict | None = None) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError) as e:
        print(f"    ! request failed for {url}: {e}", file=sys.stderr)
        return None


def http_json(url: str, headers: dict | None = None):
    raw = http_get(url, headers)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------
# Version helpers
# --------------------------------------------------------------------------

def numeric_tuple(s: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", s))


EXT_RE = re.compile(
    r"\.(tar\.(gz|bz2|xz|zst|lz)|tgz|tbz2?|txz|zip|7z|rar|deb|rpm|exe|msi|dmg|"
    r"appimage|pkg|run|whl)$",
    re.I,
)
PLATFORM_SUFFIX_RE = re.compile(
    r"[-_.](?:linux|windows|win32|win64|macos|osx|darwin|amd64|x86[-_]?64|x64|"
    r"x86|i[36]86|arm64|aarch64|src|source|all|any|static|portable)$",
    re.I,
)
# A candidate must reduce to *exactly* this shape to be trusted: an optional
# v/r prefix, digits, and dot/dash-separated digit groups with at most one
# trailing letter (covers "6.5", "r41", "1.4w", "0.74-3", "v.1.5.0", ...).
VERSION_RE = re.compile(r"^[vVrR]?\.?\d+(?:[.\-_]\d+){0,6}[A-Za-z]?$")


def normalize_candidate(old_version: str, name: str, candidate: str) -> str | None:
    """Reformat a raw tag/filename candidate to match the style already used
    by `old_version` (mainly: whether it keeps a leading 'v'), stripping any
    archive extension / platform qualifier a filename-based candidate may
    carry. Returns None if what's left doesn't look like a clean version."""
    c = candidate.strip()

    # Strip a trailing archive/installer extension (possibly repeated, e.g.
    # ".tar.gz"), then any trailing platform/arch qualifier, iterating since
    # a filename can carry both ("-windows.zip").
    changed = True
    while changed:
        changed = False
        m = EXT_RE.search(c)
        if m:
            c = c[: m.start()]
            changed = True
        m = PLATFORM_SUFFIX_RE.search(c)
        if m:
            c = c[: m.start()]
            changed = True

    low = c.lower()
    nlow = name.lower()
    for prefix in (nlow + "-", nlow + "_", nlow):
        if low.startswith(prefix):
            c = c[len(prefix):]
            break

    if not old_version.lstrip().lower().startswith("v"):
        if re.match(r"^[vV]\d", c):
            c = c[1:]

    return c if VERSION_RE.match(c) else None


def sanity_gate(old_version: str, candidate: str) -> bool:
    """Reject candidates that don't look like a clean version bump of the
    same shape as the old version (protects against picking up unrelated
    tag/filename text)."""
    if not candidate or candidate == old_version:
        return False
    old_t, new_t = numeric_tuple(old_version), numeric_tuple(candidate)
    if not new_t:
        return False
    if abs(len(new_t) - len(old_t)) > 1:
        return False
    if len(candidate) > len(old_version) + 15:
        return False
    pad = max(len(old_t), len(new_t))
    old_p = old_t + (0,) * (pad - len(old_t))
    new_p = new_t + (0,) * (pad - len(new_t))
    return new_p > old_p


def pick_best_candidate(old_version: str, name: str, raw_candidates: list[str]) -> str | None:
    best = None
    best_tuple = numeric_tuple(old_version)
    for raw in raw_candidates:
        cand = normalize_candidate(old_version, name, raw)
        if not sanity_gate(old_version, cand):
            continue
        t = numeric_tuple(cand)
        pad = max(len(t), len(best_tuple))
        if (t + (0,) * (pad - len(t))) > (best_tuple + (0,) * (pad - len(best_tuple))):
            best, best_tuple = cand, t
    return best


# --------------------------------------------------------------------------
# Upstream detection strategies
# --------------------------------------------------------------------------

def github_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def check_github(owner: str, repo: str, name: str, old_version: str) -> str | None:
    data = http_json(
        f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=100",
        github_headers(),
    )
    candidates = []
    if isinstance(data, list):
        for rel in data:
            if rel.get("draft") or rel.get("prerelease"):
                continue
            tag = rel.get("tag_name")
            if tag:
                candidates.append(tag)
    best = pick_best_candidate(old_version, name, candidates)
    if best:
        return best

    data = http_json(
        f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=100",
        github_headers(),
    )
    candidates = []
    if isinstance(data, list):
        for t in data:
            n = t.get("name")
            if n:
                candidates.append(n)
    return pick_best_candidate(old_version, name, candidates)


def check_gitlab(host: str, owner: str, repo: str, name: str, old_version: str) -> str | None:
    project = quote(f"{owner}/{repo}", safe="")
    data = http_json(f"https://{host}/api/v4/projects/{project}/repository/tags?per_page=100")
    candidates = []
    if isinstance(data, list):
        for t in data:
            n = t.get("name")
            if n:
                candidates.append(n)
    return pick_best_candidate(old_version, name, candidates)


def check_sourceforge(project: str, name: str, old_version: str) -> str | None:
    data = http_json(f"https://sourceforge.net/projects/{project}/best_release.json")
    if not isinstance(data, dict):
        return None
    candidates = []
    rel = data.get("release") or {}
    for key in ("filename", "url"):
        v = rel.get(key)
        if v:
            candidates.append(os.path.basename(v))
    return pick_best_candidate(old_version, name, candidates)


def check_generic_directory(dir_url: str, name: str, old_version: str) -> str | None:
    raw = http_get(dir_url)
    if raw is None:
        return None
    html = raw.decode("utf-8", errors="ignore")
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    candidates = [os.path.basename(h.rstrip("/")) for h in hrefs if re.search(r"\d", h)]
    return pick_best_candidate(old_version, name, candidates)


GITHUB_RE = re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/]+)/")
GITLAB_RE = re.compile(r"^https?://(gitlab\.[^/]+)/(.+?)/-/(?:archive|raw|releases)/")
SOURCEFORGE_RE = re.compile(r"sourceforge\.net/projects?/([^/]+)/")


def detect_latest(url_template: str, url_concrete: str, name: str, old_version: str) -> tuple[str | None, str]:
    """Returns (new_version_or_None, strategy_name)."""
    m = GITHUB_RE.match(url_concrete)
    if m:
        owner, repo = m.group(1), m.group(2).removesuffix(".git")
        return check_github(owner, repo, name, old_version), "github"

    m = GITLAB_RE.match(url_concrete)
    if m:
        host, path = m.group(1), m.group(2)
        parts = path.split("/")
        owner, repo = "/".join(parts[:-1]) or parts[0], parts[-1]
        return check_gitlab(host, owner, repo, name, old_version), "gitlab"

    m = SOURCEFORGE_RE.search(url_concrete)
    if m:
        return check_sourceforge(m.group(1), name, old_version), "sourceforge"

    if url_concrete.startswith("ftp://"):
        return None, "unsupported(ftp)"

    parts = urlsplit(url_concrete)
    dir_url = url_concrete.rsplit("/", 1)[0] + "/"
    if parts.scheme in ("http", "https"):
        return check_generic_directory(dir_url, name, old_version), "directory-listing"

    return None, "unsupported"


# --------------------------------------------------------------------------
# Build-file parsing (CRUX Pkgfile / Venom spkgbuild)
# --------------------------------------------------------------------------

@dataclass
class Pkg:
    dir: str
    file: str
    kind: str  # "Pkgfile" or "spkgbuild"
    name: str
    version: str
    version_span: tuple[int, int]
    release_span: tuple[int, int] | None
    source_text: str
    source_span: tuple[int, int]


def find_field_span(text: str, field: str) -> tuple[int, int] | None:
    m = re.search(rf"(?m)^{field}=.*$", text)
    return (m.start(), m.end()) if m else None


def parse_build_file(dirpath: str, filename: str, text: str) -> Pkg | None:
    name_m = re.search(r"(?m)^name=(\S+)\s*$", text)
    version_m = re.search(r"(?m)^version=(\S+)\s*$", text)
    if not name_m or not version_m:
        return None
    name = name_m.group(1)
    version = version_m.group(1)
    version_span = (version_m.start(), version_m.end())
    release_span = find_field_span(text, "release")

    if filename == "Pkgfile":
        src_m = re.search(r"source=\((.*?)\)", text, re.S)
    else:
        src_m = re.search(r'source="([^"]*)"', text, re.S)
    if not src_m:
        return None
    source_text = src_m.group(1)
    source_span = (src_m.start(1), src_m.end(1))

    return Pkg(dirpath, filename, filename, name, version, version_span, release_span, source_text, source_span)


def first_source_url(pkg: Pkg) -> str | None:
    tokens = pkg.source_text.split()
    return tokens[0] if tokens else None


def substitute_vars(url: str, pkg: Pkg) -> str:
    out = url.replace("$name", pkg.name).replace("${name}", pkg.name)
    out = out.replace("$version", pkg.version).replace("${version}", pkg.version)
    out = re.sub(r"\$\{version%\.\*\}", pkg.version.rsplit(".", 1)[0], out)
    return out


def apply_update(text: str, pkg: Pkg, new_version: str) -> str | None:
    """Returns the updated file text, or None if the change is not safe to
    apply (a stale copy of the old version would be left behind, e.g. a
    build() step that hardcodes a version-derived filename, or a tag naming
    scheme that embeds the version more than once in inconsistent forms)."""
    new_text = text[:pkg.version_span[0]] + f"version={new_version}" + text[pkg.version_span[1]:]
    shift = len(f"version={new_version}") - (pkg.version_span[1] - pkg.version_span[0])

    if pkg.release_span:
        rs, re_ = pkg.release_span[0] + shift, pkg.release_span[1] + shift
        new_text = new_text[:rs] + "release=1" + new_text[re_:]
        shift += len("release=1") - (re_ - rs)

    # Bare single-character versions (rare) are too collision-prone to hunt
    # for across the whole file (e.g. "4" could match an unrelated "-j4"
    # build flag) -- restrict those to the source=() / source="" block only.
    # Longer versions are searched for across the *whole* file, since a
    # build() step occasionally hardcodes a version-derived filename outside
    # of source= (see e.g. frostwire's Pkgfile).
    if len(pkg.version) >= 2:
        scan_start, scan_end = 0, len(new_text)
    else:
        scan_start = pkg.source_span[0] + shift
        scan_end = pkg.source_span[1] + shift

    scan_region = new_text[scan_start:scan_end]

    # GitHub-style releases commonly spell the same version two ways in one
    # URL: a 'v'-prefixed tag in the path and a bare version in the asset
    # filename (.../releases/download/v1.8.4/notable_1.8.4_amd64.deb). Both
    # need to move together, so replace v-prefixed occurrences first
    # (preserving the v/V), then bare occurrences.
    vprefixed_re = rf"(?<![0-9A-Za-z.])([vV]){re.escape(pkg.version)}(?![0-9A-Za-z])"
    scan_region_new = re.sub(vprefixed_re, lambda m: m.group(1) + new_version, scan_region)
    token_re = rf"(?<![0-9A-Za-z.]){re.escape(pkg.version)}(?![0-9A-Za-z])"
    scan_region_new = re.sub(token_re, new_version, scan_region_new)

    # Final safety net: if any form of the old version is still lurking
    # (e.g. an odd tag scheme like "keybinder-3.0-v0.3.2" where 'v' isn't a
    # clean token boundary either), bail out rather than leave a broken,
    # inconsistent source URL. In practice the upstream candidate-selection
    # step already filters out such odd tag shapes before we get here.
    stale_re = rf"(?<![0-9A-UW-Za-uw-z]){re.escape(pkg.version)}(?![0-9A-Za-z])"
    if re.search(stale_re, scan_region_new):
        return None  # a stale occurrence of the old version remains -> unsafe

    return new_text[:scan_start] + scan_region_new + new_text[scan_end:]


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--exclude-file", default=None)
    ap.add_argument("--summary-file", default="update-summary.md")
    args = ap.parse_args()

    excluded: set[str] = set()
    if args.exclude_file and os.path.isfile(args.exclude_file):
        with open(args.exclude_file) as f:
            excluded = {ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")}

    updated: list[tuple[str, str, str, str]] = []  # name, old, new, strategy
    skipped: list[tuple[str, str]] = []  # name, reason
    excluded_hit: list[str] = []

    for entry in sorted(os.listdir(args.root)):
        dirpath = os.path.join(args.root, entry)
        if not os.path.isdir(dirpath) or entry.startswith("."):
            continue
        if entry in excluded:
            excluded_hit.append(entry)
            continue

        for filename in ("Pkgfile", "spkgbuild"):
            fpath = os.path.join(dirpath, filename)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, encoding="utf-8", errors="ignore") as f:
                text = f.read()

            pkg = parse_build_file(dirpath, filename, text)
            if pkg is None:
                skipped.append((entry, "could not parse name/version/source"))
                break

            url = first_source_url(pkg)
            if not url:
                skipped.append((pkg.name, "no source URL found"))
                break

            concrete = substitute_vars(url, pkg)
            print(f"[{pkg.name}] current={pkg.version} source={concrete}")
            new_version, strategy = detect_latest(url, concrete, pkg.name, pkg.version)

            if not new_version:
                skipped.append((pkg.name, f"no confident newer version found (strategy: {strategy})"))
                break

            print(f"    -> found {new_version} via {strategy}")
            new_text = apply_update(text, pkg, new_version)
            if new_text is None:
                skipped.append((pkg.name, f"found {new_version} via {strategy}, but the old version "
                                           "string appears ambiguously in the source URL(s) -- "
                                           "skipped to avoid a broken/partial edit"))
                break
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(new_text)
            updated.append((pkg.name, pkg.version, new_version, strategy))
            break

    lines = ["# Package version check\n"]
    if updated:
        lines.append("## Updated\n")
        lines.append("| Package | Old version | New version | Source |")
        lines.append("|---|---|---|---|")
        for name, old, new, strategy in updated:
            lines.append(f"| `{name}` | {old} | **{new}** | {strategy} |")
        lines.append("")
    else:
        lines.append("No packages needed an update.\n")

    if excluded_hit:
        lines.append(f"## Excluded from checks ({len(excluded_hit)})\n")
        lines.append(", ".join(f"`{n}`" for n in sorted(excluded_hit)))
        lines.append("")

    if skipped:
        lines.append(f"## Skipped / needs manual check ({len(skipped)})\n")
        lines.append("| Package | Reason |")
        lines.append("|---|---|")
        for name, reason in skipped:
            lines.append(f"| `{name}` | {reason} |")
        lines.append("")

    summary = "\n".join(lines)
    with open(args.summary_file, "w") as f:
        f.write(summary)
    print("\n" + summary)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"changed={'true' if updated else 'false'}\n")

    gh_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary:
        with open(gh_summary, "a") as f:
            f.write(summary + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
