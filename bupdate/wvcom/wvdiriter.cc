/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * Directory iterator.  Recursively uses opendir and readdir, so you don't
 * have to.  Basically implements 'find'.
 */
#include "wvdiriter.h"
#include <assert.h>

#if defined(_WIN32) && !defined(S_ISDIR)
#define S_ISDIR(x) (_S_IFDIR | (x))
#endif
#ifdef _WIN32
#define lstat stat
#endif

WvDirIter::WvDirIter( WvStringParm _dirname,
		      bool _recurse, bool _skip_mounts, size_t sizeof_stat )
    : relpath(""), dir(dirs)
/****************************************************************************/
{
    // if this assertion fails, then you probably used different compiler
    // options for the wvstreams library and the calling program.  Check
    // for defines like _FILE_OFFSET_BITS=64 and _LARGEFILE_SOURCE.
    assert(sizeof_stat == sizeof(struct stat));
    
    recurse = _recurse;
    go_up   = false;
    skip_mounts = _skip_mounts;
    found_top = false;

    WvString dirname(_dirname);
    int dl = strlen(dirname);
    if (dl != 0 && dirname[dl-1] == '/')
        dirname.edit()[dl-1] = 0;

    DIR * d = opendir( dirname );
    if( d ) {
        Dir * dd = new Dir( d, dirname );
        dirs.prepend( dd, true );
    }
}

WvDirIter::~WvDirIter()
/*********************/
{
    dirs.zap();
}

bool WvDirIter::isok() const
/**************************/
{
    return( !dirs.isempty() );
}

bool WvDirIter::isdir() const
/***************************/
{
    return( S_ISDIR( info.st_mode ) );
}

void WvDirIter::rewind()
/**********************/
{
    // have to closedir() everything that isn't the one we started with,
    // and rewind that.
    while( dirs.count() > 1 ) {
        dir.rewind();
        dir.next();
        dir.unlink();
    }

    if( isok() ) {
        dir.rewind();
        dir.next();
	rewinddir( dir->d );
    }
}


bool WvDirIter::next()
/********************/
// use readdir... and if that returns a directory, opendir() it and prepend
// it to dirs, so we start reading it until it's done.
{
    struct dirent * dent = NULL;

    if( !isok() )
        return( false );

    bool tryagain;
    do {
        bool ok = false;
        tryagain = false;

        // unrecurse if the user wants to
        if( go_up ) {
            go_up = false;
            if( dirs.count() > 1 ) {
                dir.unlink();
                dir.rewind();
                dir.next();
            } else
                return( false );
        }

        do {
            dent = readdir( dir->d ); 
	    if( dent ) { 
		info.fullname = WvString( "%s/%s", dir->dirname, dent->d_name );
                info.name = dent->d_name;

                if (relpath == "")
                    info.relname = info.name;
                else
                    info.relname = WvString("%s%s", relpath, info.name);

                ok = ( lstat( info.fullname, &info ) == 0
                            && strcmp( dent->d_name, "." )
                            && strcmp( dent->d_name, ".." ) );

                if (ok && !found_top)
                {
                    lstat(info.fullname, &topdir);
                    topdir.fullname = info.fullname;
                    topdir.name = info.name;
                    topdir.relname = info.relname;
                    found_top = true;
                }
            }
        } while( dent && !ok );

        if( dent ) {
            // recurse?
            if( recurse && S_ISDIR( info.st_mode ) &&
                    ( !skip_mounts || info.st_dev == topdir.st_dev) ) {
                DIR * d = opendir( info.fullname );
                if( d ) {
                    relpath = WvString( "%s%s/", relpath, info.name );
                    Dir * dd = new Dir( d, info.fullname );
                    dirs.prepend( dd, true );
                    dir.rewind();
                    dir.next();
                }
            }
        } else {
            // end of directory.  if we recursed, unlink it and go up a 
            // notch.  if this is the top level, DON'T close it, so that
            // the user can ::rewind() again if he wants.
            if( dirs.count() > 1 ) {
                if (dirs.count() == 2)
                    relpath = WvString("");
                else
                    relpath = WvString( "%s/", getdirname(relpath) );

                dir.unlink();
                dir.rewind();
                dir.next();
                tryagain = true;
            }
        }
    } while( tryagain );

    return( dent != NULL );
}

