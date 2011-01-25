#!/usr/bin/env bash
. wvtest.sh
set -e -o pipefail

TOP="$(pwd)"
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

# Very simple metadata tests -- "make install" to a temp directory,
# then check that bup meta can reproduce the metadata correctly
# (according to coreutils stat) via create, extract, start-extract,
# and finish-extract.  The current tests are crude, and this does not
# test devices, varying users/groups, acls, attrs, etc.
WVSTART "meta"

genstat()
{
  (
    export PATH="${TOP}:${PATH}" # pick up bup
    # Skip atime (test elsewhere) to avoid the observer effect.
    find . | sort | xargs bup xstat --exclude-fields ctime,atime
  )
}

force-delete()
{
  if test "$(whoami)" != root
  then
    rm -rf "$@"
  else
    # Go to greater lengths to deal with any test detritus.
    for f in "$@"
    do
      test -e "$@" || continue
      chattr -fR = "$@" || true
      setfacl -Rb "$@"
      rm -r "$@"
    done
  fi
}

test-src-create-extract()
{
  # Test bup meta create/extract for ./src -> ./src-restore.
  # Also writes to ./src-stat and ./src-restore-stat.
  (
    (cd src && WVPASS genstat) > src-stat
    WVPASS bup meta --create --recurse --file src.meta src
    # Test extract.
    force-delete src-restore
    mkdir src-restore
    cd src-restore
    WVPASS bup meta --extract --file ../src.meta
    WVPASS test -d src
    (cd src && genstat >../../src-restore-stat) || WVFAIL
    WVPASS diff -u5 ../src-stat ../src-restore-stat
    # Test start/finish extract.
    force-delete src
    WVPASS bup meta --start-extract --file ../src.meta
    WVPASS test -d src
    WVPASS bup meta --finish-extract --file ../src.meta
    (cd src && genstat >../../src-restore-stat) || WVFAIL
    WVPASS diff -u5 ../src-stat ../src-restore-stat
  )
}

if test "$(whoami)" == root
then
  umount "${TOP}/bupmeta.tmp/testfs" || true
fi

force-delete "${BUP_DIR}"
force-delete "${TOP}/bupmeta.tmp"

# Create a test tree.
(
  mkdir -p "${TOP}/bupmeta.tmp"
  make DESTDIR="${TOP}/bupmeta.tmp/src" install
  mkdir "${TOP}/bupmeta.tmp/src/misc"
  cp -a cmd/bup-* "${TOP}/bupmeta.tmp/src/misc/"
) || WVFAIL

# Use the test tree to check bup meta.
(
  cd "${TOP}/bupmeta.tmp"
  test-src-create-extract
)

# Root-only tests: ACLs, Linux attr, Linux xattr, etc.
if test "$(whoami)" == root
then
  (
    cleanup_at_exit()
    {
      cd "${TOP}"
      umount "${TOP}/bupmeta.tmp/testfs" || true
    }

    trap cleanup_at_exit EXIT

    WVPASS cd "${TOP}/bupmeta.tmp"
    umount testfs || true
    dd if=/dev/zero of=test-fs.img bs=1M count=32
    mke2fs -F -j -m 0 test-fs.img
    mkdir testfs
    mount -o loop,acl,user_xattr test-fs.img testfs
    # Hide, so that tests can't create risks.
    chown root:root testfs
    chmod 0700 testfs

    cp -a src testfs/src
    (cd testfs && test-src-create-extract)

    # Test Linux attr.
    force-delete testfs/src
    mkdir testfs/src
    (
      touch testfs/src/foo
      mkdir testfs/src/bar
      chattr +acdeijstuADST testfs/src/foo
      chattr +acdeijstuADST testfs/src/bar
      (cd testfs && test-src-create-extract)
    )

    # Test Linux xattr.
    force-delete testfs/src
    mkdir testfs/src
    (
      touch testfs/src/foo
      mkdir testfs/src/bar
      attr -s foo -V bar testfs/src/foo
      attr -s foo -V bar testfs/src/bar
      (cd testfs && test-src-create-extract)
    )
  )
fi

force-delete "${BUP_DIR}"
force-delete "$TOP/bupmeta.tmp"

exit 0
