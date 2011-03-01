exec >&2
rm -f fidx *.exe
find . \( -name '*.[oa]' -o -name '*~' \) -exec rm -f {} \;
