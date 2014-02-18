#!/usr/bin/env bash
. ./wvtest-bup.sh

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
WVPASS touch -t 196907202018 src/.dotfile
WVPASS bup random 1k > src/file
WVPASS touch -t 196907202018 src/file
(WVPASS cd src; WVPASS ln -s file symlink) || exit $?
WVPASS mkfifo src/fifo
WVPASS touch -t 196907202018 src/fifo
WVPASS "$top"/t/mksock src/socket
WVPASS touch -t 196907202018 src/socket
WVPASS touch -t 196907202018 src/executable
WVPASS chmod u+x src/executable
WVPASS touch -t 196907202018 src/executable
WVPASS touch -t 196907202018 src
WVPASS touch -t 196907202018 .
WVPASS chmod -R u=rwX,g-rwx,o-rwx .
WVPASS bup index src
WVPASS bup save -n src src

WVSTART "ls (short)"

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

symlink_size="$(WVPASS python -c "import os
print os.lstat('src/symlink').st_size")" || exit $?

symlink_date="$(WVPASS bup ls -l src/latest"$tmpdir"/src | grep symlink)" || exit $?
symlink_date="$(WVPASS echo "$symlink_date" \
  | WVPASS perl -ne 'm/.*? (\d+) (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $2')" \
    || exit $?

uid="$(id -u)" || exit $?
gid="$(id -g)" || exit $?
user="$(id -un)" || exit $?
group="$(id -gn)" || exit $?

WVPASSEQ "$(bup ls -l src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 1969-07-20 20:18 executable
prw------- $user/$group 0 1969-07-20 20:18 fifo
-rw------- $user/$group 1024 1969-07-20 20:18 file
srwx------ $user/$group 0 1969-07-20 20:18 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -la src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"drwx------ $user/$group 0 1969-07-20 20:18 .
drwx------ $user/$group 0 1969-07-20 20:18 ..
-rw------- $user/$group 0 1969-07-20 20:18 .dotfile
-rwx------ $user/$group 0 1969-07-20 20:18 executable
prw------- $user/$group 0 1969-07-20 20:18 fifo
-rw------- $user/$group 1024 1969-07-20 20:18 file
srwx------ $user/$group 0 1969-07-20 20:18 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lA src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rw------- $user/$group 0 1969-07-20 20:18 .dotfile
-rwx------ $user/$group 0 1969-07-20 20:18 executable
prw------- $user/$group 0 1969-07-20 20:18 fifo
-rw------- $user/$group 1024 1969-07-20 20:18 file
srwx------ $user/$group 0 1969-07-20 20:18 socket
$symlink_mode $user/$group $symlink_size $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lF src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 1969-07-20 20:18 executable*
prw------- $user/$group 0 1969-07-20 20:18 fifo|
-rw------- $user/$group 1024 1969-07-20 20:18 file
srwx------ $user/$group 0 1969-07-20 20:18 socket=
$symlink_mode $user/$group $symlink_size $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -l --file-type src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group 0 1969-07-20 20:18 executable
prw------- $user/$group 0 1969-07-20 20:18 fifo|
-rw------- $user/$group 1024 1969-07-20 20:18 file
srwx------ $user/$group 0 1969-07-20 20:18 socket=
$symlink_mode $user/$group $symlink_size $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -ln src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $uid/$gid 0 1969-07-20 20:18 executable
prw------- $uid/$gid 0 1969-07-20 20:18 fifo
-rw------- $uid/$gid 1024 1969-07-20 20:18 file
srwx------ $uid/$gid 0 1969-07-20 20:18 socket
$symlink_mode $uid/$gid $symlink_size $symlink_date symlink -> file"

WVSTART "ls (backup set - long)"
WVPASSEQ "$(bup ls -l src | cut -d' ' -f 1-2)" \
"l--------- ?/?
l--------- ?/?"

WVSTART "ls (dates TZ != UTC)"
export TZ=US/Central
symlink_date_central="$(bup ls -l src/latest"$tmpdir"/src | grep symlink)"
symlink_date_central="$(echo "$symlink_date_central" \
  | perl -ne 'm/.*? (\d+) (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $2')"
WVPASSEQ "$(bup ls -ln src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $uid/$gid 0 1969-07-20 15:18 executable
prw------- $uid/$gid 0 1969-07-20 15:18 fifo
-rw------- $uid/$gid 1024 1969-07-20 15:18 file
srwx------ $uid/$gid 0 1969-07-20 15:18 socket
$symlink_mode $uid/$gid $symlink_size $symlink_date_central symlink -> file"
unset TZ

WVPASS rm -rf "$tmpdir"
