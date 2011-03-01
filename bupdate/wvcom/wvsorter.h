/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * An iterator that can sort anything that has an iterator, includes the
 * right member functions, and uses WvLink objects - at the moment,
 * this includes WvList- and WvHashTable-based objects.
 */
#ifndef __WVSORTER_H
#define __WVSORTER_H

#include "wvxplc.h"
#include "wvlink.h"

// the base class for sorted list iterators.
// It is similar to IterBase, except for rewind(), next(), and cur().
// The sorting is done in rewind(), which makes an array of WvLink
// pointers and calls qsort.  "lptr" is a pointer to the current WvLink *
// in the array, and next() increments to the next one.
// NOTE: we do not keep "prev" because it makes no sense to do so.
//       I guess Sorter::unlink() will be slow... <sigh>
//       ...so we didn't implement it.
class WvSorterBase
{
public:
    typedef int (CompareFunc)(const void *a, const void *b);
    
    void *list;
    void **array;
    void **lptr;
    
    WvSorterBase(void *_list)
    	{ list = _list; array = lptr = NULL; }
    ~WvSorterBase()
    	{ if (array) deletev array; }
    bool next()
	{ return *(++lptr) != 0; }
    bool cur()
    	{ return *lptr != 0; }
    
protected:
    template <class _list_,class _iter_> void rewind(CompareFunc *cmp);
    
    static int magic_compare(const void *_a, const void *_b);
    static CompareFunc *actual_compare;
};

// the actual type-specific sorter.  Set _list_ and _iter_ to be your
// common base class (eg. WvListBase and WvListBase::IterBase) if possible,
// so we don't need to generate a specific rewind(cmp) function for each
// specific type of list.  Since rewind(cmp) is the only non-inline function
// in a sorter, that means you only need one of them per top-level container
// type (ie. one for WvList and one for HashTable), not one per data type
// you might store in such a container.
template <class _type_,class _list_,class _iter_>
class WvSorter : public WvSorterBase
{
public:
    typedef int (RealCompareFunc)(const _type_ *a, const _type_ *b);
    RealCompareFunc *cmp;
    
    WvSorter(_list_ &_list, RealCompareFunc *_cmp)
	: WvSorterBase(&_list)
	{ cmp = _cmp; }
    _type_ *ptr() const
	{ return (_type_ *)(*lptr); }
    
    // declare standard iterator accessors
    WvIterStuff(_type_);
    
    void rewind()
      { WvSorterBase::rewind<_list_,_iter_>((CompareFunc *)cmp); }
};


// Note that this is largely the same as WvLink::SorterBase::rewind(),
// except we iterate through a bunch of lists instead of a single one.
template <class _list_,class _iter_>
void WvSorterBase::rewind(CompareFunc *cmp)
{
    int n, remaining;
    
    if (array)
        deletev array;
    array = lptr = NULL;

    _iter_ i(*(_list_ *)list);
    
    // count the number of elements
    n = 0;
    for (i.rewind(); i.next(); )
	n++;

    typedef void *VoidPtr;
    array = new VoidPtr[n+2];
    void **aptr = array;

    *aptr++ = NULL; // initial link is NULL, to act like a normal iterator
    
    for (remaining = n, i.rewind(); i.next() && remaining; remaining--)
    {
        *aptr = i.vptr();
        aptr++;
    }
    
    // weird: list length changed?
    // (this can happen with "virtual" lists like ones from WvDirIter)
    if (remaining)
	n -= remaining;
    
    *aptr = NULL;

    // sort the array.  "Very nearly re-entrant" (unless the compare function
    // ends up being called recursively or something really weird...)
    CompareFunc *old_compare = actual_compare;
    actual_compare = cmp;
    qsort(array+1, n, sizeof(void *), magic_compare);
    actual_compare = old_compare;

    lptr = array;
}


#endif // __WVSORTER_H
