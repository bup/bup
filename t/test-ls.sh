#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. t/lib.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

export TZ=UTC

WVPASS bup init
WVPASS cd "$tmpdir"

WVPASS mkdir src
WVPASS touch src/.dotfile src/executable
WVPASS mkfifo src/fifo
WVPASS "$top"/t/mksock src/socket
WVPASS bup random 1k > src/file
WVPASS chmod u+x src/executable
WVPASS chmod -R u=rwX,g-rwx,o-rwx .
WVPASS touch -t 200910032348 src/.dotfile src/*
(WVPASS cd src; WVPASS ln -s file symlink) || exit $?
WVPASS touch -t 200910032348 src
WVPASS touch -t 200910032348 .
WVPASS bup index src
WVPASS bup save -n src -d 242312160 src
WVPASS bup tag some-tag src


WVSTART "ls (short)"

(export BUP_FORCE_TTY=1; WVPASSEQ "$(WVPASS bup ls | tr -d ' ')" src)

WVPASSEQ "$(WVPASS bup ls /)" "src"

WVPASSEQ "$(WVPASS bup ls -A /)" ".commit
.tag
src"

WVPASSEQ "$(WVPASS bup ls -AF /)" ".commit/
.tag/
src/"

WVPASSEQ "$(WVPASS bup ls -a /)" ".
..
.commit
.tag
src"

WVPASSEQ "$(WVPASS bup ls -aF /)" "./
../
.commit/
.tag/
src/"

WVPASSEQ "$(WVPASS bup ls /.tag)" "some-tag"

WVPASSEQ "$(WVPASS bup ls /src)" \
"1977-09-05-125600
latest"

WVPASSEQ "$(WVPASS bup ls src/latest/"$tmpdir"/src)" "executable
fifo
file
socket
symlink"

WVPASSEQ "$(WVPASS bup ls -A src/latest/"$tmpdir"/src)" ".dotfile
executable
fifo
file
socket
symlink"

WVPASSEQ "$(WVPASS bup ls -a src/latest/"$tmpdir"/src)" ".
..
.dotfile
executable
fifo
file
socket
symlink"

WVPASSEQ "$(WVPASS bup ls -F src/latest/"$tmpdir"/src)" "executable*
fifo|
file
socket=
symlink@"

WVPASSEQ "$(WVPASS bup ls --file-type src/latest/"$tmpdir"/src)" "executable
fifo|
file
socket=
symlink@"

WVPASSEQ "$(WVPASS bup ls -d src/latest/"$tmpdir"/src)" "src/latest$tmpdir/src"


WVSTART "ls (long)"

WVPASSEQ "$(WVPASS bup ls -l / | tr -s ' ' ' ')" \
"d--------- ?/? 0 1970-01-01 00:00 src"

WVPASSEQ "$(WVPASS bup ls -lA / | tr -s ' ' ' ')" \
"d--------- ?/? 0 1970-01-01 00:00 .commit
d--------- ?/? 0 1970-01-01 00:00 .tag
d--------- ?/? 0 1970-01-01 00:00 src"

WVPASSEQ "$(WVPASS bup ls -lAF / | tr -s ' ' ' ')" \
"d--------- ?/? 0 1970-01-01 00:00 .commit/
d--------- ?/? 0 1970-01-01 00:00 .tag/
d--------- ?/? 0 1970-01-01 00:00 src/"

WVPASSEQ "$(WVPASS bup ls -la / | tr -s ' ' ' ')" \
"d--------- ?/? 0 1970-01-01 00:00 .
d--------- ?/? 0 1970-01-01 00:00 ..
d--------- ?/? 0 1970-01-01 00:00 .commit
d--------- ?/? 0 1970-01-01 00:00 .tag
d--------- ?/? 0 1970-01-01 00:00 src"

WVPASSEQ "$(WVPASS bup ls -laF / | tr -s ' ' ' ')" \
"d--------- ?/? 0 1970-01-01 00:00 ./
d--------- ?/? 0 1970-01-01 00:00 ../
d--------- ?/? 0 1970-01-01 00:00 .commit/
d--------- ?/? 0 1970-01-01 00:00 .tag/
d--------- ?/? 0 1970-01-01 00:00 src/"

symlink_mode="$(WVPASS ls -l src/symlink | cut -b -10)" || exit $?
socket_mode="$(WVPASS ls -l src/socket | cut -b -10)" || exit $?

symlink_bup_info="$(WVPASS bup ls -l src/latest"$tmpdir"/src | grep symlink)" \
    || exit $?
symlink_date="$(WVPASS echo "$symlink_bup_info" \
  | WVPASS perl -ne 'm/.*? (\d+) (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $2')" \
    || exit $?

if test "$(uname -s)" != NetBSD; then
    symlink_size="$(WVPASS bup-python -c "import os
print os.lstat('src/symlink').st_size")" || exit $?
else
    # NetBSD appears to return varying sizes, so for now, just ignore it.
    symlink_size="$(WVPASS echo "$symlink_bup_info" \
      | WVPASS perl -ne 'm/.*? (\d+) (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $1')" \
        || exit $?
fi

uid="$(WVPASS id -u)" || exit $?
gid="$(WVPASS bup-python -c 'import os; print os.stat("src").st_gid')" || exit $?
user="$(WVPASS id -un)" || exit $?
group="$(WVPASS bup-python -c 'import grp, os;
print grp.getgrgid(os.stat("src").st_gid)[0]')" || exit $?

WVPASSEQ "$(bup ls -l src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 2009-10-03 23:48 executable
prw------- $user/$group 0 2009-10-03 23:48 fifo
-rw------- $user/$group 1024 2009-10-03 23:48 file
$socket_mode $user/$group 0 2009-10-03 23:48 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -la src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"drwx------ $user/$group 0 2009-10-03 23:48 .
drwx------ $user/$group 0 2009-10-03 23:48 ..
-rw------- $user/$group 0 2009-10-03 23:48 .dotfile
-rwx------ $user/$group 0 2009-10-03 23:48 executable
prw------- $user/$group 0 2009-10-03 23:48 fifo
-rw------- $user/$group 1024 2009-10-03 23:48 file
$socket_mode $user/$group 0 2009-10-03 23:48 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lA src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rw------- $user/$group 0 2009-10-03 23:48 .dotfile
-rwx------ $user/$group 0 2009-10-03 23:48 executable
prw------- $user/$group 0 2009-10-03 23:48 fifo
-rw------- $user/$group 1024 2009-10-03 23:48 file
$socket_mode $user/$group 0 2009-10-03 23:48 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lF src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 2009-10-03 23:48 executable*
prw------- $user/$group 0 2009-10-03 23:48 fifo|
-rw------- $user/$group 1024 2009-10-03 23:48 file
$socket_mode $user/$group 0 2009-10-03 23:48 socket=
$symlink_mode $user/$group $symlink_size $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -l --file-type src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 2009-10-03 23:48 executable
prw------- $user/$group 0 2009-10-03 23:48 fifo|
-rw------- $user/$group 1024 2009-10-03 23:48 file
$socket_mode $user/$group 0 2009-10-03 23:48 socket=
$symlink_mode $user/$group $symlink_size $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -ln src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $uid/$gid 0 2009-10-03 23:48 executable
prw------- $uid/$gid 0 2009-10-03 23:48 fifo
-rw------- $uid/$gid 1024 2009-10-03 23:48 file
$socket_mode $uid/$gid 0 2009-10-03 23:48 socket
$symlink_mode $uid/$gid $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -ld "src/latest$tmpdir/src" | tr -s ' ' ' ')" \
"drwx------ $user/$group 0 2009-10-03 23:48 src/latest$tmpdir/src"


WVSTART "ls (backup set - long)"
WVPASSEQ "$(bup ls -l src | cut -d' ' -f 1-2)" \
"l--------- ?/?
l--------- ?/?"


WVSTART "ls (dates TZ != UTC)"
export TZ=America/Chicago
symlink_date_central="$(bup ls -l src/latest"$tmpdir"/src | grep symlink)"
symlink_date_central="$(echo "$symlink_date_central" \
  | perl -ne 'm/.*? (\d+) (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $2')"
WVPASSEQ "$(bup ls -ln src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $uid/$gid 0 2009-10-03 18:48 executable
prw------- $uid/$gid 0 2009-10-03 18:48 fifo
-rw------- $uid/$gid 1024 2009-10-03 18:48 file
$socket_mode $uid/$gid 0 2009-10-03 18:48 socket
$symlink_mode $uid/$gid $symlink_size $symlink_date_central symlink -> file"
unset TZ


WVPASS rm -rf "$tmpdir"
