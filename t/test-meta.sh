#!/usr/bin/env bash
. wvtest.sh
. t/lib.sh

TOP="$(pwd)"
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

hardlink-sets()
{
    "$TOP/t/hardlink-sets" "$@"
}

# Very simple metadata tests -- create a test tree then check that bup
# meta can reproduce the metadata correctly (according to bup xstat)
# via create, extract, start-extract, and finish-extract.  The current
# tests are crude, and this does not fully test devices, varying
# users/groups, acls, attrs, etc.

genstat()
{
    (
        export PATH="$TOP:$PATH" # pick up bup
        # Skip atime (test elsewhere) to avoid the observer effect.
        find . | sort | xargs bup xstat --exclude-fields ctime,atime,size
    )
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
        WVPASS diff -U5 ../src-stat ../src-restore-stat
        # Test start/finish extract.
        force-delete src
        WVPASS bup meta --start-extract --file ../src.meta
        WVPASS test -d src
        WVPASS bup meta --finish-extract --file ../src.meta
        (cd src && genstat >../../src-restore-stat) || WVFAIL
        WVPASS diff -U5 ../src-stat ../src-restore-stat
    )
}

test-src-save-restore()
{
    # Test bup save/restore metadata for ./src -> ./src-restore.  Also
    # writes to ./src.bup.  Note that for now this just tests the
    # restore below src/, in order to avoid having to worry about
    # operations that require root (like chown /home).
    (
        #verbose:set -x
        rm -rf src.bup
        mkdir src.bup
        export BUP_DIR=$(pwd)/src.bup
        WVPASS bup init
        WVPASS bup index src
        WVPASS bup save -t -n src src
        # Test extract.
        force-delete src-restore
        mkdir src-restore
        WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
        WVPASS test -d src-restore/src
        WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/
        rm -rf src.bup
        #verbose:set +x
    )
}

universal-cleanup()
{
    if [ $(t/root-status) != root ]; then return 0; fi
    cd "$TOP"
    umount "$TOP/bupmeta.tmp/testfs" || true
    umount "$TOP/bupmeta.tmp/testfs-limited" || true
}

universal-cleanup
trap universal-cleanup EXIT

setup-test-tree()
(
    set -e
    force-delete "$BUP_DIR"
    force-delete "$TOP/bupmeta.tmp"
    mkdir -p "$TOP/bupmeta.tmp/src"
    cp -pPR Documentation cmd lib t "$TOP/bupmeta.tmp"/src

    # Add some hard links for the general tests.
    (
        cd "$TOP/bupmeta.tmp"/src
        touch hardlink-target
        ln hardlink-target hardlink-1
        ln hardlink-target hardlink-2
        ln hardlink-target hardlink-3
    )

    # Add some trivial files for the index, modify, save tests.
    (
        cd "$TOP/bupmeta.tmp"/src
        mkdir volatile
        touch volatile/{1,2,3}
    )

    # Regression test for metadata sort order.  Previously, these two
    # entries would sort in the wrong order because the metadata
    # entries were being sorted by mangled name, but the index isn't.
    dd if=/dev/zero of="$TOP/bupmeta.tmp"/src/foo bs=1k count=33
    if [[ $(uname) =~ OpenBSD ]]; then
        touch -t 201111110000 "$TOP/bupmeta.tmp"/src/foo
        touch -t 201112120000 "$TOP/bupmeta.tmp"/src/foo-bar
    else
        touch -d 2011-11-11 "$TOP/bupmeta.tmp"/src/foo
        touch -d 2011-12-12 "$TOP/bupmeta.tmp"/src/foo-bar
    fi

    t/mksock "$TOP/bupmeta.tmp/src/test-socket" || true
) || WVFAIL

# Use the test tree to check bup meta.
WVSTART 'meta --create/--extract'
(
    setup-test-tree
    cd "$TOP/bupmeta.tmp"
    test-src-create-extract

    # Test a top-level file (not dir).
    touch src-file
    WVPASS bup meta -cf src-file.meta src-file
    mkdir dest
    cd dest
    WVPASS bup meta -xf ../src-file.meta
)

# Use the test tree to check bup save/restore metadata.
WVSTART 'metadata save/restore (general)'
(
    setup-test-tree
    cd "$TOP/bupmeta.tmp"
    test-src-save-restore
)

# Test that we pull the index (not filesystem) metadata for any
# unchanged files whenever we're saving other files in a given
# directory.
WVSTART 'metadata save/restore (using index metadata)'
(
    setup-test-tree
    cd "$TOP/bupmeta.tmp"

    # ...for now -- might be a problem with hardlink restores that was
    # causing noise wrt this test.
    rm -rf src/hardlink*

    # Pause here to keep the filesystem changes far enough away from
    # the first index run that bup won't cap their index timestamps
    # (see "bup help index" for more information).  Without this
    # sleep, the compare-trees test below "Bup should *not* pick up
    # these metadata..." may fail.
    sleep 1

    #verbose:set -x
    rm -rf src.bup
    mkdir src.bup
    export BUP_DIR=$(pwd)/src.bup
    WVPASS bup init
    WVPASS bup index src
    WVPASS bup save -t -n src src

    force-delete src-restore-1
    mkdir src-restore-1
    WVPASS bup restore -C src-restore-1 "/src/latest$(pwd)/"
    WVPASS test -d src-restore-1/src
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore-1/src/

    echo "blarg" > src/volatile/1
    cp -pPR src/volatile/1 src-restore-1/src/volatile/
    #cp -a  src/volatile/1 src-restore-1/src/volatile/
    WVPASS bup index src

    # Bup should *not* pick up these metadata changes.
    touch src/volatile/2

    WVPASS bup save -t -n src src

    force-delete src-restore-2
    mkdir src-restore-2
    WVPASS bup restore -C src-restore-2 "/src/latest$(pwd)/"
    WVPASS test -d src-restore-2/src
    WVPASS "$TOP/t/compare-trees" -c src-restore-1/src/ src-restore-2/src/

    rm -rf src.bup
    #verbose:set +x
)

setup-hardlink-test()
{
    (
        cd "$TOP/bupmeta.tmp"
        rm -rf src src.bup
        mkdir src src.bup
        WVPASS bup init
    )
}

hardlink-test-run-restore()
{
    force-delete src-restore
    mkdir src-restore
    WVPASS bup restore -C src-restore "/src/latest$(pwd)/"
    WVPASS test -d src-restore/src
}

# Test hardlinks more carefully.
WVSTART 'metadata save/restore (hardlinks)'
(
    set -e
    #verbose:set -x
    export BUP_DIR="$TOP/bupmeta.tmp/src.bup"
    force-delete "$TOP/bupmeta.tmp"
    mkdir -p "$TOP/bupmeta.tmp"

    cd "$TOP/bupmeta.tmp"

    # Test trivial case - single hardlink.
    setup-hardlink-test
    (
        cd "$TOP/bupmeta.tmp"/src
        touch hardlink-target
        ln hardlink-target hardlink-1
    )
    WVPASS bup index src
    WVPASS bup save -t -n src src
    hardlink-test-run-restore
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/

    # Test the case where the hardlink hasn't changed, but the tree
    # needs to be saved again. i.e. the save-cmd.py "if hashvalid:"
    # case.
    (
        cd "$TOP/bupmeta.tmp"/src
        echo whatever > something-new
    )
    WVPASS bup index src
    WVPASS bup save -t -n src src
    hardlink-test-run-restore
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/

    # Test hardlink changes between index runs.
    #
    setup-hardlink-test
    cd "$TOP/bupmeta.tmp"/src
    touch hardlink-target-a
    touch hardlink-target-b
    ln hardlink-target-a hardlink-b-1
    ln hardlink-target-a hardlink-a-1
    cd ..
    WVPASS bup index -vv src
    rm src/hardlink-b-1
    ln src/hardlink-target-b src/hardlink-b-1
    WVPASS bup index -vv src
    WVPASS bup save -t -n src src
    hardlink-test-run-restore
    echo ./src/hardlink-a-1 > hardlink-sets.expected
    echo ./src/hardlink-target-a >> hardlink-sets.expected
    echo >> hardlink-sets.expected
    echo ./src/hardlink-b-1 >> hardlink-sets.expected
    echo ./src/hardlink-target-b >> hardlink-sets.expected
    (cd src-restore && hardlink-sets .) > hardlink-sets.restored
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test hardlink changes between index and save -- hardlink set [a
    # b c d] changes to [a b] [c d].  At least right now bup should
    # notice and recreate the latter.
    setup-hardlink-test
    cd "$TOP/bupmeta.tmp"/src
    touch a
    ln a b
    ln a c
    ln a d
    cd ..
    WVPASS bup index -vv src
    rm src/c src/d
    touch src/c
    ln src/c src/d
    WVPASS bup save -t -n src src
    hardlink-test-run-restore
    echo ./src/a > hardlink-sets.expected
    echo ./src/b >> hardlink-sets.expected
    echo >> hardlink-sets.expected
    echo ./src/c >> hardlink-sets.expected
    echo ./src/d >> hardlink-sets.expected
    (cd src-restore && hardlink-sets .) > hardlink-sets.restored
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test that we don't link outside restore tree.
    setup-hardlink-test
    cd "$TOP/bupmeta.tmp"
    mkdir src/a src/b
    touch src/a/1
    ln src/a/1 src/b/1
    WVPASS bup index -vv src
    WVPASS bup save -t -n src src
    force-delete src-restore
    mkdir src-restore
    WVPASS bup restore -C src-restore "/src/latest$(pwd)/src/a/"
    WVPASS test -e src-restore/1
    echo -n > hardlink-sets.expected
    (cd src-restore && hardlink-sets .) > hardlink-sets.restored
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test that we do link within separate sub-trees.
    setup-hardlink-test
    cd "$TOP/bupmeta.tmp"
    mkdir src/a src/b
    touch src/a/1
    ln src/a/1 src/b/1
    WVPASS bup index -vv src/a src/b
    WVPASS bup save -t -n src src/a src/b
    hardlink-test-run-restore
    echo ./src/a/1 > hardlink-sets.expected
    echo ./src/b/1 >> hardlink-sets.expected
    (cd src-restore && hardlink-sets .) > hardlink-sets.restored
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored
)

WVSTART 'meta --edit'
(
    force-delete "$TOP/bupmeta.tmp"
    mkdir "$TOP/bupmeta.tmp"
    cd "$TOP/bupmeta.tmp"
    mkdir src
    WVPASS bup meta -cf src.meta src

    WVPASS bup meta --edit --set-uid 0 src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^uid: 0'
    WVPASS bup meta --edit --set-uid 1000 src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^uid: 1000'

    WVPASS bup meta --edit --set-gid 0 src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^gid: 0'
    WVPASS bup meta --edit --set-gid 1000 src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^gid: 1000'

    WVPASS bup meta --edit --set-user foo src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^user: foo'
    WVPASS bup meta --edit --set-user bar src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^user: bar'
    WVPASS bup meta --edit --unset-user src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^user:'
    WVPASS bup meta --edit --set-user bar --unset-user src.meta \
        | WVPASS bup meta -tvvf - | WVPASS grep -qE '^user:'
    WVPASS bup meta --edit --unset-user --set-user bar src.meta \
        | WVPASS bup meta -tvvf - | WVPASS grep -qE '^user: bar'

    WVPASS bup meta --edit --set-group foo src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^group: foo'
    WVPASS bup meta --edit --set-group bar src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^group: bar'
    WVPASS bup meta --edit --unset-group src.meta | WVPASS bup meta -tvvf - \
        | WVPASS grep -qE '^group:'
    WVPASS bup meta --edit --set-group bar --unset-group src.meta \
        | WVPASS bup meta -tvvf - | WVPASS grep -qE '^group:'
    WVPASS bup meta --edit --unset-group --set-group bar src.meta \
        | WVPASS bup meta -tvvf - | grep -qE '^group: bar'
)

# Test ownership restoration (when not root or fakeroot).
(
    if [ $(t/root-status) != none ]; then
        exit 0
    fi

    WVSTART 'metadata (restoration of ownership)'
    force-delete "$TOP/bupmeta.tmp"
    mkdir "$TOP/bupmeta.tmp"
    cd "$TOP/bupmeta.tmp"
    touch src
    WVPASS bup meta -cf src.meta src

    mkdir dest
    cd dest
    # Make sure we don't change (or try to change) the user when not root.
    WVPASS bup meta --edit --set-user root ../src.meta | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qvE '^user: root'
    rm -rf src
    WVPASS bup meta --edit --unset-user --set-uid 0 ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | grep -qvE '^user: root'

    # Make sure we can restore one of the user's groups.
    last_group="$(python -c 'import os,grp; \
      print grp.getgrgid(os.getgroups()[0])[0]')"
    rm -rf src
    WVPASS bup meta --edit --set-group "$last_group" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^group: $last_group"

    # Make sure we can restore one of the user's gids.
    user_gids="$(id -G)"
    last_gid="$(echo ${user_gids/* /})"
    rm -rf src
    WVPASS bup meta --edit --unset-group --set-gid "$last_gid" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^gid: $last_gid"

    # Test --numeric-ids (gid).
    rm -rf src
    current_gidx=$(bup meta -tvvf ../src.meta | grep -e '^gid:')
    WVPASS bup meta --edit --set-group "$last_group" ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$current_gidx" "$new_gidx"

    # Test that restoring an unknown user works.
    unknown_user=$("$TOP"/t/unknown-owner --user)
    rm -rf src
    current_uidx=$(bup meta -tvvf ../src.meta | grep -e '^uid:')
    WVPASS bup meta --edit --set-user "$unknown_user" ../src.meta \
        | WVPASS bup meta -x
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$current_uidx" "$new_uidx"

    # Test that restoring an unknown group works.
    unknown_group=$("$TOP"/t/unknown-owner --group)
    rm -rf src
    current_gidx=$(bup meta -tvvf ../src.meta | grep -e '^gid:')
    WVPASS bup meta --edit --set-group "$unknown_group" ../src.meta \
        | WVPASS bup meta -x
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$current_gidx" "$new_gidx"
)

# Test ownership restoration (when root or fakeroot).
(
    if [ $(t/root-status) == none ]; then
        exit 0
    fi

    WVSTART 'metadata (restoration of ownership as root)'
    force-delete "$TOP/bupmeta.tmp"
    mkdir "$TOP/bupmeta.tmp"
    cd "$TOP/bupmeta.tmp"
    touch src
    chown 0:0 src # In case the parent dir is sgid, etc.
    WVPASS bup meta -cf src.meta src

    mkdir dest
    chmod 700 dest # so we can't accidentally do something insecure
    cd dest

    # Make sure we can restore a uid.
    WVPASS bup meta --edit --unset-user --set-uid 42 ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE '^uid: 42'

    # Make sure we can restore a gid.
    WVPASS bup meta --edit --unset-group --set-gid 42 ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE '^gid: 42'

    some_user=$("$TOP"/t/some-owner --user)
    some_group=$("$TOP"/t/some-owner --group)

    # Try to restore a user (and see that user trumps uid when uid is not 0).
    WVPASS bup meta --edit --set-uid 42 --set-user "$some_user" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^user: $some_user"

    # Try to restore a group (and see that group trumps gid when gid is not 0).
    WVPASS bup meta --edit --set-gid 42 --set-group "$some_group" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^group: $some_user"

    # Make sure a uid of 0 trumps a non-root user.
    WVPASS bup meta --edit --set-user "$some_user" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qvE "^user: $some_user"
    WVPASS bup xstat src | WVPASS grep -qE "^uid: 0"

    # Make sure a gid of 0 trumps a non-root group.
    WVPASS bup meta --edit --set-group "$some_user" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qvE "^group: $some_group"
    WVPASS bup xstat src | WVPASS grep -qE "^gid: 0"

    # Test --numeric-ids (gid).  Note the name 'root' is not handled
    # specially, so we use that here as the test group name.  We
    # assume that the root group's gid is never 42.
    rm -rf src
    WVPASS bup meta --edit --set-group root --set-gid 42 ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$new_gidx" 'gid: 42'

    # Test --numeric-ids (uid).  Note the name 'root' is not handled
    # specially, so we use that here as the test user name.  We assume
    # that the root user's uid is never 42.
    rm -rf src
    WVPASS bup meta --edit --set-user root --set-uid 42 ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$new_uidx" 'uid: 42'

    # Test that restoring an unknown user works.
    unknown_user=$("$TOP"/t/unknown-owners --user)
    rm -rf src
    WVPASS bup meta --edit --set-uid 42 --set-user "$unknown_user" ../src.meta \
        | WVPASS bup meta -x
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$new_uidx" 'uid: 42'

    # Test that restoring an unknown group works.
    unknown_group=$("$TOP"/t/unknown-owners --group)
    rm -rf src
    WVPASS bup meta --edit \
        --set-gid 42 --set-group "$unknown_group" ../src.meta \
        | WVPASS bup meta -x
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$new_gidx" 'gid: 42'
)

# Root-only tests that require an FS with all the trimmings: ACLs,
# Linux attr, Linux xattr, etc.
if [ $(t/root-status) == root ]; then
    (
        set -e
        # Some cleanup handled in universal-cleanup() above.
        # These tests are only likely to work under Linux for now
        # (patches welcome).
        [[ $(uname) =~ Linux ]] || exit 0

        WVSTART 'meta - general (as root)'
        setup-test-tree
        cd "$TOP/bupmeta.tmp"

        umount testfs || true
        dd if=/dev/zero of=testfs.img bs=1M count=32
        mke2fs -F -j -m 0 testfs.img
        mkdir testfs
        mount -o loop,acl,user_xattr testfs.img testfs
        # Hide, so that tests can't create risks.
        chown root:root testfs
        chmod 0700 testfs

        umount testfs-limited || true
        dd if=/dev/zero of=testfs-limited.img bs=1M count=32
        mkfs -t vfat testfs-limited.img
        mkdir testfs-limited
        mount -o loop,uid=root,gid=root,umask=0077 \
            testfs-limited.img testfs-limited

        #cp -a src testfs/src
        cp -pPR src testfs/src
        (cd testfs && test-src-create-extract)

        WVSTART 'meta - atime (as root)'
        force-delete testfs/src
        mkdir testfs/src
        (
            mkdir testfs/src/foo
            touch testfs/src/bar
            PYTHONPATH="$TOP/lib" \
                python -c "from bup import xstat; \
                x = xstat.timespec_to_nsecs((42, 0));\
                   xstat.utime('testfs/src/foo', (x, x));\
                   xstat.utime('testfs/src/bar', (x, x));"
            cd testfs
            WVPASS bup meta -v --create --recurse --file src.meta src
            bup meta -tvf src.meta
            # Test extract.
            force-delete src-restore
            mkdir src-restore
            cd src-restore
            WVPASS bup meta --extract --file ../src.meta
            WVPASSEQ "$(bup xstat --include-fields=atime src/foo)" "atime: 42"
            WVPASSEQ "$(bup xstat --include-fields=atime src/bar)" "atime: 42"
            # Test start/finish extract.
            force-delete src
            WVPASS bup meta --start-extract --file ../src.meta
            WVPASS test -d src
            WVPASS bup meta --finish-extract --file ../src.meta
            WVPASSEQ "$(bup xstat --include-fields=atime src/foo)" "atime: 42"
            WVPASSEQ "$(bup xstat --include-fields=atime src/bar)" "atime: 42"
        )

        WVSTART 'meta - Linux attr (as root)'
        force-delete testfs/src
        mkdir testfs/src
        (
            touch testfs/src/foo
            mkdir testfs/src/bar
            chattr +acdeijstuADST testfs/src/foo
            chattr +acdeijstuADST testfs/src/bar
            (cd testfs && test-src-create-extract)
            # Test restoration to a limited filesystem (vfat).
            (
                WVPASS bup meta --create --recurse --file testfs/src.meta \
                    testfs/src
                force-delete testfs-limited/src-restore
                mkdir testfs-limited/src-restore
                cd testfs-limited/src-restore
                WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                    | WVPASS grep -e '^Linux chattr:' \
                    | WVPASS python -c \
                      'import sys; exit(not len(sys.stdin.readlines()) == 2)'
            )
        )

        WVSTART 'meta - Linux xattr (as root)'
        force-delete testfs/src
        mkdir testfs/src
        (
            touch testfs/src/foo
            mkdir testfs/src/bar
            attr -s foo -V bar testfs/src/foo
            attr -s foo -V bar testfs/src/bar
            (cd testfs && test-src-create-extract)

            # Test restoration to a limited filesystem (vfat).
            (
                WVPASS bup meta --create --recurse --file testfs/src.meta \
                    testfs/src
                force-delete testfs-limited/src-restore
                mkdir testfs-limited/src-restore
                cd testfs-limited/src-restore
                WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                    | WVPASS grep -e '^xattr\.set:' \
                    | WVPASS python -c \
                      'import sys; exit(not len(sys.stdin.readlines()) == 2)'
            )
        )

        WVSTART 'meta - POSIX.1e ACLs (as root)'
        force-delete testfs/src
        mkdir testfs/src
        (
            touch testfs/src/foo
            mkdir testfs/src/bar
            setfacl -m u:root:r testfs/src/foo
            setfacl -m u:root:r testfs/src/bar
            (cd testfs && test-src-create-extract)

            # Test restoration to a limited filesystem (vfat).
            (
                WVPASS bup meta --create --recurse --file testfs/src.meta \
                    testfs/src
                force-delete testfs-limited/src-restore
                mkdir testfs-limited/src-restore
                cd testfs-limited/src-restore
                WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                    | WVPASS grep -e '^POSIX1e ACL applyto:' \
                    | WVPASS python -c \
                      'import sys; exit(not len(sys.stdin.readlines()) == 2)'
            )
        )
    )
fi

exit 0
