exec >&2
rm -f fidx http-win http-curl bupdate *.exe
find . \( -name '*.[oa]' -o -name '*~' \) -exec rm -f {} \;
