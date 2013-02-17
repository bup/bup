#!/usr/bin/env bash
. ./wvtest-bup.sh
. ./t/lib.sh

set -ex -o pipefail

if ! actually-root; then
    echo 'Not root: skipping --check-device tests.'
    exit 0 # FIXME: add WVSKIP.
fi

if test -z "$(type -p losetup)"; then
    echo 'Unable to find losetup: skipping --check-device tests.'
    exit 0 # FIXME: add WVSKIP.
fi

if test -z "$(type -p mke2fs)"; then
    echo 'Unable to find mke2fs: skipping --check-device tests.'
    exit 0 # FIXME: add WVSKIP.
fi

WVSTART '--check-device'

top="$(pwd)"
tmpdir="$(wvmktempdir)"
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

srcmnt="$(wvmkmountpt)"
tmpmnt1="$(wvmkmountpt)"
tmpmnt2="$(wvmkmountpt)"

cd "$tmpdir"

dd if=/dev/zero of=testfs.img bs=1M count=32
mke2fs -F -j -m 0 testfs.img
mount -o loop testfs.img "$tmpmnt1"
# Hide, so that tests can't create risks.
chown root:root "$tmpmnt1"
chmod 0700 "$tmpmnt1"

# Create trivial content.
date > "$tmpmnt1/foo"
umount "$tmpmnt1"

# Mount twice, so we'll have the same content with different devices.
mount -oro,loop testfs.img "$tmpmnt1"
mount -oro,loop testfs.img "$tmpmnt2"

# Test default behavior: --check-device.
mount -oro --bind "$tmpmnt1" "$srcmnt"
bup init
bup index --fake-valid "$srcmnt"
umount "$srcmnt"
mount -oro --bind "$tmpmnt2" "$srcmnt"
bup index "$srcmnt"
WVPASSEQ "$(bup index --status "$srcmnt")" \
"M $srcmnt/lost+found/
M $srcmnt/foo
M $srcmnt/"
umount "$srcmnt"

WVSTART '--no-check-device'
mount -oro --bind "$tmpmnt1" "$srcmnt"
bup index --clear
bup index --fake-valid "$srcmnt"
umount "$srcmnt"
mount -oro --bind "$tmpmnt2" "$srcmnt"
bup index --no-check-device "$srcmnt"
bup index --status "$srcmnt"
WVPASSEQ "$(bup index --status "$srcmnt")" \
"  $srcmnt/lost+found/
  $srcmnt/foo
  $srcmnt/"

umount "$srcmnt"
umount "$tmpmnt1"
umount "$tmpmnt2"
rm -r "$tmpmnt1" "$tmpmnt2" "$tmpdir"
