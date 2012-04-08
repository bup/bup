% bup-memtest(1) Bup %BUP_VERSION%
% Avery Pennarun <apenwarr@gmail.com>
% %BUP_DATE%

# NAME

bup-memtest - test bup memory usage statistics

# SYNOPSIS

bup memtest [options...]

# DESCRIPTION

`bup memtest` opens the list of pack indexes in your bup
repository, then searches the list for a series of
nonexistent objects, printing memory usage statistics after
each cycle.

Because of the way Unix systems work, the output will
usually show a large (and unchanging) value in the VmSize
column, because mapping the index files in the first place
takes a certain amount of virtual address space.  However, this
virtual memory usage is entirely virtual; it doesn't take
any of your RAM.  Over time, bup uses *parts* of the
indexes, which need to be loaded from disk, and this is
what causes an increase in the VmRSS column.

# OPTIONS

-n, \--number=*number*
:   set the number of objects to search for during each
    cycle (ie. before printing a line of output)
    
-c, \--cycles=*cycles*
:   set the number of cycles (ie. the number of lines of
    output after the first).  The first line of output is
    always 0 (ie. the baseline before searching for any
    objects).
    
\--ignore-midx
:   ignore any `.midx` files created by `bup midx`.  This
    allows you to compare memory performance with and
    without using midx.
    
\--existing
:   search for existing objects instead of searching for
    random nonexistent ones.  This can greatly affect
    memory usage and performance.  Note that most of the
    time, `bup save` spends most of its time searching for
    nonexistent objects, since existing ones are probably
    in unmodified files that we won't be trying to back up
    anyway.  So the default behaviour reflects real bup
    performance more accurately.  But you might want this
    option anyway just to make sure you haven't made
    searching for existing objects much worse than before.


# EXAMPLE

    $ bup memtest -n300 -c5
    PackIdxList: using 1 index.
                   VmSize      VmRSS     VmData      VmStk 
            0    20824 kB    4528 kB    1980 kB      84 kB 
          300    20828 kB    5828 kB    1984 kB      84 kB 
          600    20828 kB    6844 kB    1984 kB      84 kB 
          900    20828 kB    7836 kB    1984 kB      84 kB 
         1200    20828 kB    8736 kB    1984 kB      84 kB 
         1500    20828 kB    9452 kB    1984 kB      84 kB 

    $ bup memtest -n300 -c5 --ignore-midx
    PackIdxList: using 361 indexes.
                   VmSize      VmRSS     VmData      VmStk 
            0    27444 kB    6552 kB    2516 kB      84 kB 
          300    27448 kB   15832 kB    2520 kB      84 kB 
          600    27448 kB   17220 kB    2520 kB      84 kB 
          900    27448 kB   18012 kB    2520 kB      84 kB 
         1200    27448 kB   18388 kB    2520 kB      84 kB 
         1500    27448 kB   18556 kB    2520 kB      84 kB 

    
# DISCUSSION

When optimizing bup indexing, the first goal is to keep the
VmRSS reasonably low.  However, it might eventually be
necessary to swap in all the indexes, simply because
you're searching for a lot of objects, and this will cause
your RSS to grow as large as VmSize eventually.

The key word here is *eventually*.  As long as VmRSS grows
reasonably slowly, the amount of disk activity caused by
accessing pack indexes is reasonably small.  If it grows
quickly, bup will probably spend most of its time swapping
index data from disk instead of actually running your
backup, so backups will run very slowly.

The purpose of `bup memtest` is to give you an idea of how
fast your memory usage is growing, and to help in
optimizing bup for better memory use.  If you have memory
problems you might be asked to send the output of `bup
memtest` to help diagnose the problems.

Tip: try using `bup midx -a` or `bup midx -f` to see if it
helps reduce your memory usage.

Trivia: index memory usage in bup (or git) is only really a
problem when adding a large number of previously unseen
objects.  This is because for each object, we need to
absolutely confirm that it isn't already in the database,
which requires us to search through *all* the existing pack
indexes to ensure that none of them contain the object in
question.  In the more obvious case of searching for
objects that *do* exist, the objects being searched for are
typically related in some way, which means they probably
all exist in a small number of packfiles, so memory usage
will be constrained to just those packfile indexes.

Since git users typically don't add a lot of files in a
single run, git doesn't really need a program like `bup
midx`.  bup, on the other hand, spends most of its time
backing up files it hasn't seen before, so its memory usage
patterns are different.


# SEE ALSO

`bup-midx`(1)

# BUP

Part of the `bup`(1) suite.
