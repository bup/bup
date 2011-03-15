exec >&2
rm -f fidx http-win http-curl bupdate *.exe *.dll *.map *.err
find . \( -name '*.[oa]' -o -name '*~' \) -exec rm -f {} \;
