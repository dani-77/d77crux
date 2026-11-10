#!/bin/bash
# Host-side test of d77crux-cache with a fake ports tree and a stub prt-get.
# Real signify (manifest and CRUX-style .signature files) and real sha256sum.
#   bash binpkg/tests/test-d77crux-cache.sh
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
tool=$here/../d77crux-cache
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
    i=\$(awk -v n=\$n '\$1==n{print \$2}' $w/inst); printf '%s\t%s\t%s\t%s\t%s\n' \$n \$p \$version \$release \${i:-no}
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
printf 'export CFLAGS="-O2 -march=x86-64 -pipe"\nPKGMK_COMPRESSION_MODE="xz"\nPKGMK_PACKAGE_DIR=/srv/pkg\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses global package dir"   '[[ $rc != 0 ]] && grep -q "PKGMK_PACKAGE_DIR" <<<"$out"'
printf 'export CFLAGS="-O2 -march=native -pipe"\nPKGMK_COMPRESSION_MODE="xz"\n' > "$w/pkgmk.conf"
out=$(run 2>&1) && rc=0 || rc=$?
check "refuses custom CFLAGS"        '[[ $rc != 0 ]] && grep -q "CFLAGS" <<<"$out"'

exit $fail
