#!/bin/sh
# Does an import of a rsnapshot archive.

cmd_dir="$(cd "$(dirname "$0")" && pwd)" || exit $?

usage() {
    echo "Usage: bup import-rsnapshot [-n]" \
        "<path to snapshot_root> [<backuptarget>]"
    echo "-n,--dry-run: just print what would be done"
    exit 1
}

DRY_RUN=
while [ "$1" = "-n" -o "$1" = "--dry-run" ]; do
    DRY_RUN=echo
    shift
done

bup()
{
    $DRY_RUN "$cmd_dir/bup" "$@"
}

SNAPSHOT_ROOT=$1
TARGET=$2

[ -n "$SNAPSHOT_ROOT" -a "$#" -le 2 ] || usage

if [ ! -e "$SNAPSHOT_ROOT/." ]; then
    echo "'$SNAPSHOT_ROOT' isn't a directory!"
    exit 1
fi


cd "$SNAPSHOT_ROOT" || exit 2

for SNAPSHOT in *; do
    [ -e "$SNAPSHOT/." ] || continue
    echo "snapshot='$SNAPSHOT'" >&2
    for BRANCH_PATH in "$SNAPSHOT/"*; do
        BRANCH=$(basename "$BRANCH_PATH") || exit $?
        [ -e "$BRANCH_PATH/." ] || continue
        [ -z "$TARGET" -o "$TARGET" = "$BRANCH" ] || continue
        
        echo "snapshot='$SNAPSHOT' branch='$BRANCH'" >&2

        # Get the snapshot's ctime
        DATE=$(perl -e '@a=stat($ARGV[0]) or die "$ARGV[0]: $!";
                        print $a[10];' "$BRANCH_PATH")
	[ -n "$DATE" ] || exit 3

        TMPIDX=bupindex.$BRANCH.tmp
        bup index -ux -f "$TMPIDX" "$BRANCH_PATH/" || exit $?
        bup save --strip --date="$DATE" \
            -f "$TMPIDX" -n "$BRANCH" \
            "$BRANCH_PATH/" || exit $?
        rm "$TMPIDX" || exit $?
    done
done
