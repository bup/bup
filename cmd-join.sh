#!/bin/sh
set -e
export GIT_DIR="$BUP_DIR"

get_one()
{
    local typ="$1"
    local sha="$2"
    if [ "$typ" = "tree" -o "$typ" = "commit" ]; then
        git cat-file -p "$x:" | while read nmode ntyp nsha njunk; do
	    get_one $ntyp $nsha
	done
    else
        git cat-file blob "$sha"
    fi
}


get_from_stdin()
{
    while read x junk; do
        [ -z "$x" ] && continue
        typ="$(git cat-file -t "$x")"
        get_one "$typ" "$x"
    done
}


if [ -z "$*" ]; then
    get_from_stdin
else
    for d in "$@"; do
        echo "$d"
    done | get_from_stdin
fi
