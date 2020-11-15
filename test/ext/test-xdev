#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?

set -o pipefail

root_status="$(dev/root-status)" || exit $?

if [ "$root_status" != root ]; then
    WVSTART 'not root: skipping tests'
    exit 0 # FIXME: add WVSKIP.
fi

if ! modprobe loop; then
    WVSTART 'unable to load loopback module; skipping tests' 1>&2
    exit 0
fi

# These tests are only likely to work under Linux for now
# (patches welcome).
if ! [[ $(uname) =~ Linux ]]; then
    WVSTART 'not Linux: skipping tests'
    exit 0 # FIXME: add WVSKIP.
fi

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS pushd "$tmpdir"

WVSTART 'drecurse'

WVPASS dd if=/dev/zero of=testfs-1.img bs=1M count=32
WVPASS dd if=/dev/zero of=testfs-2.img bs=1M count=32
WVPASS mkfs -F testfs-1.img # Don't care what type (though must have symlinks)
WVPASS mkfs -F testfs-2.img # Don't care what type (though must have symlinks)
WVPASS mkdir -p src/mnt-1/hidden-1 src/mnt-2/hidden-2
WVPASS mount -o loop testfs-1.img src/mnt-1
WVPASS mount -o loop testfs-2.img src/mnt-2

WVPASS touch src/1

WVPASS mkdir -p src/mnt-1/x
WVPASS touch src/mnt-1/2 src/mnt-1/x/3

WVPASS touch src/mnt-2/4

(WVPASS cd src && WVPASS ln -s mnt-2 mnt-link)
(WVPASS cd src && WVPASS ln -s . top)

WVPASSEQ "$(bup drecurse src | grep -vF lost+found)" "src/top
src/mnt-link
src/mnt-2/4
src/mnt-2/
src/mnt-1/x/3
src/mnt-1/x/
src/mnt-1/2
src/mnt-1/
src/1
src/"

WVPASSEQ "$(bup drecurse -x src)" "src/top
src/mnt-link
src/mnt-2/
src/mnt-1/
src/1
src/"

WVSTART 'index/save/restore'

WVPASS bup index src
WVPASS bup save -n src src
WVPASS mkdir src-restore
WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
WVPASS test -d src-restore/src
WVPASS "$top/dev/compare-trees" -c src/ src-restore/src/

# Test -x when none of the mount points are explicitly indexed
WVPASS rm -r "$BUP_DIR" src-restore
WVPASS bup init
WVPASS bup index -x src
WVPASS bup save -n src src
WVPASS mkdir src-restore
WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
WVPASS test -d src-restore/src
WVPASSEQ "$(cd src-restore/src && find . -not -name lost+found | LC_ALL=C sort)" \
".
./1
./mnt-1
./mnt-2
./mnt-link
./top"

# Test -x when a mount point is explicitly indexed.  This should
# include the mount.
WVPASS rm -r "$BUP_DIR" src-restore
WVPASS bup init
WVPASS bup index -x src src/mnt-2
WVPASS bup save -n src src
WVPASS mkdir src-restore
WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
WVPASS test -d src-restore/src
WVPASSEQ "$(cd src-restore/src && find . -not -name lost+found | LC_ALL=C sort)" \
".
./1
./mnt-1
./mnt-2
./mnt-2/4
./mnt-link
./top"

# Test -x when a direct link to a mount point is explicitly indexed.
# This should *not* include the mount.
WVPASS rm -r "$BUP_DIR" src-restore
WVPASS bup init
WVPASS bup index -x src src/mnt-link
WVPASS bup save -n src src
WVPASS mkdir src-restore
WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
WVPASS test -d src-restore/src
WVPASSEQ "$(cd src-restore/src && find . -not -name lost+found | LC_ALL=C sort)" \
".
./1
./mnt-1
./mnt-2
./mnt-link
./top"

# Test -x when a path that resolves to a mount point is explicitly
# indexed (i.e. dir symlnks that redirect the leaf to a mount point).
# This should include the mount.
WVPASS rm -r "$BUP_DIR" src-restore
WVPASS bup init
WVPASS bup index -x src src/top/top/mnt-2
WVPASS bup save -n src src
WVPASS mkdir src-restore
WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
WVPASS test -d src-restore/src
WVPASSEQ "$(cd src-restore/src && find . -not -name lost+found | LC_ALL=C sort)" \
".
./1
./mnt-1
./mnt-2
./mnt-2/4
./mnt-link
./top"

WVPASS cd "$top"
WVPASS umount "$tmpdir/src/mnt-1"
WVPASS umount "$tmpdir/src/mnt-2"
WVPASS rm -r "$tmpdir"
