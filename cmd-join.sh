#!/bin/sh
set -e

get_one()
{
    local typ="$1"
    local sha="$2"
    if [ "$typ" = "tree" ]; then
        git cat-file -p "$x" | while read nmode ntyp nsha njunk; do
	    get_one $ntyp $nsha
	done
    else
        git cat-file blob "$sha"
    fi
}

while read x junk; do
    typ="$(git cat-file -t "$x")"
    get_one "$typ" "$x"
done
