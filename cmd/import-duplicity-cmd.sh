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

dup_timestamps=$(duplicity collection-status --log-fd=3 \
                 "$duplicity_target_url" 3>&1 1>/dev/null 2>/dev/null |
                 grep "[[:digit:]][[:digit:]]T" |
                 cut -d" " -f 3)
backups_count=$(echo "$dup_timestamp" | wc -l)
counter=1
echo "$dup_timestamps" |
while read dup_timestamp; do
  timestamp=$(python -c "import time,calendar; " \
      "print str(int(calendar.timegm(time.strptime('$dup_timestamp', " \
      "'%Y%m%dT%H%M%SZ'))))")
  echo "Importing backup from $(date --date=@$timestamp +%c) " \
      "($counter / $backups_count)" 1>&2
  echo 1>&2

  tmpdir=$(mktemp -d)

  echo "Restoring from rdiff-backup..." 1>&2
  duplicity restore -t "$dup_timestamp" "$duplicity_target_url" "$tmpdir"
  echo 1>&2

  echo "Importing into bup..." 1>&2
  tmpidx=$(mktemp -u)
  bup index -ux -f "$tmpidx" "$tmpdir"
  bup save --strip --date="$timestamp" -f "$tmpidx" -n "$branch" "$tmpdir"
  rm -f "$tmpidx"

  rm -rf "$tmpdir"
  counter=$((counter+1))
  echo 1>&2
  echo 1>&2
done
