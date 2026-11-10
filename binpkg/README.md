# binpkg — CRUX binary packages for sysvd77 installs

Status: **prototype**. The client and the release generator work and passed a
VM trial (below). The scheduled import workflow, the production signing key
and the port for the client do not exist yet.

The goal (see `AGENTS.md`): keep installed sysvd77 systems up to date from
binary packages, reusing the archives in Jaeger's updated CRUX ISOs
(crux.ninja) byte for byte, adding only what this project builds itself (the
kernel and the d77crux extras), and publishing everything as GitHub Releases
of this repository. The sysvd77 ISO is rebuilt rarely (every few months, by
hand); installs are updated through this channel, not by new ISOs.

This directory is excluded from the httpup collection
(`.httpup-repgen-ignore`), so it never reaches `/usr/ports/d77crux`.

| File | What |
|---|---|
| `make-binrepo.py` | Builds a release directory from one ISO: archives copied byte for byte, public asset names, `manifest.txt` |
| `d77crux-update` | Client: `plan` / `apply` against `pkginfo -i`, verify everything before the first `pkgadd` |

The VM tests that exercise these against a real sysvd77 install live in
sysv-d77 (`scripts/install-vm-mocinha.sh`, `tests/vm-update-trial.py`).

## Manifest format (v1, as implemented)

Plain text, tab-separated, signed with signify (`manifest.txt.sig`, detached):

```
format      d77crux-binpkg 1
tag         crux-3.8-x86_64-20261109-5e15a2d0
series      3.8
arch        x86_64
iso_url     https://crux.ninja/updated-iso/crux-3.8-updated.iso
iso_sha256  5e15a2d0…
pkg  <name> <version> <release> <collection> <origin> <asset> <crux_file> <size> <sha256>
```

- `tag`: series, architecture, ISO date and the first 8 hex digits of the ISO
  digest. The digest is the import identity, because crux.ninja reuses the
  ISO's URL and name.
- `asset`: public name without `#`, the d77crux-kernel convention
  (`name-version-release.pkg.tar.xz`), since `gh release upload` reads `#` as
  a label separator. `crux_file` is the `name#version-release.pkg.tar.*` name
  the client restores before `pkgadd`.
- `pkg` lines are ordered with dependencies first (from the ISO's
  `crux/setup.dependencies`).
- Layout `<base>/<tag>/<asset>` matches GitHub's
  `…/releases/download/<tag>/<asset>`, so a test server and GitHub differ only
  in the base URL.

## Client behaviour (as implemented)

`d77crux-update [-c CONF] plan|apply`, with `BASE_URL`, `TAG`, `PUBKEY`,
`CACHE` in `/etc/d77crux-update.conf`.

1. Fetch `manifest.txt` and `.sig`, verify with `signify -V` against the
   configured public key, and check the format and tag.
2. Plan against `pkginfo -i`: `upgrade`, `current`, `not-installed` (skipped),
   `locked` (in `/var/lib/pkg/prt-get.locker`), `newer-installed`.
3. **Preparation:** download every planned archive and check its size and
   SHA-256. Any failure stops here: no `pkgadd` has run.
4. **Application:** `pkgadd -u` in manifest order (so `/etc/pkgadd.conf`
   UPGRADE rules apply), and log each package to `$CACHE/$TAG/applied`. A
   re-run plans again and continues from what is left.

## VM trial, 2026-11-10

Base: a VM installed from `sysv-d77-3.8-x86_64.iso` (2026-10-11, built on
crux.ninja ISO `cbb3e75f…`) by the ISO's own Mocinha 0.1.5 with
`/etc/mocinha.toml`; 347 packages. Release: four packages from crux.ninja ISO
`5e15a2d0…` (2026-11-09), signed with a throwaway test key, served over HTTP
from the host (QEMU user network, `10.0.2.2`).

| Package | Before | After |
|---|---|---|
| libnghttp2 | 1.70.0-1 | 1.71.0-1 |
| curl | 8.22.0-1 | 8.23.0-1 |
| nano | 9.2-1 | 9.3-1 |
| rsync | 3.5.1-1 | 3.5.2-1 |

- Update: signature verified, 4 archives verified, then 4 `pkgadd -u`
  (libnghttp2 before curl). `pkginfo` shows the new versions, the programs
  report them, `curl` links `nghttp2/1.71.0` and fetches over HTTP, and a
  second plan finds nothing to do. The updated disk passes Mocinha's boot proof
  and its `expect/sysv-d77.json` equivalence check.
- Missing archive (404 on rsync): stopped in preparation, "nothing installed".
- Altered archive (nano, one byte, same size): SHA-256 mismatch in
  preparation, "nothing installed".
- In both failure cases the SHA-256 of `/var/lib/pkg/db` is unchanged and the
  old versions still run.

Not covered: the full set, port hooks, `pkgadd.conf` rules in play, UEFI,
interruption during application, the production key and its delivery.

## Findings that shape the design

1. **Jaeger's snapshots change bytes without changing versions.** Between the
   2026-10-11 and 2026-11-09 ISOs, all 337 archives differ: 73 changed version
   and 263 did not. In a sample (bash, coreutils, gtk3, signify, xorg-xinit)
   the only differences are in gzip-compressed man pages (header timestamps),
   and the decompressed content and binaries are identical. A same-version
   byte change is therefore normal and is **not** an update.
2. **sysvd77 shadows some Jaeger packages.** Installs carry
   `at-spi2-core#2.60.6-1` and `gtk3#3.24.52-1` built by sysv-d77's
   `build-ports.sh`. The ISO has at-spi2-core 2.62.x (so the install is
   *older*), and gtk3 at the same version with different bytes. Without a
   supplier rule, a naive client would silently swap the project's builds for
   Jaeger's.
3. **The kernel release reuses its tag on a rebuild.** `build-kernel.yml`
   deletes and recreates `d77crux-kernel-<ver>-<rel>`. After a rebuild the same
   `name#version-release` has new bytes (sysv-d77 commit `fddbda0` re-pinned
   exactly this).
4. **`releases/latest` is the kernel.** It cannot be the update channel.

## Proposed design (next steps)

- **Complete manifests.** Each snapshot manifest lists the whole set, so an
  install made from a months-old ISO converges in one run, not one release at
  a time.
- **Package pool.** Store each `name-version-release` once (a long-lived pool
  release, or per-snapshot releases that reuse assets), and let each snapshot
  manifest reference it. The first bytes seen are canonical. A later
  same-version rebuild is recorded as `bytes differ, same version`, with the
  normalised content compared (gzip members decompressed), and is not
  republished. This avoids ~1.4 GiB per snapshot.
- **One supplier per name.** A supplier map, `jaeger-iso` | `d77crux` |
  `d77crux-kernel`, lives in this repo. A d77crux-supplied name hides
  Jaeger's archive of the same name. The manifest's `origin` field carries
  the supplier. The client never replaces a package with one from another
  supplier unless the manifest declares the migration.
- **Extras.** The kernel keeps building in CI. The userland ports that
  sysvd77 installs must be built against the snapshot's libraries in a CRUX
  chroot (sysv-d77's `crux-rootfs.sh` already makes one from the ISO), either
  in CI or on Daniel's CRUX machine where ports are signed. A Pkgfile version
  bump, or an ABI-relevant change in a dependency of the snapshot, triggers a
  rebuild.
- **Channel pointer.** A small signed `channel.txt` (current tag + manifest
  SHA-256) at a fixed URL, so clients find the newest snapshot without
  depending on `releases/latest`.
- **Import workflow** (scheduled + manual, serialised per series/arch):
  1. probe the published SHA-256 and stop if that digest is already imported;
  2. download, verify, and re-check the digest afterwards;
  3. extract and apply the supplier map, then add the kernel and extras;
  4. optionally cross-check every imported name/version/release against the
     signify-signed official CRUX ports;
  5. upload to a **draft** release, validate the asset list and sizes against
     the manifest, sign, and publish. Promotion stays manual at first.
- **Signing.** Daniel holds the production signify key and signs the manifest
  and channel pointer; the public key ships in the client's port. The test
  key used in the trial is throwaway. Jaeger's SHA-256 only checks the
  download; our signature attests "this is what we imported from that ISO".
- **Coexistence with prt-get.** The channel owns what came from the ISO and
  the sysvd77 extras. `prt-get` owns what the user installed. The client
  honours prt-get locks and ignores packages that are not in the manifest.
  After applying, it runs `revdep` (prt-utils) and lists local builds that
  need rebuilding after an ABI change.

## Protecting local builds (required before any real-hardware run)

The worst failure would be a working machine broken by the channel: a
package built locally with machine-specific changes, overwritten or left
without the libraries it was linked against. The prototype client can't tell
a local build from Jaeger's when the versions match, so:

- **Ownership registry.** `/var/lib/d77crux-update/owned` records name,
  version-release and archive SHA-256 for every package the installer or the
  client put on the system (Mocinha writes the initial one from the medium).
  The client upgrades only packages that are registered and still at the
  registered version. Everything else is reported as `local` and never
  touched: installed by the user, rebuilt with `prt-get`/`pkgmk`, or changed
  since.
- **Holds.** Packages locked with prt-get, or listed in
  `/etc/d77crux-update.hold`, are never planned.
- **Soname check before applying.** For every library in the plan, compare
  the shared objects in the new archive with the installed ones
  (`pkginfo -l`). If a soname disappears and a `local` package needs it
  (ELF `NEEDED`), the plan stops and names both packages. It applies only
  after explicit confirmation.
- **Rollback.** Before each `pkgadd -u`, rebuild an archive of the installed
  package from its file list into `$CACHE/rollback/`.
  `d77crux-update rollback <tag>` reinstalls those archives in reverse order.
- **revdep afterwards.** Run prt-utils `revdep` and list local packages that
  need rebuilding.

VM scenarios to add: a locally rebuilt package at the same version as the
manifest (must stay untouched), a held package, a soname bump under a local
build (must stop in the plan), and a rollback after a deliberately broken
apply.

## Still to confirm

- The T480s (real install, kept without updates on purpose) as the first
  real-hardware run of the full channel.
- The full content comparison of the 263 same-version packages (only five
  were sampled).
- How the client's port and its public key reach existing installs (first
  install from the ports collection, or included in the next ISO).
- Where the extras are built: CI chroot or Daniel's CRUX machine.
