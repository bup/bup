#!/usr/bin/env bash
. wvtest.sh
. t/lib.sh

set -o pipefail

TOP="$(WVPASS pwd)" || exit $?
export BUP_DIR="$TOP/buptest.tmp"

bup()
{
    "$TOP/bup" "$@"
}

hardlink-sets()
{
    "$TOP/t/hardlink-sets" "$@"
}

id-other-than()
{
    "$TOP/t/id-other-than" "$@"
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
        WVPASS find . | WVPASS sort \
            | WVPASS xargs bup xstat --exclude-fields ctime,atime,size
    )
}

test-src-create-extract()
{
    # Test bup meta create/extract for ./src -> ./src-restore.
    # Also writes to ./src-stat and ./src-restore-stat.
    (
        (WVPASS cd src; WVPASS genstat) > src-stat || exit $?
        WVPASS bup meta --create --recurse --file src.meta src
        # Test extract.
        WVPASS force-delete src-restore
        WVPASS mkdir src-restore
        WVPASS cd src-restore
        WVPASS bup meta --extract --file ../src.meta
        WVPASS test -d src
        (WVPASS cd src; WVPASS genstat >../../src-restore-stat) || exit $?
        WVPASS diff -U5 ../src-stat ../src-restore-stat
        # Test start/finish extract.
        WVPASS force-delete src
        WVPASS bup meta --start-extract --file ../src.meta
        WVPASS test -d src
        WVPASS bup meta --finish-extract --file ../src.meta
        (WVPASS cd src; WVPASS genstat >../../src-restore-stat) || exit $?
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
        WVPASS rm -rf src.bup
        WVPASS mkdir src.bup
        export BUP_DIR=$(pwd)/src.bup
        WVPASS bup init
        WVPASS bup index src
        WVPASS bup save -t -n src src
        # Test extract.
        WVPASS force-delete src-restore
        WVPASS mkdir src-restore
        WVPASS bup restore -C src-restore "/src/latest$(pwd -P)/"
        WVPASS test -d src-restore/src
        WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/
        WVPASS rm -rf src.bup
    )
}

universal-cleanup()
{
    if [ $(t/root-status) != root ]; then return 0; fi
    umount "$TOP/bupmeta.tmp/testfs" || true
    umount "$TOP/bupmeta.tmp/testfs-limited" || true
}

WVPASS universal-cleanup
trap universal-cleanup EXIT

setup-test-tree()
{
    WVPASS force-delete "$BUP_DIR"
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir -p "$TOP/bupmeta.tmp/src"
    WVPASS cp -pPR Documentation cmd lib t "$TOP/bupmeta.tmp"/src

    # Add some hard links for the general tests.
    (
        WVPASS cd "$TOP/bupmeta.tmp"/src
        WVPASS touch hardlink-target
        WVPASS ln hardlink-target hardlink-1
        WVPASS ln hardlink-target hardlink-2
        WVPASS ln hardlink-target hardlink-3
    ) || exit $?

    # Add some trivial files for the index, modify, save tests.
    (
        WVPASS cd "$TOP/bupmeta.tmp"/src
        WVPASS mkdir volatile
        WVPASS touch volatile/{1,2,3}
    ) || exit $?

    # Regression test for metadata sort order.  Previously, these two
    # entries would sort in the wrong order because the metadata
    # entries were being sorted by mangled name, but the index isn't.
    WVPASS dd if=/dev/zero of="$TOP/bupmeta.tmp"/src/foo bs=1k count=33
    WVPASS touch -t 201111111111 "$TOP/bupmeta.tmp"/src/foo
    WVPASS touch -t 201112121111 "$TOP/bupmeta.tmp"/src/foo-bar

    t/mksock "$TOP/bupmeta.tmp/src/test-socket" || true
}

# Use the test tree to check bup meta.
WVSTART 'meta --create/--extract'
(
    WVPASS setup-test-tree
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS test-src-create-extract

    # Test a top-level file (not dir).
    WVPASS touch src-file
    WVPASS bup meta -cf src-file.meta src-file
    WVPASS mkdir dest
    WVPASS cd dest
    WVPASS bup meta -xf ../src-file.meta
) || exit $?

# Use the test tree to check bup save/restore metadata.
WVSTART 'metadata save/restore (general)'
(
    WVPASS setup-test-tree
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS test-src-save-restore

    # Test a deeper subdir/ to make sure top-level non-dir metadata is
    # restored correctly.  We need at least one dir and one non-dir at
    # the "top-level".
    WVPASS test -f src/lib/__init__.py
    WVPASS test -d src/lib/bup
    WVPASS rm -rf src.bup
    WVPASS mkdir src.bup
    export BUP_DIR=$(pwd)/src.bup
    WVPASS bup init
    WVPASS touch -t 201111111111 src-restore # Make sure the top won't match.
    WVPASS bup index src
    WVPASS bup save -t -n src src
    WVPASS force-delete src-restore
    WVPASS bup restore -C src-restore "/src/latest$(pwd -P)/src/lib/"
    WVPASS touch -t 201211111111 src-restore # Make sure the top won't match.
    # Check that the only difference is the top dir.
    WVFAIL $TOP/t/compare-trees -c src/lib/ src-restore/ > tmp-compare-trees
    WVPASSEQ $(cat tmp-compare-trees | wc -l) 2
    WVPASS tail -n +2 tmp-compare-trees | WVPASS grep -qE '^\.d[^ ]+ \./$'
) || exit $?

# Test that we pull the index (not filesystem) metadata for any
# unchanged files whenever we're saving other files in a given
# directory.
WVSTART 'metadata save/restore (using index metadata)'
(
    WVPASS setup-test-tree
    WVPASS cd "$TOP/bupmeta.tmp"

    # ...for now -- might be a problem with hardlink restores that was
    # causing noise wrt this test.
    WVPASS rm -rf src/hardlink*

    # Pause here to keep the filesystem changes far enough away from
    # the first index run that bup won't cap their index timestamps
    # (see "bup help index" for more information).  Without this
    # sleep, the compare-trees test below "Bup should *not* pick up
    # these metadata..." may fail.
    WVPASS sleep 1

    WVPASS rm -rf src.bup
    WVPASS mkdir src.bup
    export BUP_DIR=$(pwd)/src.bup
    WVPASS bup init
    WVPASS bup index src
    WVPASS bup save -t -n src src

    WVPASS force-delete src-restore-1
    WVPASS mkdir src-restore-1
    WVPASS bup restore -C src-restore-1 "/src/latest$(pwd -P)/"
    WVPASS test -d src-restore-1/src
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore-1/src/

    WVPASS echo "blarg" > src/volatile/1
    WVPASS cp -a src/volatile/1 src-restore-1/src/volatile/
    WVPASS bup index src

    # Bup should *not* pick up these metadata changes.
    WVPASS touch src/volatile/2

    WVPASS bup save -t -n src src

    WVPASS force-delete src-restore-2
    WVPASS mkdir src-restore-2
    WVPASS bup restore -C src-restore-2 "/src/latest$(pwd -P)/"
    WVPASS test -d src-restore-2/src
    WVPASS "$TOP/t/compare-trees" -c src-restore-1/src/ src-restore-2/src/

    WVPASS rm -rf src.bup
) || exit $?

setup-hardlink-test()
{
    WVPASS rm -rf "$TOP/bupmeta.tmp"/src "$TOP/bupmeta.tmp"/src.bup
    WVPASS mkdir "$TOP/bupmeta.tmp"/src "$TOP/bupmeta.tmp"/src.bup
    WVPASS bup init
}

hardlink-test-run-restore()
{
    WVPASS force-delete src-restore
    WVPASS mkdir src-restore
    WVPASS bup restore -C src-restore "/src/latest$(pwd -P)/"
    WVPASS test -d src-restore/src
}

# Test hardlinks more carefully.
WVSTART 'metadata save/restore (hardlinks)'
(
    export BUP_DIR="$TOP/bupmeta.tmp/src.bup"
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir -p "$TOP/bupmeta.tmp"

    WVPASS cd "$TOP/bupmeta.tmp"

    # Test trivial case - single hardlink.
    WVPASS setup-hardlink-test
    (
        WVPASS cd "$TOP/bupmeta.tmp"/src
        WVPASS touch hardlink-target
        WVPASS ln hardlink-target hardlink-1
    ) || exit $?
    WVPASS bup index src
    WVPASS bup save -t -n src src
    WVPASS hardlink-test-run-restore
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/

    # Test the case where the hardlink hasn't changed, but the tree
    # needs to be saved again. i.e. the save-cmd.py "if hashvalid:"
    # case.
    (
        WVPASS cd "$TOP/bupmeta.tmp"/src
        WVPASS echo whatever > something-new
    ) || exit $?
    WVPASS bup index src
    WVPASS bup save -t -n src src
    WVPASS hardlink-test-run-restore
    WVPASS "$TOP/t/compare-trees" -c src/ src-restore/src/

    # Test hardlink changes between index runs.
    #
    WVPASS setup-hardlink-test
    WVPASS cd "$TOP/bupmeta.tmp"/src
    WVPASS touch hardlink-target-a
    WVPASS touch hardlink-target-b
    WVPASS ln hardlink-target-a hardlink-b-1
    WVPASS ln hardlink-target-a hardlink-a-1
    WVPASS cd ..
    WVPASS bup index -vv src
    WVPASS rm src/hardlink-b-1
    WVPASS ln src/hardlink-target-b src/hardlink-b-1
    WVPASS bup index -vv src
    WVPASS bup save -t -n src src
    WVPASS hardlink-test-run-restore
    WVPASS echo ./src/hardlink-a-1 > hardlink-sets.expected
    WVPASS echo ./src/hardlink-target-a >> hardlink-sets.expected
    WVPASS echo >> hardlink-sets.expected
    WVPASS echo ./src/hardlink-b-1 >> hardlink-sets.expected
    WVPASS echo ./src/hardlink-target-b >> hardlink-sets.expected
    (WVPASS cd src-restore; WVPASS hardlink-sets .) > hardlink-sets.restored \
        || exit $?
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test hardlink changes between index and save -- hardlink set [a
    # b c d] changes to [a b] [c d].  At least right now bup should
    # notice and recreate the latter.
    WVPASS setup-hardlink-test
    WVPASS cd "$TOP/bupmeta.tmp"/src
    WVPASS touch a
    WVPASS ln a b
    WVPASS ln a c
    WVPASS ln a d
    WVPASS cd ..
    WVPASS bup index -vv src
    WVPASS rm src/c src/d
    WVPASS touch src/c
    WVPASS ln src/c src/d
    WVPASS bup save -t -n src src
    WVPASS hardlink-test-run-restore
    WVPASS echo ./src/a > hardlink-sets.expected
    WVPASS echo ./src/b >> hardlink-sets.expected
    WVPASS echo >> hardlink-sets.expected
    WVPASS echo ./src/c >> hardlink-sets.expected
    WVPASS echo ./src/d >> hardlink-sets.expected
    (WVPASS cd src-restore; WVPASS hardlink-sets .) > hardlink-sets.restored \
        || exit $?
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test that we don't link outside restore tree.
    WVPASS setup-hardlink-test
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS mkdir src/a src/b
    WVPASS touch src/a/1
    WVPASS ln src/a/1 src/b/1
    WVPASS bup index -vv src
    WVPASS bup save -t -n src src
    WVPASS force-delete src-restore
    WVPASS mkdir src-restore
    WVPASS bup restore -C src-restore "/src/latest$(pwd -P)/src/a/"
    WVPASS test -e src-restore/1
    WVPASS echo -n > hardlink-sets.expected
    (WVPASS cd src-restore; WVPASS hardlink-sets .) > hardlink-sets.restored \
        || exit $?
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored

    # Test that we do link within separate sub-trees.
    WVPASS setup-hardlink-test
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS mkdir src/a src/b
    WVPASS touch src/a/1
    WVPASS ln src/a/1 src/b/1
    WVPASS bup index -vv src/a src/b
    WVPASS bup save -t -n src src/a src/b
    WVPASS hardlink-test-run-restore
    WVPASS echo ./src/a/1 > hardlink-sets.expected
    WVPASS echo ./src/b/1 >> hardlink-sets.expected
    (WVPASS cd src-restore; WVPASS hardlink-sets .) > hardlink-sets.restored \
        || exit $?
    WVPASS diff -u hardlink-sets.expected hardlink-sets.restored
) || exit $?

WVSTART 'meta --edit'
(
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir "$TOP/bupmeta.tmp"
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS mkdir src
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
) || exit $?

WVSTART 'meta --no-recurse'
(
    set +e
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir "$TOP/bupmeta.tmp"
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS mkdir src
    WVPASS mkdir src/foo
    WVPASS touch src/foo/{1,2,3}
    WVPASS bup meta -cf src.meta src
    WVPASSEQ "$(LC_ALL=C; bup meta -tf src.meta | sort)" "src/
src/foo/
src/foo/1
src/foo/2
src/foo/3"
    WVPASS bup meta --no-recurse -cf src.meta src
    WVPASSEQ "$(LC_ALL=C; bup meta -tf src.meta | sort)" "src/"
) || exit $?

# Test ownership restoration (when not root or fakeroot).
(
    if [ $(t/root-status) != none ]; then
        exit 0
    fi

    WVSTART 'metadata (restoration of ownership)'
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir "$TOP/bupmeta.tmp"
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS touch src
    WVPASS bup meta -cf src.meta src

    WVPASS mkdir dest
    WVPASS cd dest
    # Make sure we don't change (or try to change) the user when not root.
    WVPASS bup meta --edit --set-user root ../src.meta | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qvE '^user: root'
    WVPASS rm -rf src
    WVPASS bup meta --edit --unset-user --set-uid 0 ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qvE '^user: root'

    # Make sure we can restore one of the user's groups.
    last_group="$(python -c 'import os,grp; \
      print grp.getgrgid(os.getgroups()[0])[0]')"
    WVPASS rm -rf src
    WVPASS bup meta --edit --set-group "$last_group" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^group: $last_group"

    # Make sure we can restore one of the user's gids.
    user_gids="$(id -G)"
    last_gid="$(echo ${user_gids/* /})"
    WVPASS rm -rf src
    WVPASS bup meta --edit --unset-group --set-gid "$last_gid" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^gid: $last_gid"

    # Test --numeric-ids (gid).
    WVPASS rm -rf src
    current_gidx=$(bup meta -tvvf ../src.meta | grep -e '^gid:')
    WVPASS bup meta --edit --set-group "$last_group" ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$current_gidx" "$new_gidx"

    # Test that restoring an unknown user works.
    unknown_user=$("$TOP"/t/unknown-owner --user)
    WVPASS rm -rf src
    current_uidx=$(bup meta -tvvf ../src.meta | grep -e '^uid:')
    WVPASS bup meta --edit --set-user "$unknown_user" ../src.meta \
        | WVPASS bup meta -x
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$current_uidx" "$new_uidx"

    # Test that restoring an unknown group works.
    unknown_group=$("$TOP"/t/unknown-owner --group)
    WVPASS rm -rf src
    current_gidx=$(bup meta -tvvf ../src.meta | grep -e '^gid:')
    WVPASS bup meta --edit --set-group "$unknown_group" ../src.meta \
        | WVPASS bup meta -x
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$current_gidx" "$new_gidx"
) || exit $?

# Test ownership restoration (when root or fakeroot).
(
    if [ $(t/root-status) = none ]; then
        exit 0
    fi

    WVSTART 'metadata (restoration of ownership as root)'
    WVPASS force-delete "$TOP/bupmeta.tmp"
    WVPASS mkdir "$TOP/bupmeta.tmp"
    WVPASS cd "$TOP/bupmeta.tmp"
    WVPASS touch src
    WVPASS chown 0:0 src # In case the parent dir is sgid, etc.
    WVPASS bup meta -cf src.meta src

    WVPASS mkdir dest
    WVPASS chmod 700 dest # so we can't accidentally do something insecure
    WVPASS cd dest

    other_uinfo="$(id-other-than --user "$(id -un)")"
    other_user="${other_uinfo%%:*}"
    other_uid="${other_uinfo##*:}"

    other_ginfo="$(id-other-than --group "$(id -gn)")"
    other_group="${other_ginfo%%:*}"
    other_gid="${other_ginfo##*:}"

    # Make sure we can restore a uid (must be in /etc/passwd b/c cygwin).
    WVPASS bup meta --edit --unset-user --set-uid "$other_uid" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^uid: $other_uid"

    # Make sure we can restore a gid (must be in /etc/group b/c cygwin).
    WVPASS bup meta --edit --unset-group --set-gid "$other_gid" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^gid: $other_gid"

    other_uinfo2="$(id-other-than --user "$(id -un)" "$other_user")"
    other_user2="${other_uinfo2%%:*}"
    other_uid2="${other_uinfo2##*:}"

    other_ginfo2="$(id-other-than --group "$(id -gn)" "$other_group")"
    other_group2="${other_ginfo2%%:*}"
    other_gid2="${other_ginfo2##*:}"

    # Try to restore a user (and see that user trumps uid when uid is not 0).
    WVPASS bup meta --edit \
        --set-uid "$other_uid2" --set-user "$some_user" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^user: $some_user"

    # Try to restore a group (and see that group trumps gid when gid is not 0).
    WVPASS bup meta --edit \
        --set-gid "$other_gid2" --set-group "$some_group" ../src.meta \
        | WVPASS bup meta -x
    WVPASS bup xstat src | WVPASS grep -qE "^group: $some_user"

    # Test --numeric-ids (uid).  Note the name 'root' is not handled
    # specially, so we use that here as the test user name.  We assume
    # that the root user's uid is never 42.
    WVPASS rm -rf src
    WVPASS bup meta --edit --set-user root --set-uid "$other_uid" ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$new_uidx" "uid: $other_uid"

    # Test --numeric-ids (gid).  Note the name 'root' is not handled
    # specially, so we use that here as the test group name.  We
    # assume that the root group's gid is never 42.
    WVPASS rm -rf src
    WVPASS bup meta --edit --set-group root --set-gid "$other_gid" ../src.meta \
        | WVPASS bup meta -x --numeric-ids
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$new_gidx" "gid: $other_gid"

    # Test that restoring an unknown user works.
    unknown_user=$("$TOP"/t/unknown-owners --user)
    WVPASS rm -rf src
    WVPASS bup meta --edit \
        --set-uid "$other_uid" --set-user "$unknown_user" ../src.meta \
        | WVPASS bup meta -x
    new_uidx=$(bup xstat src | grep -e '^uid:')
    WVPASSEQ "$new_uidx" "uid: $other_uid"

    # Test that restoring an unknown group works.
    unknown_group=$("$TOP"/t/unknown-owners --group)
    WVPASS rm -rf src
    WVPASS bup meta --edit \
        --set-gid "$other_gid" --set-group "$unknown_group" ../src.meta \
        | WVPASS bup meta -x
    new_gidx=$(bup xstat src | grep -e '^gid:')
    WVPASSEQ "$new_gidx" "gid: $other_gid"

    if ! [[ $(uname) =~ CYGWIN ]]; then
        # For now, skip these on Cygwin because it doesn't allow
        # restoring an unknown uid/gid.

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
    fi
) || exit $?


# Root-only tests that require an FS with all the trimmings: ACLs,
# Linux attr, Linux xattr, etc.
if [ $(t/root-status) = root ]; then
    (
        # Some cleanup handled in universal-cleanup() above.
        # These tests are only likely to work under Linux for now
        # (patches welcome).
        [[ $(uname) =~ Linux ]] || exit 0

        WVSTART 'meta - general (as root)'
        WVPASS setup-test-tree
        WVPASS cd "$TOP/bupmeta.tmp"

        umount testfs
        WVPASS dd if=/dev/zero of=testfs.img bs=1M count=32
        # Make sure we have all the options the chattr test needs
        # (i.e. create a "normal" ext4 filesystem).
        WVPASS mke2fs -F -m 0 \
            -I 256 \
            -O has_journal,extent,huge_file,flex_bg,uninit_bg,dir_nlink,extra_isize \
            testfs.img
        WVPASS mkdir testfs
        WVPASS mount -o loop,acl,user_xattr testfs.img testfs
        # Hide, so that tests can't create risks.
        WVPASS chown root:root testfs
        WVPASS chmod 0700 testfs

        umount testfs-limited
        WVPASS dd if=/dev/zero of=testfs-limited.img bs=1M count=32
        WVPASS mkfs -t vfat testfs-limited.img
        WVPASS mkdir testfs-limited
        WVPASS mount -o loop,uid=root,gid=root,umask=0077 \
            testfs-limited.img testfs-limited

        WVPASS cp -pPR src testfs/src
        (WVPASS cd testfs; WVPASS test-src-create-extract) || exit $?

        WVSTART 'meta - atime (as root)'
        WVPASS force-delete testfs/src
        WVPASS mkdir testfs/src
        (
            WVPASS mkdir testfs/src/foo
            WVPASS touch testfs/src/bar
            PYTHONPATH="$TOP/lib" \
                WVPASS python -c "from bup import xstat; \
                x = xstat.timespec_to_nsecs((42, 0));\
                   xstat.utime('testfs/src/foo', (x, x));\
                   xstat.utime('testfs/src/bar', (x, x));"
            WVPASS cd testfs
            WVPASS bup meta -v --create --recurse --file src.meta src
            WVPASS bup meta -tvf src.meta
            # Test extract.
            WVPASS force-delete src-restore
            WVPASS mkdir src-restore
            WVPASS cd src-restore
            WVPASS bup meta --extract --file ../src.meta
            WVPASSEQ "$(bup xstat --include-fields=atime src/foo)" "atime: 42"
            WVPASSEQ "$(bup xstat --include-fields=atime src/bar)" "atime: 42"
            # Test start/finish extract.
            WVPASS force-delete src
            WVPASS bup meta --start-extract --file ../src.meta
            WVPASS test -d src
            WVPASS bup meta --finish-extract --file ../src.meta
            WVPASSEQ "$(bup xstat --include-fields=atime src/foo)" "atime: 42"
            WVPASSEQ "$(bup xstat --include-fields=atime src/bar)" "atime: 42"
        ) || exit $?

        WVSTART 'meta - Linux attr (as root)'
        WVPASS force-delete testfs/src
        WVPASS mkdir testfs/src
        (
            WVPASS touch testfs/src/foo
            WVPASS mkdir testfs/src/bar
            WVPASS chattr +acdeijstuADST testfs/src/foo
            WVPASS chattr +acdeijstuADST testfs/src/bar
            (WVPASS cd testfs; WVPASS test-src-create-extract) || exit $?
            # Test restoration to a limited filesystem (vfat).
            (
                WVPASS bup meta --create --recurse --file testfs/src.meta \
                    testfs/src
                WVPASS force-delete testfs-limited/src-restore
                WVPASS mkdir testfs-limited/src-restore
                WVPASS cd testfs-limited/src-restore
                WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                    | WVPASS grep -e '^Linux chattr:' \
                    | WVPASS python -c \
                    'import sys; exit(not len(sys.stdin.readlines()) == 3)'
            ) || exit $?
        ) || exit $?

        WVSTART 'meta - Linux xattr (as root)'
        WVPASS force-delete testfs/src
        WVPASS mkdir testfs/src
        WVPASS touch testfs/src/foo
        WVPASS mkdir testfs/src/bar
        WVPASS attr -s foo -V bar testfs/src/foo
        WVPASS attr -s foo -V bar testfs/src/bar
        (WVPASS cd testfs; WVPASS test-src-create-extract) || exit $?

        # Test restoration to a limited filesystem (vfat).
        (
            WVPASS bup meta --create --recurse --file testfs/src.meta \
                testfs/src
            WVPASS force-delete testfs-limited/src-restore
            WVPASS mkdir testfs-limited/src-restore
            WVPASS cd testfs-limited/src-restore
            WVFAIL bup meta --extract --file ../../testfs/src.meta
            WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                | WVPASS grep -e '^xattr\.set:' \
                | WVPASS python -c \
                'import sys; exit(not len(sys.stdin.readlines()) == 2)'
        ) || exit $?

        WVSTART 'meta - POSIX.1e ACLs (as root)'
        WVPASS force-delete testfs/src
        WVPASS mkdir testfs/src
        WVPASS touch testfs/src/foo
        WVPASS mkdir testfs/src/bar
        WVPASS setfacl -m u:root:r testfs/src/foo
        WVPASS setfacl -m u:root:r testfs/src/bar
        (WVPASS cd testfs; WVPASS test-src-create-extract) || exit $?

        # Test restoration to a limited filesystem (vfat).
        (
            WVPASS bup meta --create --recurse --file testfs/src.meta \
                testfs/src
            WVPASS force-delete testfs-limited/src-restore
            WVPASS mkdir testfs-limited/src-restore
            WVPASS cd testfs-limited/src-restore
            WVFAIL bup meta --extract --file ../../testfs/src.meta 2>&1 \
                | WVPASS grep -e '^POSIX1e ACL applyto:' \
                | WVPASS python -c \
                'import sys; exit(not len(sys.stdin.readlines()) == 2)'
        ) || exit $?
    ) || exit $?
fi
