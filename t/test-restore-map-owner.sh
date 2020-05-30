#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. t/lib.sh || exit $?

root_status="$(t/root-status)" || exit $?

if [ "$root_status" != root ]; then
    echo 'Not root: skipping restore --map-* tests.'
    exit 0 # FIXME: add WVSKIP.
fi

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

uid=$(WVPASS id -u) || exit $?
user=$(WVPASS id -un) || exit $?
gid=$(WVPASS id -g) || exit $?
group=$(WVPASS id -gn) || exit $?

other_uinfo=$(WVPASS t/id-other-than --user "$user") || exit $?
other_user="${other_uinfo%%:*}"
other_uid="${other_uinfo##*:}"

other_ginfo=$(WVPASS t/id-other-than --group "$group" 0) || exit $?
other_group="${other_ginfo%%:*}"
other_gid="${other_ginfo##*:}"

WVPASS bup init
WVPASS cd "$tmpdir"

WVSTART "restore --map-user/group/uid/gid (control)"
WVPASS mkdir src
WVPASS touch src/foo
# Some systems assign the parent dir group to new paths.
WVPASS chgrp -R "$group" src
WVPASS bup index src
WVPASS bup save -n src src
WVPASS bup restore -C dest "src/latest/$(pwd)/src/"
WVPASS bup xstat dest/foo > foo-xstat
WVPASS grep -qE "^user: $user\$" foo-xstat
WVPASS grep -qE "^uid: $uid\$" foo-xstat
WVPASS grep -qE "^group: $group\$" foo-xstat
WVPASS grep -qE "^gid: $gid\$" foo-xstat

WVSTART "restore --map-user/group/uid/gid (user/group)"
WVPASS rm -rf dest
# Have to remap uid/gid too because we're root and 0 would win).
WVPASS bup restore -C dest \
    --map-uid "$uid=$other_uid" --map-gid "$gid=$other_gid" \
    --map-user "$user=$other_user" --map-group "$group=$other_group" \
    "src/latest/$(pwd)/src/"
WVPASS bup xstat dest/foo > foo-xstat
WVPASS grep -qE "^user: $other_user\$" foo-xstat
WVPASS grep -qE "^uid: $other_uid\$" foo-xstat
WVPASS grep -qE "^group: $other_group\$" foo-xstat
WVPASS grep -qE "^gid: $other_gid\$" foo-xstat

WVSTART "restore --map-user/group/uid/gid (user/group trumps uid/gid)"
WVPASS rm -rf dest
WVPASS bup restore -C dest \
    --map-uid "$uid=$other_uid" --map-gid "$gid=$other_gid" \
    "src/latest/$(pwd)/src/"
# Should be no changes.
WVPASS bup xstat dest/foo > foo-xstat
WVPASS grep -qE "^user: $user\$" foo-xstat
WVPASS grep -qE "^uid: $uid\$" foo-xstat
WVPASS grep -qE "^group: $group\$" foo-xstat
WVPASS grep -qE "^gid: $gid\$" foo-xstat

WVSTART "restore --map-user/group/uid/gid (uid/gid)"
WVPASS rm -rf dest
WVPASS bup restore -C dest \
    --map-user "$user=" --map-group "$group=" \
    --map-uid "$uid=$other_uid" --map-gid "$gid=$other_gid" \
    "src/latest/$(pwd)/src/"
WVPASS bup xstat dest/foo > foo-xstat
WVPASS grep -qE "^user: $other_user\$" foo-xstat
WVPASS grep -qE "^uid: $other_uid\$" foo-xstat
WVPASS grep -qE "^group: $other_group\$" foo-xstat
WVPASS grep -qE "^gid: $other_gid\$" foo-xstat

has_uid_gid_0=$(WVPASS bup-cfg-py -c "
import grp, pwd
try:
  pwd.getpwuid(0)
  grp.getgrgid(0)
  print('yes')
except KeyError as ex:
  pass
") || exit $?
if [ "$has_uid_gid_0" == yes ]
then
    WVSTART "restore --map-user/group/uid/gid (zero uid/gid trumps all)"
    WVPASS rm -rf dest
    WVPASS bup restore -C dest \
        --map-user "$user=$other_user" --map-group "$group=$other_group" \
        --map-uid "$uid=0" --map-gid "$gid=0" \
        "src/latest/$(pwd)/src/"
    WVPASS bup xstat dest/foo > foo-xstat
    WVPASS grep -qE "^uid: 0\$" foo-xstat
    WVPASS grep -qE "^gid: 0\$" foo-xstat

    WVPASS rm -rf "$tmpdir"
fi
