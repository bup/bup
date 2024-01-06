% bup-prune-older(1) bup %BUP_VERSION% | bup %BUP_VERSION%
% Rob Browning <rlb@defaultvalue.org>
% %BUP_DATE%

# NAME

bup-prune-older - remove older saves

# SYNOPSIS

bup prune-older [options...] <*branch*...>

# DESCRIPTION

`bup prune-older` removes (permanently deletes) all saves except those
preserved by the various keep arguments detailed below.  At least one
keep argument must be specified.  This command is equivalent to a
suitable `bup rm` invocation followed by `bup gc`.

WARNING: This is one of the few bup commands that modifies your
archive in intentionally destructive ways.  Though if an attempt to
`join` or `restore` the data you still care about after a
`prune-older` succeeds, that's a fairly encouraging sign that the
commands worked correctly.  (The `dev/compare-trees` command in the
source tree can be used to help test before/after results.)

# KEEP PERIODS

A `--keep` PERIOD (as required below) must be an integer followed by a
scale, or "forever".  For example, 12y specifies a PERIOD of twelve
years.  Here are the valid scales:

  - s indicates seconds
  - min indicates minutes (60s)
  - h indicates hours (60m)
  - d indicates days (24h)
  - w indicates weeks (7d)
  - m indicates months (31d)
  - y indicates years (366d)
  - forever is infinitely far in the past

As indicated, the PERIODS are computed with respect to the current
time, or the `--wrt` value if specified, and do not respect any
calendar, so `--keep-dailies-for 5d` means a period starting exactly
5 * 24 * 60 * 60 seconds before the starting point.

# OPTIONS

\--keep-all-for PERIOD
:   when no smaller time scale `--keep` option applies, retain all saves
    within the given period.

\--keep-dailies-for PERIOD
:   when no smaller time scale `--keep` option applies, retain the
    newest save for any day within the given period.

\--keep-monthlies-for PERIOD
:   when no smaller time scale `--keep` option applies, retain the
    newest save for any month within the given period.

\--keep-yearlies-for PERIOD
:   when no smaller time scale `--keep` option applies, retain the
    newest save for any year within the given period.

\--wrt UTC_SECONDS
:   when computing a keep period, place the most recent end of the
    range at UTC\_SECONDS, and any saves newer than this will be kept.

\--pretend
:   don't do anything, just list the actions that would be taken to
    standard output, one action per line like this:

        - SAVE
        + SAVE
        ...

\--gc
:   garbage collect the repository after removing the relevant saves.
    This is the default behavior, but it can be avoided with `--no-gc`.

\--gc-threshold N
:   only rewrite a packfile if it's over N percent garbage; otherwise
    leave it alone.  The default threshold is 10%.

-*#*, \--compress *#*
:   set the compression level when rewriting archive data to # (a
    value from 0-9, where 9 is the highest and 0 is no compression).
    The default is 1 (fast, loose compression).

-v, \--verbose
:   increase verbosity (can be specified more than once).

# NOTES

When `--verbose` is specified, the save periods will be summarized to
standard error with lines like this:

    keeping monthlies since 1969-07-20-201800
    keeping all yearlies
    ...

It's possible that the current implementation might not be able to
format the date if, for example, it is far enough back in time.  In
that case, you will see something like this:

    keeping yearlies since -30109891477 seconds before 1969-12-31-180000
    ...

# EXAMPLES

    # Keep all saves for the past month, and any newer monthlies for
    # the past year.  Delete everything else.
    $ bup prune-older --keep-all-for 1m --keep-monthlies-for 1y

    # Keep all saves for the past 6 months and delete everything else,
    # but only on the semester branch.
    $ bup prune-older --keep-all-for 6m semester

# SEE ALSO

`bup-rm`(1), `bup-gc`(1), and `bup-fsck`(1)

# BUP

Part of the `bup`(1) suite.
