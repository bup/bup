#!/usr/bin/env bash

cmd_dir="$(cd "$(dirname "$0")" && pwd)" || exit $?

set -o pipefail

must() {
    local file=${BASH_SOURCE[0]}
    local line=${BASH_LINENO[0]}
    "$@"
    local rc=$?
    if test $rc -ne 0; then
        echo "Failed at line $line in $file" 1>&2
        exit $rc
    fi
}

usage() {
    echo "Usage: bup import-rdiff-backup [-n]" \
        "<path to rdiff-backup root> <backup name>"
    echo "-n,--dry-run: just print what would be done"
    exit 1
}

control_c() {
    echo "bup import-rdiff-backup: signal 2 received" 1>&2
    exit 128
}

must trap control_c INT

dry_run=
while [ "$1" = "-n" -o "$1" = "--dry-run" ]; do
    dry_run=echo
    shift
done

bup()
{
    $dry_run "$cmd_dir/bup" "$@"
}

snapshot_root="$1"
branch="$2"

[ -n "$snapshot_root" -a "$#" = 2 ] || usage

if [ ! -e "$snapshot_root/." ]; then
    echo "'$snapshot_root' isn't a directory!"
    exit 1
fi


backups=$(must rdiff-backup --list-increments --parsable-output "$snapshot_root") \
    || exit $?
backups_count=$(echo "$backups" | must wc -l) || exit $?
counter=1
echo "$backups" |
while read timestamp type; do
    tmpdir=$(must mktemp -d import-rdiff-backup-XXXXXXX) || exit $?

    echo "Importing backup from $(date -d @$timestamp +%c) " \
        "($counter / $backups_count)" 1>&2
    echo 1>&2

    echo "Restoring from rdiff-backup..." 1>&2
    must rdiff-backup -r $timestamp "$snapshot_root" "$tmpdir"
    echo 1>&2

    echo "Importing into bup..." 1>&2
    TMPIDX=$(must mktemp -u import-rdiff-backup-idx-XXXXXXX) || exit $?
    must bup index -ux -f "$tmpidx" "$tmpdir"
    must bup save --strip --date="$timestamp" -f "$tmpidx" -n "$branch" "$tmpdir"
    must rm -f "$tmpidx"

    must rm -rf "$tmpdir"
    counter=$((counter+1))
    echo 1>&2
    echo 1>&2
done
