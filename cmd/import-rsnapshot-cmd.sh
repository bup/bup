#!/bin/sh
# bup-import-rsnapshot.sh

# Does an import of a rsnapshot archive.

usage() {
    echo "Usage: bup import-rsnapshot [-n]" \
        "<path to snapshot_root> [<backuptarget>]"
    echo "-n,--dry-rung: don't do anything just print out what would be done"
    exit -1
}

if [ "$1" = "-n" -o "$1" = "--dry-run" ]; then
    bup()
    {
        echo bup "$@" >&2
    }
    shift 1
elif [ -n "$BUP_MAIN_EXE" ]; then
    bup()
    {
        "$BUP_MAIN_EXE" "$@"
    }
else
    bup()
    {
        bup "$@"
    }
fi

[ "$#" -eq 1 ] || [ "$#" -eq 2 ] || usage

if [ ! -e "$1/." ]; then
    echo "$1 isn't a directory!"
    exit -1
fi

TARGET=
[ "$#" -eq 2 ] && TARGET="$2"


ABSPATH=`readlink -f "$1"`

for SNAPSHOT in "$ABSPATH/"*; do
    if [ -e "$SNAPSHOT/." ]; then
        for BRANCH_PATH in "$SNAPSHOT/"*; do
            if [ -e "$BRANCH_PATH/." ]; then
                # Get the snapshot's ctime
                DATE=`stat -c %Z "$BRANCH_PATH"`
                BRANCH=`basename "$BRANCH_PATH"`
                TMPIDX="/tmp/$BRANCH"

                if [ "$TARGET" = "" ] || [ "$TARGET" = "$BRANCH" ]; then
                    bup index -ux \
                        -f $TMPIDX \
                        $BRANCH_PATH/
                    bup save \
                        --strip \
                        --date=$DATE \
                        -f $TMPIDX \
                        -n $BRANCH \
                        $BRANCH_PATH/

                    if [ -e "$TMPIDX" ]; then
                        rm "$TMPIDX"
                    fi
                fi
            fi
        done
    fi
done

