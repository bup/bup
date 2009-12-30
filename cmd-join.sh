#!/bin/sh
while read x junk; do
    git cat-file -p "$x"
done
