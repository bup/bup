/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * WvLink is one element of a linked list.
 * Used by wvlinklist.h.
 */
#ifndef __WVLINK_H
#define __WVLINK_H

#include <stdlib.h>  // for 'NULL'

/**
 * WvLink is one element of a WvList<T>.
 * 
 * Note that WvLink itself is untyped to minimize the amount of
 * generated code.  This means that WvLink cannot handle the
 * autofree behaviour itself which would require static type
 * information.  Instead, it defers this behaviour to the
 * template instantiation of WvList<T> that uses it.
 * 
 */
class WvLink
{
public:
    void *data;
    WvLink *next;
    const char *id;

private:
    bool autofree : 1;

public:
    WvLink(void *_data, bool _autofree, const char *_id = NULL):
	data(_data), next(NULL), id(_id), autofree(_autofree)
    {}

    WvLink(void *_data, WvLink *prev, WvLink *&tail, bool _autofree,
	   const char *_id = NULL);

    bool get_autofree()
    {
	return autofree;
    }

    void set_autofree(bool _autofree)
    {
	autofree = _autofree;
    }

    void unlink(WvLink *prev)
    {
	prev->next = next;
	delete this;
    }
};

#define WvIterStuff(_type_) \
    /*! @brief Returns a reference to the current element. */ \
    _type_ &operator () () const \
        { return *ptr(); } \
    /*! @brief Returns a pointer to the current element. */ \
    _type_ *operator -> () const \
        { return ptr(); } \
    /*! @brief Returns a reference to the current element. */ \
    _type_ &operator* () const \
        { return *ptr(); }

#endif // __WVLINK_H
