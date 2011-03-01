/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * Directory iterator.  Recursively uses opendir and readdir, so you don't
 * have to.  Basically implements 'find'.
 *
 */

#ifndef __WVDIRITER_H
#define __WVDIRITER_H

#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>

#include "wvstring.h"
#include "wvlinklist.h"
#include "wvstrutils.h"

struct WvDirEnt : public stat
/***************************/
{
    // we already have everything from struct stat, but let's also include
    // some variations on the filename for convenience.
    WvString        fullname; // contains: startdir/path/file
    WvString        name;     // contains: file
    WvString        relname;  // contains: path/file
};

class WvDirIter
/*************/
{
private:
    bool        recurse;
    bool        go_up;
    bool        skip_mounts;
    bool        found_top;

    WvDirEnt        topdir;
    WvDirEnt        info;
    WvString        relpath;

    struct Dir {
        Dir( DIR * _d, WvString _dirname )
            : d( _d ), dirname( _dirname )
            {}
        ~Dir()
            { if( d ) closedir( d ); }

        DIR *    d;
        WvString dirname;
    };

    DeclareWvList( Dir );
    DirList       dirs;
    DirList::Iter dir;
    
public:
    // the sizeof(stat) helps an assert() in wvdiriter.cc.
    WvDirIter( WvStringParm dirname,
	       bool _recurse = true, bool _skip_mounts = false,
	       size_t sizeof_stat = sizeof(struct stat) );
    
    ~WvDirIter();

    bool isok() const;
    bool isdir() const;
    void rewind();
    bool next();

    // calling up() will abandon the current level of recursion, if, for
    // example, you decide you don't want to continue reading the contents
    // of the directory you're in.  After up(), next() will return the next
    // entry after the directory you've abandoned, in its parent.
    void up()
        { go_up = true; }
    
    const WvDirEnt *ptr() const { return &info; }
    WvIterStuff(const WvDirEnt);
    
    int depth() const
        { return( dirs.count() ); }
};

#endif
