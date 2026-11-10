#!/bin/bash
# Host-side test of d77crux-cache with a fake ports tree and a stub prt-get.
# Real signify (manifest and CRUX-style .signature files) and real sha256sum.
#   bash binpkg/tests/test-d77crux-cache.sh
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
tool=$here/../../d77crux-cache/d77crux-cache
w=$(mktemp -d); trap 'rm -rf "$w"' EXIT
fail=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fail=1; fi; }

mkdir -p "$w"/{bin,keys,state,rel/T,ports/core/foo,ports/core/bar,ports/opt/baz,ports/local/qux}
signify -G -n -p "$w/keys/rel.pub" -s "$w/keys/rel.sec"
for c in core opt; do signify -G -n -p "$w/keys/$c.pub" -s "$w/keys/$c.sec"; done

# Ports: Pkgfile + .signature in CRUX's format (signify -e over SHA256 tags).
port() {  # port COLL NAME VERSION RELEASE
    local d=$w/ports/$1/$2
    printf 'name=%s\nversion=%s\nrelease=%s\n' "$2" "$3" "$4" > "$d/Pkgfile"
    [[ -f $w/keys/$1.sec ]] || return 0
    (cd "$d" && sha256sum --tag Pkgfile > .sha && signify -S -e -s "$w/keys/$1.sec" -m .sha -x .signature && rm .sha)
}
port core foo 2 1; port core bar 3 1; port opt baz 5 1; port local qux 1 1
echo '# local change' >> "$w/ports/opt/baz/Pkgfile"      # edited after signing

# Release: archives for foo 2-1, bar 2-1, baz 5-1, qux 1-1.
mk() { printf 'archive %s\n' "$1" > "$w/rel/T/$1-$2-$3.pkg.tar.xz"; }
mk foo 2 1; mk bar 2 1; mk baz 5 1; mk qux 1 1
{
    printf 'format\td77crux-binpkg 1\ntag\tT\n'
    for e in "foo 2 1 core" "bar 2 1 core" "baz 5 1 opt" "qux 1 1 core"; do
        set -- $e; a=$1-$2-$3.pkg.tar.xz
        printf 'pkg\t%s\t%s\t%s\t%s\tcrux.ninja-iso\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$a" \
            "$1#$2-$3.pkg.tar.xz" "$(stat -c %s "$w/rel/T/$a")" "$(sha256sum "$w/rel/T/$a" | cut -d' ' -f1)"
    done
} > "$w/rel/T/manifest.txt"
signify -S -s "$w/keys/rel.sec" -m "$w/rel/T/manifest.txt" -x "$w/rel/T/manifest.txt.sig"

# Stub prt-get: "printf '%n\t%p\t%v\t%r\t%i\n'" from $w/inst (name status).
cat > "$w/bin/prt-get" <<EOF
#!/bin/bash
for d in $w/ports/*/*; do
    n=\${d##*/}; p=\${d%/*}; . \$d/Pkgfile
    i=\$(awk -v n=\$n '\$1==n{print \$2}' $w/inst); l=\$(awk -v n=\$n '\$1==n{print \$3}' $w/inst)
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \$n \$p \$version \$release \${i:-no} \${l:-no}
done
EOF
chmod +x "$w/bin/prt-get"
printf 'foo diff\nbar diff\nbaz diff\nqux diff\n' > "$w/inst"

printf 'BASE_URL=file://%s/rel\nTAG=T\nPUBKEY=%s/keys/rel.pub\n' "$w" "$w" > "$w/conf"
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\n' > "$w/pkgmk.conf"
run() { PATH=$w/bin:$PATH PORTS=$w/ports PKGMK_CONF=$w/pkgmk.conf PORTS_KEYS=$w/keys STATE_DIR=$w/state \
        D77CRUX_CACHE_TEST=1 bash "$tool" -c "$w/conf" "$@"; }

out=$(run 2>&1) || true
check "foo cached"                   '[[ -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]] && grep -q "^cached .*foo" <<<"$out"'
check "bar skipped: version differs" 'grep -q "^skip-version .*bar" <<<"$out" && ! ls $w/ports/core/bar/*.pkg.tar.* 2>/dev/null'
check "baz skipped: Pkgfile edited"  'grep -q "^skip-modified .*baz" <<<"$out" && ! ls $w/ports/opt/baz/*.pkg.tar.* 2>/dev/null'
check "qux skipped: not official"    'grep -q "^skip-collection .*qux" <<<"$out"'

out=$(run 2>&1) || true
check "second run keeps foo"         '[[ -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]] && grep -q "^present .*foo" <<<"$out"'

printf 'foo yes\n' > "$w/inst"
out=$(run 2>&1) || true
check "installed foo: archive removed" '[[ ! -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]] && grep -q "^removed" <<<"$out"'

printf 'foo diff\n' > "$w/inst"
mk foo 2 1; echo tampered >> "$w/rel/T/foo-2-1.pkg.tar.xz"
out=$(run 2>&1) || true
check "altered archive refused"      '[[ ! -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]] && grep -q "^failed .*foo" <<<"$out"'

printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses gz compression"       '[[ $rc != 0 ]] && grep -q "PKGMK_COMPRESSION_MODE" <<<"$out"'
# --- prt-get locks ----------------------------------------------------------
mk foo 2 1
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\n' > "$w/pkgmk.conf"
printf 'foo diff yes\n' > "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "locked: no archive, binary reported" '[[ $rc == 0 && ! -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]] && grep -q "^locked .*foo .*binary available" <<<"$out" && grep -q "prt-get unlock foo" <<<"$out"'
printf 'bar diff yes\n' > "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "locked, no matching binary: no hint" 'grep -q "^skip-version .*bar" <<<"$out" && ! grep -q "Locked ports" <<<"$out"'

# --- global PKGMK_PACKAGE_DIR ----------------------------------------------
mk foo 2 1   # untampered again
mkdir -p "$w/pkgdir"
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\nPKGMK_PACKAGE_DIR=%s/pkgdir\n' "$w" > "$w/pkgmk.conf"
printf 'foo diff\nbar diff\nbaz diff\nqux diff\n' > "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "global dir: archive placed there"  '[[ $rc == 0 && -f $w/pkgdir/foo#2-1.pkg.tar.xz && ! -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]]'
echo "my own build" > "$w/pkgdir/qux#1-1.pkg.tar.xz"; printf 'qux diff\n' >> "$w/inst"
mkdir -p "$w/ports/core/quux"; port core quux 1 1; mk quux 1 1
printf 'pkg\tquux\t1\t1\tcore\tcrux.ninja-iso\tquux-1-1.pkg.tar.xz\tquux#1-1.pkg.tar.xz\t%s\t%s\n' \
    "$(stat -c %s "$w/rel/T/quux-1-1.pkg.tar.xz")" "$(sha256sum "$w/rel/T/quux-1-1.pkg.tar.xz" | cut -d' ' -f1)" >> "$w/rel/T/manifest.txt"
rm -f "$w/rel/T/manifest.txt.sig"; signify -S -s "$w/keys/rel.sec" -m "$w/rel/T/manifest.txt" -x "$w/rel/T/manifest.txt.sig"
echo "my own quux build" > "$w/pkgdir/quux#1-1.pkg.tar.xz"; printf 'quux diff\n' >> "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "global dir: foreign archive kept"  'grep -q "^skip-foreign .*quux" <<<"$out" && grep -qx "my own quux build" "$w/pkgdir/quux#1-1.pkg.tar.xz"'
printf 'foo yes\n' > "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "global dir: only own archives removed" '[[ ! -f $w/pkgdir/foo#2-1.pkg.tar.xz ]] && [[ -f $w/pkgdir/quux#1-1.pkg.tar.xz && -f $w/pkgdir/qux#1-1.pkg.tar.xz ]]'
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\nPKGMK_PACKAGE_DIR="$PWD/out"\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses a port-relative package dir" '[[ $rc != 0 ]] && grep -q "depends on the port directory" <<<"$out"'
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\nPKGMK_PACKAGE_DIR=/nonexistent/pkg\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses a missing package dir"     '[[ $rc != 0 ]] && grep -q "not an existing absolute directory" <<<"$out"'
printf 'export CFLAGS="-O2 -march=native -pipe"\nPKGMK_COMPRESSION_MODE="xz"\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses custom CFLAGS"        '[[ $rc != 0 ]] && grep -q "CFLAGS" <<<"$out"'
echo 'ACCEPT_GENERIC=yes' >> "$w/conf"
printf 'foo diff\n' > "$w/inst"
out=$(run 2>&1) && rc=0 || rc=$?
check "ACCEPT_GENERIC=yes allows custom CFLAGS" '[[ $rc == 0 ]] && grep -q "ACCEPT_GENERIC=yes: placing generic" <<<"$out" && [[ -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]]'
sed -i '/^ACCEPT_GENERIC=/d' "$w/conf"

# --- channel pointer -----------------------------------------------------
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\n' > "$w/pkgmk.conf"
mk foo 2 1   # restore the untampered archive the manifest describes
printf 'foo diff\n' > "$w/inst"   # earlier cases marked foo installed
chan() {  # chan PUBLISHED [MANIFEST_SHA]
    mkdir -p "$w/rel/C"
    printf 'format\td77crux-binpkg-channel 1\nseries\t3.8\narch\tx86_64\ntag\tT\nmanifest_sha256\t%s\npublished\t%s\n' \
        "${2:-$(sha256sum "$w/rel/T/manifest.txt" | cut -d' ' -f1)}" "$1" > "$w/rel/C/channel.txt"
    rm -f "$w/rel/C/channel.txt.sig"; signify -S -s "$w/keys/rel.sec" -m "$w/rel/C/channel.txt" -x "$w/rel/C/channel.txt.sig"
}
printf 'BASE_URL=file://%s/rel\nCHANNEL_TAG=C\nPUBKEY=%s/keys/rel.pub\n' "$w" "$w" > "$w/conf"
rm -f "$w/state/channel-published"
chan 2026-11-10T08:00:00Z
out=$(run 2>&1) && rc=0 || rc=$?
check "channel: follows the named snapshot" '[[ $rc == 0 ]] && [[ -f $w/ports/core/foo/foo#2-1.pkg.tar.xz ]]'
chan 2026-11-09T08:00:00Z
out=$(run 2>&1) && rc=0 || rc=$?
check "channel: older pointer refused"      '[[ $rc != 0 ]] && grep -q "older than" <<<"$out"'
chan 2026-11-11T08:00:00Z 0000000000000000000000000000000000000000000000000000000000000000
out=$(run 2>&1) && rc=0 || rc=$?
check "channel: manifest mismatch refused"  '[[ $rc != 0 ]] && grep -q "does not match the channel" <<<"$out"'
echo tamper >> "$w/rel/C/channel.txt"
out=$(run 2>&1) && rc=0 || rc=$?
check "channel: bad signature refused"      '[[ $rc != 0 ]] && grep -q "channel signature" <<<"$out"'

exit $fail
