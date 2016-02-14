#!/usr/bin/env bash
. ./wvtest-bup.sh || exit $?
. ./t/lib.sh || exit $?

set -o pipefail

top="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?

export BUP_DIR="$tmpdir/bup"
export GIT_DIR="$tmpdir/bup"


bup() { "$top/bup" "$@"; }
compare-trees() { "$top/t/compare-trees" "$@"; }

wv_matches_rx()
{
    caller_file=${BASH_SOURCE[0]}
    caller_line=${BASH_LINENO[0]}
    src="$caller_file:$caller_line"
    if test $# -ne 2; then
        echo "! $src wv_matches_rx requires 2 arguments FAILED" 1>&2
        return
    fi
    str="$1"
    rx="$2"
    (echo "Matching:"
     echo "$str" | sed 's/^\(.*\)/  \1/'
     echo "Against:"
     echo "$rx" | sed 's/^\(.*\)/  \1/') 1>&2
    if [[ "$str" =~ $rx ]]; then
        echo "! $src regex matches ok" 1>&2
    else
        echo "! $src regex doesn't match FAILED" 1>&2
    fi
}


WVPASS bup init
WVPASS cd "$tmpdir"


WVSTART "rm /foo (lone branch)"
WVPASS mkdir src src/foo
WVPASS echo twisty-maze > src/1
WVPASS bup index src
WVPASS bup save -n src src
WVPASS "$top"/t/sync-tree bup/ bup-baseline/
# FIXME: test -n
WVPASS bup tick # Make sure we always get the timestamp changes below
WVPASS bup rm --unsafe /src
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
'\*deleting[ ]+logs/refs/heads/src
\*deleting[ ]+refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+logs/refs/heads/
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/'


WVSTART "rm /foo (one of many)"
WVPASS rm -rf bup
WVPASS mv bup-baseline bup
WVPASS echo twisty-maze > src/2
WVPASS bup index src
WVPASS bup save -n src-2 src
WVPASS echo twisty-maze > src/3
WVPASS bup index src
WVPASS bup save -n src-3 src
WVPASS "$top"/t/sync-tree bup/ bup-baseline/
WVPASS bup tick # Make sure we always get the timestamp changes below
WVPASS bup rm --unsafe /src
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
"\*deleting[ ]+logs/refs/heads/src
\*deleting[ ]+refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+logs/refs/heads/
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/"


WVSTART "rm /foo /bar (multiple of many)"
WVPASS rm -rf bup
WVPASS mv bup-baseline bup
WVPASS echo twisty-maze > src/4
WVPASS bup index src
WVPASS bup save -n src-4 src
WVPASS echo twisty-maze > src/5
WVPASS bup index src
WVPASS bup save -n src-5 src
WVPASS "$top"/t/sync-tree bup/ bup-baseline/
WVPASS bup tick # Make sure we always get the timestamp changes below
WVPASS bup rm --unsafe /src-2 /src-4
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
"\*deleting[ ]+logs/refs/heads/src-4
\*deleting[ ]+logs/refs/heads/src-2
\*deleting[ ]+refs/heads/src-4
\*deleting[ ]+refs/heads/src-2
\.d\.\.t\.\.\.[.]*[ ]+logs/refs/heads/
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/"


WVSTART "rm /foo /bar (all)"
WVPASS rm -rf bup
WVPASS mv bup-baseline bup
WVPASS "$top"/t/sync-tree bup/ bup-baseline/
WVPASS bup tick # Make sure we always get the timestamp changes below
WVPASS bup rm --unsafe /src /src-2 /src-3 /src-4 /src-5
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
"\*deleting[ ]+logs/refs/heads/src-5
\*deleting[ ]+logs/refs/heads/src-4
\*deleting[ ]+logs/refs/heads/src-3
\*deleting[ ]+logs/refs/heads/src-2
\*deleting[ ]+logs/refs/heads/src
\*deleting[ ]+refs/heads/src-5
\*deleting[ ]+refs/heads/src-4
\*deleting[ ]+refs/heads/src-3
\*deleting[ ]+refs/heads/src-2
\*deleting[ ]+refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+logs/refs/heads/
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/"


WVSTART "rm /foo/bar (lone save - equivalent to rm /foo)"
WVPASS rm -rf bup bup-baseline src
WVPASS bup init
WVPASS mkdir src
WVPASS echo twisty-maze > src/1
WVPASS bup index src
WVPASS bup save -n src src
save1="$(WVPASS bup ls src | head -n 1)" || exit $?
WVPASS "$top"/t/sync-tree bup/ bup-baseline/
WVPASS bup tick # Make sure we always get the timestamp changes below
WVFAIL bup rm --unsafe /src/latest
WVPASS bup rm --unsafe /src/"$save1"
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
"\*deleting[ ]+logs/refs/heads/src
\*deleting[ ]+refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+logs/refs/heads/
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/"


verify-changes-caused-by-rewriting-save()
(
    local before="$1"
    local after="$2"
    local tmpdir="$(WVPASS wvmktempdir)" || exit $?
    (WVPASS cd "$before" && WVPASS find . | WVPASS sort) > "$tmpdir/before"
    (WVPASS cd "$after" && WVPASS find . | WVPASS sort) > "$tmpdir/after"
    new_paths="$(WVPASS comm -13 "$tmpdir/before" "$tmpdir/after")" || exit $?
    new_idx="$(echo "$new_paths" | WVPASS grep -E '^\./objects/pack/pack-.*\.idx$' | cut -b 3-)"
    new_pack="$(echo "$new_paths" | WVPASS grep -E '^\./objects/pack/pack-.*\.pack$' | cut -b 3-)"
    wv_matches_rx "$(compare-trees "$after/" "$before/")" \
">fcst\.\.\.[.]*[ ]+logs/refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+objects/
\.d\.\.t\.\.\.[.]*[ ]+objects/pack/
>fcst\.\.\.[.]*[ ]+objects/pack/bup\.bloom
>f\+\+\+\+\+\+\+[+]*[ ]+$new_idx
>f\+\+\+\+\+\+\+[+]*[ ]+$new_pack
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/
>fc\.t\.\.\.[.]*[ ]+refs/heads/src"
    WVPASS rm -rf "$tmpdir"
)

commit-hash-n()
{
    local n="$1" repo="$2" branch="$3"
    GIT_DIR="$repo" WVPASS git rev-list --reverse "$branch" \
        | WVPASS awk "FNR == $n"
}

rm-safe-cinfo()
{
    local n="$1" repo="$2" branch="$3" hash
    hash="$(commit-hash-n "$n" "$repo" "$branch")" || exit $?
    local fmt='Tree: %T%n'
    fmt="${fmt}Author: %an <%ae> %ai%n"
    fmt="${fmt}Committer: %cn <%ce> %ci%n"
    fmt="${fmt}%n%s%n%b"
    GIT_DIR="$repo" WVPASS git log -n1 --pretty=format:"$fmt" "$hash"
}


WVSTART 'rm /foo/BAR (setup)'
WVPASS rm -rf bup bup-baseline src
WVPASS bup init
WVPASS mkdir src
WVPASS echo twisty-maze > src/1
WVPASS bup index src
WVPASS bup save -n src src
WVPASS echo twisty-maze > src/2
WVPASS bup index src
WVPASS bup tick
WVPASS bup save -n src src
WVPASS echo twisty-maze > src/3
WVPASS bup index src
WVPASS bup tick
WVPASS bup save -n src src
WVPASS mv bup bup-baseline
WVPASS bup tick # Make sure we always get the timestamp changes below


WVSTART "rm /foo/BAR (first of many)"
WVPASS "$top"/t/sync-tree bup-baseline/ bup/
victim="$(WVPASS bup ls src | head -n 1)" || exit $?
WVPASS bup rm --unsafe /src/"$victim"
verify-changes-caused-by-rewriting-save bup-baseline bup
WVPASSEQ 2 $(git rev-list src | wc -l)
WVPASSEQ "$(rm-safe-cinfo 1 bup src)" "$(rm-safe-cinfo 2 bup-baseline src)"
WVPASSEQ "$(rm-safe-cinfo 2 bup src)" "$(rm-safe-cinfo 3 bup-baseline src)"


WVSTART "rm /foo/BAR (one of many)"
WVPASS "$top"/t/sync-tree bup-baseline/ bup/
victim="$(WVPASS bup ls src | tail -n +2 | head -n 1)" || exit $?
WVPASS bup rm --unsafe /src/"$victim"
verify-changes-caused-by-rewriting-save bup-baseline bup
WVPASSEQ 2 $(git rev-list src | wc -l)
WVPASSEQ "$(commit-hash-n 1 bup src)" "$(commit-hash-n 1 bup-baseline src)"
WVPASSEQ "$(rm-safe-cinfo 2 bup src)" "$(rm-safe-cinfo 3 bup-baseline src)"


WVSTART "rm /foo/BAR (last of many)"
WVPASS "$top"/t/sync-tree bup-baseline/ bup/
victim="$(WVPASS bup ls src | tail -n 2 | head -n 1)" || exit $?
WVPASS bup rm --unsafe -vv /src/"$victim"
wv_matches_rx "$(compare-trees bup/ bup-baseline/)" \
">fcst\.\.\.[.]*[ ]+logs/refs/heads/src
\.d\.\.t\.\.\.[.]*[ ]+refs/heads/
>fc\.t\.\.\.[.]*[ ]+refs/heads/src"
WVPASSEQ 2 $(git rev-list src | wc -l)
WVPASSEQ "$(commit-hash-n 1 bup src)" "$(commit-hash-n 1 bup-baseline src)"
WVPASSEQ "$(commit-hash-n 2 bup src)" "$(commit-hash-n 2 bup-baseline src)"


# FIXME: test that committer changes when rewriting, when appropriate

WVPASS rm -rf "$tmpdir"
