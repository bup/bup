#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. ./dev/lib.sh || exit $?

set -o pipefail

root_status="$(dev/root-status)" || exit $?

if [ "$root_status" != root ]; then
    echo 'Not root: skipping --check-device tests.'
    exit 0 # FIXME: add WVSKIP.
fi

if test -n "$(type -p modprobe)" && ! modprobe loop; then
    echo 'Unable to load loopback module; skipping --check-device test.' 1>&2
    exit 0
fi

if test -z "$(type -p losetup)"; then
    echo 'Unable to find losetup: skipping --check-device tests.' 1>&2
    exit 0 # FIXME: add WVSKIP.
fi

if test -z "$(type -p mke2fs)"; then
    echo 'Unable to find mke2fs: skipping --check-device tests.' 1>&2
    exit 0 # FIXME: add WVSKIP.
fi

WVSTART '--check-device'

top="$(pwd)"
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

srcmnt="$(WVPASS wvmkmountpt)" || exit $?
tmpmnt1="$(WVPASS wvmkmountpt)" || exit $?
tmpmnt2="$(WVPASS wvmkmountpt)" || exit $?

WVPASS cd "$tmpdir"

WVPASS dd if=/dev/zero of=testfs.img bs=1M count=32
WVPASS mke2fs -F -j -m 0 testfs.img
WVPASS mount -o loop testfs.img "$tmpmnt1"
# Hide, so that tests can't create risks.
WVPASS chown root:root "$tmpmnt1"
WVPASS chmod 0700 "$tmpmnt1"

# Create trivial content.
WVPASS date > "$tmpmnt1/foo"
WVPASS umount "$tmpmnt1"

# Mount twice, so we'll have the same content with different devices.
WVPASS cp -pP testfs.img testfs2.img
WVPASS mount -oro,loop testfs.img "$tmpmnt1"
WVPASS mount -oro,loop testfs2.img "$tmpmnt2"

# Test default behavior: --check-device.
WVPASS mount -oro --bind "$tmpmnt1" "$srcmnt"
WVPASS bup init
WVPASS bup index --fake-valid "$srcmnt"
WVPASS umount "$srcmnt"
WVPASS mount -oro --bind "$tmpmnt2" "$srcmnt"
WVPASS bup index "$srcmnt"
WVPASSEQ "$(bup index --status "$srcmnt")" \
"M $srcmnt/lost+found/
M $srcmnt/foo
M $srcmnt/"
WVPASS umount "$srcmnt"

WVSTART '--no-check-device'
WVPASS mount -oro --bind "$tmpmnt1" "$srcmnt"
WVPASS bup index --clear
WVPASS bup index --fake-valid "$srcmnt"
WVPASS umount "$srcmnt"
WVPASS mount -oro --bind "$tmpmnt2" "$srcmnt"
WVPASS bup index --no-check-device "$srcmnt"
WVPASS bup index --status "$srcmnt"
WVPASSEQ "$(bup index --status "$srcmnt")" \
"  $srcmnt/lost+found/
  $srcmnt/foo
  $srcmnt/"

WVPASS umount "$srcmnt"
WVPASS umount "$tmpmnt1"
WVPASS umount "$tmpmnt2"
WVPASS rm -r "$tmpmnt1" "$tmpmnt2" "$tmpdir"
