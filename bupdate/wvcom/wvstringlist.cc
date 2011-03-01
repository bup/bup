/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * Some helper functions for WvStringList.
 * 
 * This is blatantly block-copied from WvStringTable, but I don't care!  Hah!
 * (I just know I'm going to regret this someday...)
 */
#include "wvstringlist.h"
#include "wvstrutils.h"


WvString WvStringList::join(const char *joinchars) const
{
    return ::strcoll_join(*this, joinchars);
}

void WvStringList::split(WvStringParm s, const char *splitchars,
    int limit)
{
    return ::strcoll_split(*this, s, splitchars, limit);
}

void WvStringList::splitstrict(WvStringParm s, const char *splitchars,
    int limit)
{
    return ::strcoll_splitstrict(*this, s, splitchars, limit);
}

void WvStringList::fill(const char * const *array)
{
    while (array && *array)
    {
	append(new WvString(*array), true);
	array++;
    }
}


void WvStringList::append(WvStringParm str)
{
    WvStringListBase::append(new WvString(str), true);
}


void WvStringList::append(WvString *strp, bool autofree, char *id)
{
    WvStringListBase::append(strp, autofree, id);
}


bool WvStringList::contains(WvStringParm str) const
{
    WvStringList::Iter i(*this);
    for (i.rewind(); i.next(); )
	if (*i == str)
	    return true;
    return false;
}


// get the first string in the list, or an empty string if the list is empty.
// Removes the returned string from the list.
WvString WvStringList::popstr()
{
    if (isempty())
	return "";
    
    WvString s = *first();
    unlink_first();
    return s;
}


#ifdef HAVE_REGEX
void WvStringList::split(WvStringParm s, const WvRegex &regex, int limit)
{
    return ::strcoll_split(*this, s, regex, limit);
}
#endif
