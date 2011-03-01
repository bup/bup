/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * WvStrings are used a lot more often than WvStringLists, so the List need
 * not be defined most of the time.  Include this file if you need it.
 *
 */
#ifndef __WVSTRINGLIST_H
#define __WVSTRINGLIST_H

#include "wvstring.h"
#include "wvlinklist.h"

class WvRegex;

DeclareWvList2(WvStringListBase, WvString);

/**
 * This is a WvList of WvStrings, and is a really handy way to parse
 * strings. If you ever find yourself using strtok(3) or strpbrk(3), 
 * or find yourself needing to parse a line of input, WvStringList, 
 * WvStringList::split(), and WvStringList::popstr() are probably what you 
 * want, and avoid all sorts of nasty security bugs caused by doing it any 
 * other way.
 */
class WvStringList : public WvStringListBase
{
    // copy constructor: not defined anywhere!
    WvStringList(const WvStringList &l);
public:
    /**
     * Instatiate a new WvStringList()
     */
    WvStringList() {}
    
    /**
     * concatenates all elements of the list seperating on joinchars
     */
    WvString join(const char *joinchars = " ") const;
    
    /**
     * split s and form a list ignoring splitchars (except at beginning and end)
     * ie. " happy birthday  to  you" split on " " will populate the list with
     * ""
     * "happy"
     * "birthday"
     * "to"
     * "you"
     */
    void split(WvStringParm s, const char *splitchars = " \t\r\n",
	       int limit = 0);
    /**
     * split s and form a list creating null entries when there are multiple 
     * splitchars
     * ie " happy birthday  to  you" split on " " will populate the list with
     *  ""
     *  "happy"
     *  "birthday"
     *  ""
     *  "to"
     *  ""
     *  "you"
     *      
     */
    void splitstrict(WvStringParm s, const char *splitchars = " \t\r\n",
	       int limit = 0);

#ifndef _WIN32
    /**
     * split s and form a list ignoring regex (except at beginning and end)
     * Note that there is no splitstrict for regexes, since the differece is
     * taken care of through the regex (...)+ syntax
     */
    void split(WvStringParm s, const WvRegex &regex, int limit = 0);
#endif
    
    /**
     * populate the list from an array of strings
     */
    void fill(const char * const *array);

    void append(WvStringParm str);
    void append(WVSTRING_FORMAT_DECL)
        { append(WvString(WVSTRING_FORMAT_CALL)); }
    void append(WvString *strp, bool autofree, char *id = NULL);
    
    /**
     * Returns true if 'str' is in the list.
     */
    bool contains(WvStringParm str) const;

    /** 
     * get the first string in the list, or an empty string if the list is empty.
     * Removes the returned string from the list.
     */
    WvString popstr();
};

#endif // __WVSTRINGLIST_H
