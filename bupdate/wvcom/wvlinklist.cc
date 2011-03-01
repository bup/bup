/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 * 
 * Implementation of a Linked List management class, or rather, macros that
 * declare arbitrary linked list management classes.
 * 
 * wvlinklist.h does all the real work.
 */
#include "wvlinklist.h"

WvLink::WvLink(void *_data, WvLink *prev, WvLink *&tail, bool _autofree,
	       const char *_id)
{
    data = _data;
    next = prev->next;
    if (!next) tail = this;
    prev->next = this;
    autofree = _autofree;
    id = _id;
}


size_t WvListBase::count() const
{
    WvLink *l;
    size_t n = 0;
    
    for (l = head.next; l; l = l->next)
	n++;
    return n;
}


void WvListBase::reverse()
{
    WvLink *prev, *curr, *next;

    if (!head.next || !head.next->next)
        return;
    
    prev = head.next;
    curr = prev->next; 
   
    do {
        next = curr->next;
	curr->next = prev;
	prev = curr;
	curr = next;
    } while(curr);
    
    tail = head.next;
    tail->next = NULL;
    head.next = prev;
}


WvLink *WvListBase::IterBase::find(const void *data)
{
    for (rewind(); next(); )
	if (link->data == data)
	    break;
    return link;
}

WvLink *WvListBase::IterBase::find_next(const void *data)
{
    if (link)
    {
	if (link->data == data)
	    return link;

	for (rewind(); next(); )
	    if (link->data == data)
		break;
    }
    return link;
}


#if 0
static WvListBase::SorterBase::CompareFunc *actual_compare = NULL;

static int magic_compare(const void *_a, const void *_b)
{
    WvLink *a = *(WvLink **)_a, *b = *(WvLink **)_b;
    return actual_compare(a->data, b->data);
}

void WvListBase::SorterBase::rewind(CompareFunc *cmp)
{
    if (array)
        delete array;
    array = lptr = NULL;

    int n = list->count();
    array = new WvLink * [n+1];
    WvLink **aptr = array;

    // fill the array with data pointers for sorting, so that the user doesn't
    // have to deal with the WvLink objects.  Put the WvLink pointers back 
    // in after sorting.
    IterBase i(*list);
    aptr = array;
    for (i.rewind(); i.next(); )
    {
        *aptr = i.cur();
        aptr++;
    }
    
    *aptr = NULL;

    // sort the array.  "Very nearly re-entrant" (unless the compare function
    // ends up being called recursively or something really weird...)
    CompareFunc *old_compare = actual_compare;
    actual_compare = cmp;
    qsort(array, n, sizeof(WvLink *), magic_compare);
    actual_compare = old_compare;

    lptr = NULL;    // subsequent next() will set it to first element.
}
#endif
