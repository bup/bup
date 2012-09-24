#!/bin/sh

set -e

usage() {
    echo "Usage: bup import-duplicity [-n]" \
        "<duplicity target url> <backup name>"
    echo "-n,--dry-run: just print what would be done"
    exit -1
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

duplicity_target_url=$1
branch=$2

[ -n "$duplicity_target_url" -a "$#" = 2 ] || usage

duplicity collection-status --log-fd=3 \
    "$duplicity_target_url" 3>&1 1>/dev/null 2>/dev/null |
grep "[[:digit:]][[:digit:]]T" |
cut -d" " -f 3 |
while read dup_timestamp; do
  timestamp=$(python -c "import time,calendar; " \
      "print str(int(calendar.timegm(time.strptime('$dup_timestamp', " \
      "'%Y%m%dT%H%M%SZ'))))")
  tmpdir=$(mktemp -d)

  duplicity restore -t "$dup_timestamp" "$duplicity_target_url" "$tmpdir"

  tmpidx=$(mktemp -u)
  bup index -ux -f "$tmpidx" "$tmpdir"
  bup save --strip --date="$timestamp" -f "$tmpidx" -n "$branch" "$tmpdir"
  rm -f "$tmpidx"

  rm -rf "$tmpdir"
done
