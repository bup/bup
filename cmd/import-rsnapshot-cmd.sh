#!/bin/sh
# Does an import of a rsnapshot archive.

usage() {
    echo "Usage: bup import-rsnapshot [-n]" \
        "<path to snapshot_root> [<backuptarget>]"
    echo "-n,--dry-run: just print what would be done"
    exit -1
}

DRY_RUN=
while [ "$1" = "-n" -o "$1" = "--dry-run" ]; do
    DRY_RUN=echo
    shift
done

bup()
{
    $DRY_RUN "${BUP_MAIN_EXE:=bup}" "$@"
}

SNAPSHOT_ROOT=$1
TARGET=$2

[ -n "$SNAPSHOT_ROOT" -a "$#" -le 2 ] || usage

if [ ! -e "$SNAPSHOT_ROOT/." ]; then
    echo "'$SNAPSHOT_ROOT' isn't a directory!"
    exit 1
fi


ABSPATH=$(readlink -f "$SNAPSHOT_ROOT")

for SNAPSHOT in "$ABSPATH/"*; do
    if [ -e "$SNAPSHOT/." ]; then
        for BRANCH_PATH in "$SNAPSHOT/"*; do
            if [ -e "$BRANCH_PATH/." ]; then
                # Get the snapshot's ctime
                DATE=$(stat -c %Z "$BRANCH_PATH")
                BRANCH=$(basename "$BRANCH_PATH")
                TMPIDX=/tmp/$BRANCH

                if [ -z "$TARGET" -o "$TARGET" = "$BRANCH" ]; then
                    bup index -ux \
                        -f "$TMPIDX" \
                        "$BRANCH_PATH/"
                    bup save \
                        --strip \
                        --date=$DATE \
                        -f "$TMPIDX" \
                        -n $BRANCH \
                        "$BRANCH_PATH/"

                    rm -f "$TMPIDX"
                fi
            fi
        done
    fi
done
