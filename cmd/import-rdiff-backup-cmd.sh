#!/bin/sh

set -e

usage() {
    echo "Usage: bup import-rdiff-backup [-n]" \
        "<path to rdiff-backup root> <backup name>"
    echo "-n,--dry-run: just print what would be done"
    exit 1
}

dry_run=
while [ "$1" = "-n" -o "$1" = "--dry-run" ]; do
    dry_run=echo
    shift
done

bup()
{
    $dry_run "${BUP_MAIN_EXE:=bup}" "$@"
}

snapshot_root=$1
branch=$2

[ -n "$snapshot_root" -a "$#" = 2 ] || usage

if [ ! -e "$snapshot_root/." ]; then
    echo "'$snapshot_root' isn't a directory!"
    exit 1
fi


rdiff-backup --list-increments --parsable-output "$snapshot_root" |
while read timestamp type; do
    tmpdir=$(mktemp -d)

    rdiff-backup -r $timestamp "$snapshot_root" "$tmpdir"

    tmpidx=$(mktemp -u)
    bup index -ux -f "$tmpidx" "$tmpdir"
    bup save --strip --date="$timestamp" -f "$tmpidx" -n "$branch" "$tmpdir"
    rm -f "$tmpidx"

    rm -rf "$tmpdir"
done
