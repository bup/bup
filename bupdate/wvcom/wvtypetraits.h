/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2004 Net Integration Technologies, Inc.
 *
 * Contains code you'd rather not think about.
 */
#ifndef __WVTYPETRAITS_H
#define __WVTYPETRAITS_H

class IObject;

template<class T, bool b>
struct WvTraits_Helper
{
    static inline void maybe_addref(T* obj)
    {
    }
    static inline void release(T* obj)
    {
	delete obj;
    }
};


template<class T>
struct WvTraits_Helper<T, true>
{
    static inline void maybe_addref(T* obj)
    {
	obj->addRef();
    }
    static inline void release(T* obj)
    {
	if (obj)
	    obj->release();
    }
};


template<class From>
class WvTraits
{
    typedef char Yes;
    struct No { char dummy[2]; };
    static From* from;
    static Yes test(IObject*);
    static No test(...);
public:
    static inline void maybe_addref(From* obj)
    {
	const bool is_iobject = (sizeof(test(from)) == sizeof(Yes));
	WvTraits_Helper<From, is_iobject>::maybe_addref(obj);
    }
    static inline void release(From* obj)
    {
	const bool is_iobject = (sizeof(test(from)) == sizeof(Yes));
	WvTraits_Helper<From, is_iobject>::release(obj);
    }
};

#endif /* __WVTYPETRAITS_H */
