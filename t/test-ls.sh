#!/usr/bin/env bash
. ./wvtest-bup.sh

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"

bup() { "$top/bup" "$@"; }

WVPASS bup init
WVPASS cd "$tmpdir"

WVPASS mkdir src
WVPASS touch -t 191111111111 src/.dotfile
WVPASS date > src/file
WVPASS touch -t 191111111111 src/file
(WVPASS cd src; WVPASS ln -s file symlink) || exit $?
WVPASS mkfifo src/fifo
WVPASS touch -t 191111111111 src/fifo
WVPASS "$top"/t/mksock src/socket
WVPASS touch -t 191111111111 src/socket
WVPASS touch -t 191111111111 src/executable
WVPASS chmod u+x src/executable
WVPASS touch -t 191111111111 src/executable
WVPASS touch -t 191111111111 src
WVPASS touch -t 191111111111 .
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
"d--------- ?/? - 1969-12-31 18:00 src"

WVPASSEQ "$(WVPASS bup ls -lA / | tr -s ' ' ' ')" \
"d--------- ?/? - 1969-12-31 18:00 .commit
d--------- ?/? - 1969-12-31 18:00 .tag
d--------- ?/? - 1969-12-31 18:00 src"

WVPASSEQ "$(WVPASS bup ls -lAF / | tr -s ' ' ' ')" \
"d--------- ?/? - 1969-12-31 18:00 .commit/
d--------- ?/? - 1969-12-31 18:00 .tag/
d--------- ?/? - 1969-12-31 18:00 src/"

WVPASSEQ "$(WVPASS bup ls -la / | tr -s ' ' ' ')" \
"d--------- ?/? - 1969-12-31 18:00 .
d--------- ?/? - 1969-12-31 18:00 ..
d--------- ?/? - 1969-12-31 18:00 .commit
d--------- ?/? - 1969-12-31 18:00 .tag
d--------- ?/? - 1969-12-31 18:00 src"

WVPASSEQ "$(WVPASS bup ls -laF / | tr -s ' ' ' ')" \
"d--------- ?/? - 1969-12-31 18:00 ./
d--------- ?/? - 1969-12-31 18:00 ../
d--------- ?/? - 1969-12-31 18:00 .commit/
d--------- ?/? - 1969-12-31 18:00 .tag/
d--------- ?/? - 1969-12-31 18:00 src/"

symlink_date="$(bup ls -l src/latest"$tmpdir"/src | grep symlink)"
symlink_date="$(echo "$symlink_date" \
  | perl -ne 'm/.*? - (\d\d\d\d-\d\d-\d\d \d\d:\d\d)/ and print $1')"
uid="$(id -u)" || exit $?
gid="$(id -g)" || exit $?
user="$(id -un)" || exit $?
group="$(id -gn)" || exit $?

WVPASSEQ "$(bup ls -l src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group - 1911-11-11 11:11 executable
prw------- $user/$group - 1911-11-11 11:11 fifo
-rw------- $user/$group - 1911-11-11 11:11 file
srwx------ $user/$group - 1911-11-11 11:11 socket
lrwxrwxrwx $user/$group - $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -la src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"drwx------ $user/$group - 1911-11-11 11:11 .
drwx------ $user/$group - 1911-11-11 11:11 ..
-rw------- $user/$group - 1911-11-11 11:11 .dotfile
-rwx------ $user/$group - 1911-11-11 11:11 executable
prw------- $user/$group - 1911-11-11 11:11 fifo
-rw------- $user/$group - 1911-11-11 11:11 file
srwx------ $user/$group - 1911-11-11 11:11 socket
lrwxrwxrwx $user/$group - $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lA src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rw------- $user/$group - 1911-11-11 11:11 .dotfile
-rwx------ $user/$group - 1911-11-11 11:11 executable
prw------- $user/$group - 1911-11-11 11:11 fifo
-rw------- $user/$group - 1911-11-11 11:11 file
srwx------ $user/$group - 1911-11-11 11:11 socket
lrwxrwxrwx $user/$group - $symlink_date symlink -> file"

WVPASSEQ "$(bup ls -lF src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group - 1911-11-11 11:11 executable*
prw------- $user/$group - 1911-11-11 11:11 fifo|
-rw------- $user/$group - 1911-11-11 11:11 file
srwx------ $user/$group - 1911-11-11 11:11 socket=
lrwxrwxrwx $user/$group - $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -l --file-type src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $user/$group - 1911-11-11 11:11 executable
prw------- $user/$group - 1911-11-11 11:11 fifo|
-rw------- $user/$group - 1911-11-11 11:11 file
srwx------ $user/$group - 1911-11-11 11:11 socket=
lrwxrwxrwx $user/$group - $symlink_date symlink@ -> file"

WVPASSEQ "$(bup ls -ln src/latest"$tmpdir"/src | tr -s ' ' ' ')" \
"-rwx------ $uid/$gid - 1911-11-11 11:11 executable
prw------- $uid/$gid - 1911-11-11 11:11 fifo
-rw------- $uid/$gid - 1911-11-11 11:11 file
srwx------ $uid/$gid - 1911-11-11 11:11 socket
lrwxrwxrwx $uid/$gid - $symlink_date symlink -> file"

WVSTART "ls (backup set - long)"
WVPASSEQ "$(bup ls -l src | cut -d' ' -f 1-2)" \
"l--------- ?/?
l--------- ?/?"

WVPASS rm -rf "$tmpdir"
