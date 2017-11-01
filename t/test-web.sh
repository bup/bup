#!/usr/bin/env bash
. wvtest-bup.sh || exit $?
. t/lib.sh || exit $?

set -o pipefail

TOP="$(WVPASS pwd)" || exit $?
tmpdir="$(WVPASS wvmktempdir)" || exit $?
export BUP_DIR="$tmpdir/bup"

bup()
{
    "$TOP/bup" "$@"
}

wait-for-server-start()
{
    curl --unix-socket ./socket http://localhost/
    curl_status=$?
    while test $curl_status -eq 7; do
        sleep 0.2
        curl --unix-socket ./socket http://localhost/
        curl_status=$?
    done
    WVPASSEQ $curl_status 0
}

WVPASS cd "$tmpdir"

# FIXME: add WVSKIP
run_test=true

if test -z "$(type -p curl)"; then
    WVSTART 'curl does not appear to be installed; skipping  test'
    run_test=''
fi
    
WVPASS bup-python -c "import socket as s; s.socket(s.AF_UNIX).bind('socket')"
curl -s --unix-socket ./socket http://localhost/foo
if test $? -ne 7; then
    WVSTART 'curl does not appear to support --unix-socket; skipping test'
    run_test=''
fi

if ! bup-python -c 'import tornado' 2> /dev/null; then
    WVSTART 'unable to import tornado; skipping test'
    run_test=''
fi

if test -n "$run_test"; then
    WVSTART 'web'
    WVPASS bup init
    WVPASS mkdir src
    WVPASS echo '¡excitement!' > src/data
    WVPASS bup index src
    WVPASS bup save -n '¡excitement!' --strip src

    "$TOP/bup" web unix://socket &
    web_pid=$!
    wait-for-server-start

    WVPASS curl --unix-socket ./socket \
           'http://localhost/%C2%A1excitement%21/latest/data' > result

    WVPASSEQ '¡excitement!' "$(cat result)"
    WVPASS kill -s TERM "$web_pid"
    WVPASS wait "$web_pid"
fi

WVPASS rm -r "$tmpdir"
