/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * A linked list container.
 */
#ifndef __WVLINKLIST_H
#define __WVLINKLIST_H

#include "wvtypetraits.h"
#include "wvlink.h"

/**
 * @internal
 * The untyped base class of WvList<T>.
 * 
 * Putting common code in here allows us to prevent it from being
 * replicated by each template instantiation of WvList<T>.
 * 
 */
class WvListBase
{
    WvListBase(const WvListBase &l); // copy constructor - not actually defined anywhere!
private:
    //This is private to force people to pass by reference, not by value
    WvListBase& operator= (const WvListBase &l);
    
public:
    WvLink head, *tail;

    /** Creates an empty linked list. */
    WvListBase() : head(NULL, false)
        { tail = &head; }

    /**
     * Returns the number of elements in the list.
     * 
     * This function causes a full traversal of the list which may be
     * overly inefficient depending on how and when it is used.
     * 
     * Returns: the number of elements
     */
    size_t count() const;

    /**
     * Reverses the order of elements in the list.
     *
     * This function traverses the list and rearranges the pointers
     * and updates the pointers to head & tail appropriately.
     *
     * It does nothing for lists of count<2
     */
    void reverse();

    /**
     * Quickly determines if the list is empty.
     * 
     * This is much faster than checking count() == 0.
     * 
     * Returns: true if empty
     */
    bool isempty() const
        { return head.next == NULL; }

    /**
     * @internal
     * The untyped base class of WvList<T>::Iter.
     * 
     * Putting common code in here allows us to prevent it from being
     * replicated by each template instantiation of WvList<T>.
     * 
     */
    class IterBase
    {
    public:
	const WvListBase *list;
	WvLink *link, *prev;

        /**
         * Binds the iterator to the specified list.
         * "l" is the list
         */
	IterBase(const WvListBase &l)
            { list = &l; link = NULL; }

        /**
         * Rewinds the iterator to make it point to an imaginary element
         * preceeding the first element of the list.
         */
	void rewind() // dropping a const pointer here!  Danger!
            { prev = NULL; link = &((WvListBase *)list)->head; }

	
        /**
         * Moves the iterator along the list to point to the next element.
         * 
         * If the iterator had just been rewound, it now points to the
         * first element of the list.
         * 
         * Returns: the current WvLink pointer, or null if there were no
         *         more elements remaining in the traversal sequence
         */
	WvLink *next()
            { prev = link; return link = link->next; }

        /**
         * Returns a pointer to the WvLink at the iterator's current location.
         * Returns: the current WvLink pointer, or null if there were no
         *         more elements remaining in the traversal sequence
         */
	WvLink *cur() const
            { return link; }
	
	/**
	 * Returns a void pointer to the object at the iterator's current
	 * location.  You should almost never need this.  Use ptr() instead.
	 */
	void *vptr() const
	    { return link->data; }

        /**
         * Rewinds the iterator and repositions it over the element that
         * matches the specified value.
         *
         * Uses pointer equality (object identity) as the criteria for
         * finding the matching element.
         *
         * In order to locate multiple matching elements, first call find()
         * and then use find_next().
         *
         * Returns: the current WvLink pointer, or null if no such element
         *          was found
         */
	WvLink *find(const void *data);

        /**
         * Repositions the iterator over the element that matches the
         * specified value.
         *
         * Uses pointer equality (object identity) as the criteria for
         * finding the matching element.
         *
         * Returns: the current WvLink pointer, or null if no such element
         *          was found
         */
	WvLink *find_next(const void*data);
    };
};


/**
 * A linked list container class.
 * 
 * Some rather horrible macros are used to declare actual concrete
 * list types.
 * 
 * Example:
 * 
 *   DeclareWvList(WvString);
 *
 *   int main()
 *   {
 *       WvStringList l;
 *       WvStringList::Iter i(l);
 *
 *       ... fill the list ...
 *
 *       i.rewind();
 *       while (i.next())
 *           printf("%s\\n", i.str);
 *   }
 * 
 * 
 * Deallocating list will free all of the WvLinks in the list, but
 * will only free the user objects that were added with autofree
 * set to true.
 * 
 * We need to malloc memory for each WvLink as well as the data it
 * stores; this is unnecessarily slow.  I would rather have made a
 * base "Link" class for object types that could be stored as links
 * in a list, and then used object->next instead of all the
 * List Iterator stuff, but the end result was pure ugliness, so I
 * gave up.  At least this way, the same object can be in multiple
 * lists.
 * 
 * List type construction is facilitated by the following macros:
 * 
 *  - DeclareWvList(Type): creates a subclass named TypeList
 *     that contains pointers to Type.
 *  - DeclareWvList2(name, Type): as the above, but calls the
 *     resulting class by the specified name. 
 * 
 * 
 * "T" is the object type
 */
template<class T>
class WvList : public WvListBase
{
    // copy constructor: not defined anywhere!
    WvList(const WvList &list);

public:
    /** Creates an empty linked list. */
    WvList()
	{ }
    
    /**
     * Destroys the linked list.
     * 
     * Destroys any elements that were added with autofree == true.
     * 
     */
    ~WvList()
	{ zap(); }
	
    /** Invoked by subclasses after the linked list is first created. */
    void setup() {}
    
    /** Invoked by subclasses before the linked list is destroyed. */
    void shutdown() {}

    /**
     * Clears the linked list.
     * 
     * If destroy is true, destroys any elements that were added with autofree == true.
     * 
     */
    void zap(bool destroy = true)
    {
        while (head.next)
            unlink_after(& head, destroy);
    }

    /**
     * Returns a pointer to the first element in the linked list.
     * 
     * The list must be non-empty.
     * 
     * Returns: the element pointer, possibly null
     */
    T *first() const
        { return (T*)head.next->data; }

    /**
     * Returns a pointer to the last element in the linked list.
     * 
     * The list must be non-empty.
     * 
     * Returns: the element pointer, possibly null
     */
    T *last() const
        { return (T*)tail->data; }

    /**
     * Adds the element after the specified link in the list.
     *
     * "link" is the link preceeding the desired location of the element
     *             to be inserted, non-null
     * "data" is the element pointer, may be null
     * "autofree" is if true, takes ownership of the element
     * "id" is an optional string to associate with the element, or null
     */
    void add_after(WvLink *after, T *data, bool autofree,
			const char *id = NULL )
    {
	(void)new WvLink((void *)data, after, tail, autofree, id);
    }

    /**
     * Appends the element to the end of the list.
     *
     * "data" is the element pointer, may be null
     * "autofree" is if true, takes ownership of the element
     * "id" is an optional string to associate with the element, or null
     */
    void append(T *data, bool autofree, const char *id = NULL)
	{ add_after(tail, data, autofree, id); }

    /**
     * Synonym for append(T*, bool, char*).
     * @see append(T*, bool, char*)
     */
    void add(T *data, bool autofree, const char *id = NULL)
        { append(data, autofree, id); }

    /**
     * Prepends the element to the beginning of the list.
     *
     * "data" is the element pointer, may be null
     * "autofree" is if true, takes ownership of the element
     * "id" is an optional string to associate with the element, or null
     */
    void prepend(T *data, bool autofree, const char *id = NULL)
	{ add_after(&head, data, autofree, id); }

    /**
     * Unlinks the specified element from the list.
     * 
     * Destroys the element if it was added with autofree == true.
     * 
     * "data" is the element pointer, may be null
     */
    void unlink(T *data)
        { Iter i(*this); while (i.find(data)) i.unlink(); }

    /**
     * Unlinks the first element from the list.
     * 
     * Destroys the element if it was added with autofree == true.
     * 
     */ 
    void unlink_first()
    { 
        if(head.next != NULL)   
        { Iter i(*this); i.rewind(); i.next(); i.unlink(); }
    }
    /**
     * Unlinks the element that follows the specified link in the list.
     * 
     * Destroys the element if it was added with autofree == true and
     * destroy == true.
     * 
     * "after" is the link preceeding the element to be removed, non-null
     */ 
    void unlink_after(WvLink *after, bool destroy = true)
    {
        WvLink *next = after->next;
        if(next != NULL)
        {
            T *obj = (destroy && next->get_autofree()) ?
            static_cast<T*>(next->data) : NULL;
            if (next == tail) tail = after;
            next->unlink(after);
	    if (obj)
	        WvTraits<T>::release(obj);
        }
    }

    /**
     * The iterator type for linked lists.
     * 
     * An iterator instance does not initially point to any valid
     * elements in a list.  Before using, it must be reset using rewind()
     * which causes it to point to an imaginary element located before
     * the first elements in the list.  Then next() must be invoked
     * to incrementally move the iterator along the list to first element,
     * and then later to the second, third, and subsequent elements.
     * 
     */
    class Iter : public WvListBase::IterBase
    {
    public:
        /**
         * Binds the iterator to the specified list.
         * "l" is the list
         */
        Iter(const WvList &l) : IterBase(l)
            { }

        /**
         * Returns a pointer to the current element.
         * Returns: the element pointer, possibly null
         */
        T *ptr() const
            { return (T *)link->data; }

	WvIterStuff(T);

	/**
	 * Returns the state of autofree for the current element.
	 */
	bool get_autofree() const
	{
	    return link->get_autofree();
	}

	/**
	 * Sets the state of autofree for the current element.
	 */
	void set_autofree(bool autofree)
	{
	    link->set_autofree(autofree);
	}

        /**
         * Unlinks the current element from the list and automatically
         * increments the iterator to point to the next element as if
         * next() had been called.
         */
        void unlink(bool destroy = true)
        {
	    if (prev) ((WvList *)list)->unlink_after(prev, destroy);
	    link = prev->next;
        }
	
        /**
         * Unlinks the current element from the list but unlike unlink()
         * automatically returns the iterator to the previous link in
         * the list such that next() must be called to obtain the
         * next element.
         * 
         * This version allows for writing neater loop structures since
         * an element can be unlinked in mid-traversal while still allowing
         * the iterator to be incremented at the top of the loop as usual.
         * 
         * Calling xunlink() twice in a row is currently unsupported.
         * 
         */
	void xunlink(bool destroy = true)
	{
	    if (prev) ((WvList *)list)->unlink_after(prev, destroy);
	    link = prev;
	}
    };
    
    /** The sorted iterator type for linked lists. */
    //typedef class WvSorter<T, WvListBase, WvListBase::IterBase> Sorter;
};

#define DeclareWvList2(_classname_, _type_)  \
    typedef class WvList<_type_> _classname_ 

#define DeclareWvList(_type_) DeclareWvList2(_type_##List, _type_)


#endif // __WVLINKLIST_H
