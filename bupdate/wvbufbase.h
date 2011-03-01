/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * A generic buffering API.
 * Please declare specializations in a separate header file,
 * See "wvbuf.h".
 */
#ifndef __WVBUFFERBASE_H
#define __WVBUFFERBASE_H

#include "wvbufstore.h"

template<class T>
class WvBufBase;

/**
 * An abstract generic buffer template.
 * Buffers are simple data queues designed to ease the construction of
 * functions that must generate, consume, or transform large amount of
 * data in pipeline fashion.  Concrete buffer subclases define the actual
 * storage mechanism and queuing machinery.  In addition they may provide
 * additional functionality for accomplishing particular tasks.
 *
 * The base component is split into two parts, WvBufBaseCommonImpl
 * that defines the common API for all buffer types, and WvBufBase
 * that allows specializations to be defined to add functionality
 * to the base type.  When passing around buffer objects, you should
 * use the WvBufBase<T> type rather than WvBufBaseCommonImpl<T>.
 *
 * See WvBufBase<T>
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvBufBaseCommonImpl
{
protected:
    typedef T Elem;
    typedef WvBufBase<T> Buffer;

    WvBufStore *store;
    
    // discourage copying
    explicit WvBufBaseCommonImpl(
        const WvBufBaseCommonImpl &other) { }

protected:
    /**
     * Initializes the buffer.
     * 
     * Note: Does not take ownership of the storage object.
     * 
     *
     * "store" is the low-level storage object
     */
    explicit WvBufBaseCommonImpl(WvBufStore *store) :
        store(store) { }

public:
    /** Destroys the buffer. */
    virtual ~WvBufBaseCommonImpl() { }

    /**
     * Returns a pointer to the underlying storage class object.
     *
     * Returns: the low-level storage class object pointer, non-null
     */
    WvBufStore *getstore()
    {
        return store;
    }

    /*** Buffer Reading ***/

    /**
     * Returns true if the buffer supports reading.
     *
     * Returns: true if reading is supported
     */
    bool isreadable() const
    {
        return store->isreadable();
    }
    
    /**
     * Returns the number of elements in the buffer currently
     * available for reading.
     * 
     * This function could also be called gettable().
     */
    size_t used() const
    {
        return store->used() / sizeof(Elem);
    }

    /**
     * Reads exactly the specified number of elements and returns
     * a pointer to a storage location owned by the buffer.
     * 
     * The pointer is only valid until the next non-const buffer
     * member is called. eg. alloc(size_t)
     * 
     * If count == 0, a NULL pointer may be returned.
     * 
     * It is an error for count to be greater than the number of
     * available elements in the buffer.
     * 
     * For maximum efficiency, call this function multiple times
     * with count no greater than optgettable() each time.
     * 
     * After this operation, at least count elements may be ungotten.
     */
    const T *get(size_t count)
    {
	if (count > used())
	    return NULL;

        return static_cast<const T*>(
            store->get(count * sizeof(Elem)));
    }

    /**
     * Skips exactly the specified number of elements.
     * 
     * This is equivalent to invoking get(size_t) with the count
     * and discarding the result, but may be faster for certain
     * types of buffers.  As with get(size_t), the call may be
     * followed up by an unget(size_t). 
     * 
     * It is an error for count to be greater than the number of
     * available elements in the buffer.
     * 
     * "count" is the number of elements
     */
    void skip(size_t count)
    {
        store->skip(count * sizeof(Elem));
    }

    /**
     * Returns the optimal maximum number of elements in the
     * buffer currently available for reading without incurring
     * significant overhead.
     * 
     * Invariants:
     * 
     *  - optgettable() <= used()
     *  - optgettable() != 0 if used() != 0
     * 
     *
     * Returns: the number of elements
     */
    size_t optgettable() const
    {
        size_t avail = store->optgettable();
        size_t elems = avail / sizeof(Elem);
        if (elems != 0) return elems;
        return avail != 0 && store->used() >= sizeof(Elem) ? 1 : 0;
    }

    /**
     * Ungets exactly the specified number of elements by returning
     * them to the buffer for subsequent reads.
     * 
     * This operation may always be safely performed with count
     * less than or equal to that specified in the last get(size_t)
     * if no non-const buffer members have been called since then.
     * 
     * If count == 0, nothing happens.
     * 
     * It is an error for count to be greater than ungettable().
     * 
     *
     * "count" is the number of elements
     */
    void unget(size_t count)
    {
        store->unget(count * sizeof(Elem));
    }

    /**
     * Returns the maximum number of elements that may be ungotten
     * at this time.
     *
     * Returns: the number of elements
     */
    size_t ungettable() const
    {
        return store->ungettable() / sizeof(Elem);
    }

    /**
     * Returns a const pointer into the buffer at the specified
     * offset to the specified number of elements without actually
     * adjusting the current get() index.
     * 
     * The pointer is only valid until the next non-const buffer
     * member is called. eg. alloc(size_t)
     * 
     * If count == 0, a NULL pointer may be returned.
     * 
     * If offset is greater than zero, then elements will be returned
     * beginning with the with the offset'th element that would be
     * returned by get(size_t).
     * 
     * If offset equals zero, then elements will be returned beginning
     * with the next one available for get(size_t).
     * 
     * If offset is less than zero, then elements will be returned
     * beginning with the first one that would be returned on a
     * get(size_t) following an unget(-offset).
     * 
     * It is an error for count to be greater than peekable(offset).
     * 
     * For maximum efficiency, call this function multiple times
     * with count no greater than that returned by optpeekable(size_t)
     * at incremental offsets.
     * 
     *
     * "offset" is the buffer offset
     * "count" is the number of elements
     * Returns: the element storage pointer
     */
    const T *peek(int offset, size_t count)
    {
        return static_cast<const T*>(store->peek(
            offset * sizeof(Elem), count * sizeof(Elem)));
    }

    size_t peekable(int offset)
    {
        return store->peekable(offset * sizeof(Elem)) / sizeof(Elem);
    }

    size_t optpeekable(int offset)
    {
        offset *= sizeof(Elem);
        size_t avail = store->optpeekable(offset);
        size_t elems = avail / sizeof(Elem);
        if (elems != 0) return elems;
        return avail != 0 &&
            store->peekable(offset) >= sizeof(Elem) ? 1 : 0;
    }

    /**
     * Clears the buffer.
     * 
     * For many types of buffers, calling zap() will increased the
     * amount of free space available for writing (see below) by
     * an amount greater than used().  Hence it is wise to zap()
     * a buffer just before writing to it to maximize free space.
     * 
     * After this operation, used() == 0, and often ungettable() == 0.
     * 
     */
    void zap()
    {
        store->zap();
    }

    /**
     * Reads the next element from the buffer.
     * 
     * It is an error to invoke this method if used() == 0.
     * 
     * After this operation, at least 1 element may be ungotten.
     * 
     *
     * Returns: the element
     */
    T get()
    {
        return *get(1);
    }

    /**
     * Returns the element at the specified offset in the buffer.
     * 
     * It is an error to invoke this method if used() == 0.
     * 
     *
     * "offset" is the offset, default 0
     * Returns: the element
     */
    T peek(int offset = 0)
    {
        return *peek(offset * sizeof(Elem), sizeof(Elem));
    }

    /**
     * Efficiently copies the specified number of elements from the
     * buffer to the specified UNINITIALIZED storage location
     * and removes the elements from the buffer.
     * 
     * It is an error for count to be greater than used().
     * 
     * For maximum efficiency, choose as large a count as possible.
     * 
     * The pointer buf may be NULL only if count == 0.
     * 
     * After this operation, an indeterminate number of elements
     * may be ungotten.
     * 
     *
     * "buf" is the buffer that will receive the elements
     * "count" is the number of elements
     */
    void move(T *buf, size_t count)
    {
        store->move(buf, count * sizeof(Elem));
    }
    
    /**
     * Efficiently copies the specified number of elements from the
     * buffer to the specified UNINITIALIZED storage location
     * but does not remove the elements from the buffer.
     * 
     * It is an error for count to be greater than peekable(offset).
     * 
     * For maximum efficiency, choose as large a count as possible.
     * 
     * The pointer buf may be NULL only if count == 0.
     * 
     *
     * "buf" is the buffer that will receive the elements
     * "offset" is the buffer offset
     * "count" is the number of elements
     */
    void copy(T *buf, int offset, size_t count)
    {
        store->copy(buf, offset * sizeof(Elem), count * sizeof(Elem));
    }
    
    /*** Buffer Writing ***/
    
    /**
     * Returns true if the buffer supports writing.
     *
     * Returns: true if writing is supported
     */
    bool iswritable() const
    {
        return true;
    }
    
    /**
     * Returns the number of elements that the buffer can currently
     * accept for writing.
     * 
     * Returns: the number of elements
     */
    size_t free() const
    {
        return store->free() / sizeof(Elem);
    }
    
    /**
     * Allocates exactly the specified number of elements and returns
     * a pointer to an UNINITIALIZED storage location owned by the
     * buffer.
     * 
     * The pointer is only valid until the next non-const buffer
     * member is called. eg. alloc(size_t)
     * 
     * If count == 0, a NULL pointer may be returned.
     * 
     * It is an error for count to be greater than free().
     * 
     * For best results, call this function multiple times with
     * count no greater than optallocable() each time.
     * 
     * After this operation, at least count elements may be unallocated.
     * 
     *
     * "count" is the number of elements
     * Returns: the element storage pointer
     */
    T *alloc(size_t count)
    {
        return static_cast<T*>(store->alloc(count * sizeof(Elem)));
    }
    
    /**
     * Returns the optimal maximum number of elements that the
     * buffer can currently accept for writing without incurring
     * significant overhead.
     * 
     * Invariants:
     * 
     *  - optallocable() <= free()
     *  - optallocable() != 0 if free() != 0
     * 
     *
     * Returns: the number of elements
     */
    size_t optallocable() const
    {
        size_t avail = store->optallocable();
        size_t elems = avail / sizeof(Elem);
        if (elems != 0) return elems;
        return avail != 0 && store->free() >= sizeof(Elem) ? 1 : 0;
    }

    /**
     * Unallocates exactly the specified number of elements by removing
     * them from the buffer and releasing their storage.
     * 
     * This operation may always be safely performed with count
     * less than or equal to that specified in the last alloc(size_t)
     * or put(const T*, size_t) if no non-const buffer members have
     * been called since then.
     * 
     * If count == 0, nothing happens.
     * 
     * It is an error for count to be greater than unallocable().
     * 
     *
     * "count" is the number of elements
     */
    void unalloc(size_t count)
    {
        return store->unalloc(count * sizeof(Elem));
    }

    /**
     * Returns the maximum number of elements that may be unallocated
     * at this time.
     * 
     * For all practical purposes, this number will always be at least
     * as large as the amount currently in use.  It is provided
     * primarily for symmetry, but also to handle cases where
     * buffer reading (hence used()) is not supported by the
     * implementation.
     * 
     * Invariants:
     * 
     *  - unallocable() >= used()
     * 
     *
     * Returns: the number of elements
     */
    size_t unallocable() const
    {
        return store->unallocable() / sizeof(Elem);
    }
    
    /**
     * Returns a non-const pointer info the buffer at the specified
     * offset to the specified number of elements without actually
     * adjusting the current get() index.
     * 
     * Other than the fact that the returned storage is mutable,
     * operates identically to peek(int, size_t).
     * 
     *
     * "offset" is the buffer offset
     * "count" is the number of elements
     * Returns: the element storage pointer
     */
    T *mutablepeek(int offset, size_t count)
    {
        return static_cast<T*>(store->mutablepeek(
            offset * sizeof(Elem), count * sizeof(Elem)));
    }

    /**
     * Writes the specified number of elements from the specified
     * storage location into the buffer at its tail.
     * 
     * It is an error for count to be greater than free().
     * 
     * For maximum efficiency, choose as large a count as possible.
     * 
     * The pointer buf may be NULL only if count == 0.
     * 
     * After this operation, at least count elements may be unallocated.
     * 
     *
     * "data" is the buffer that contains the elements
     * "count" is the number of elements
     */
    void put(const T *data, size_t count)
    {
        store->put(data, count * sizeof(Elem));
    }

    /**
     * Efficiently copies the specified number of elements from the
     * specified storage location into the buffer at a particular
     * offset.
     * 
     * If offset <= used() and offset + count > used(), the
     * remaining data is simply tacked onto the end of the buffer
     * with put().
     * 
     * It is an error for count to be greater than free() - offset.
     * 
     *
     * "data" is the buffer that contains the elements
     * "count" is the number of elements
     * "offset" is the buffer offset, default 0
     */
    void poke(const T *data, int offset, size_t count)
    {
        store->poke(data, offset * sizeof(Elem), count * sizeof(Elem));
    }

    /**
     * Writes the element into the buffer at its tail.
     * 
     * It is an error to invoke this method if free() == 0.
     * 
     * After this operation, at least 1 element may be unallocated.
     * 
     *
     * "valid" is the element
     */
    void put(T &value)
    {
        store->fastput(& value, sizeof(Elem));
    }

    /**
     * Writes the element into the buffer at the specified offset.
     * 
     * It is an error to invoke this method if free() == 0.
     * 
     * After this operation, at least 1 element may be unallocated.
     * 
     *
     * "value" is the element
     * "offset" is the buffer offset
     */
    void poke(T &value, int offset)
    {
        poke(& value, offset, 1);
    }


    /*** Buffer to Buffer Transfers ***/

    /**
     * Efficiently moves count bytes from the specified buffer into
     * this one.  In some cases, this may be a zero-copy operation.
     * 
     * It is an error for count to be greater than inbuf.used().
     * 
     * For maximum efficiency, choose as large a count as possible.
     * 
     * After this operation, an indeterminate number of elements
     * may be ungotten from inbuf.
     * 
     *
     * "inbuf" is the buffer from which to read
     * "count" is the number of elements
     */
    void merge(Buffer &inbuf, size_t count)
    {
        store->merge(*inbuf.store, count * sizeof(Elem));
    }

    /**
     * Efficiently merges the entire contents of a buffer into this one.
     *
     * "inbuf" is the buffer from which to read
     */
    void merge(Buffer &inbuf)
    {
        merge(inbuf, inbuf.used());
    }
};



/**
 * The generic buffer base type.
 * To specialize buffers to add new functionality, declare a template
 * specialization of this type that derives from WvBufBaseCommonImpl.
 *
 * See WvBufBaseCommonImpl<T>
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvBufBase : public WvBufBaseCommonImpl<T>
{
public:
    explicit WvBufBase(WvBufStore *store) :
        WvBufBaseCommonImpl<T>(store) { }
};



/**
 * A buffer that wraps a pre-allocated array and provides
 * read-write access to its elements.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvInPlaceBufBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvInPlaceBufStore mystore;

public:
    /**
     * Creates a new buffer backed by the supplied array.
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     * "_size" is the size of the array
     * "_autofree" is if true, the array will be freed when discarded
     */
    WvInPlaceBufBase(T *_data, size_t _avail, size_t _size,
        bool _autofree = false) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _data, _avail * sizeof(Elem),
            _size * sizeof(Elem), _autofree) { }

    /**
     * Creates a new empty buffer backed by a new array.
     *
     * "_size" is the size of the array
     */
    explicit WvInPlaceBufBase(size_t _size) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _size * sizeof(Elem)) { }

    /** Creates a new empty buffer with no backing array. */
    WvInPlaceBufBase() :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), NULL, 0, 0, false) { }

    /**
     * Destroys the buffer.
     *
     * Frees the underlying array if autofree().
     *
     */
    virtual ~WvInPlaceBufBase() { }

    /**
     * Returns the underlying array pointer.
     *
     * Returns: the element pointer
     */
    T *ptr() const
    {
        return static_cast<T*>(mystore.ptr());
    }

    /**
     * Returns the total size of the buffer.
     *
     * Returns: the number of elements
     */
    size_t size() const
    {
        return mystore.size() / sizeof(Elem);
    }

    /**
     * Returns the autofree flag.
     *
     * Returns: the autofree flag
     */
    bool get_autofree() const
    {
        return mystore.get_autofree();
    }

    /**
     * Sets or clears the autofree flag.
     *
     * "_autofree" is if true, the array will be freed when discarded
     */
    void set_autofree(bool _autofree)
    {
        mystore.set_autofree(_autofree);
    }

    /**
     * Resets the underlying buffer pointer and properties.
     *
     * If the old and new buffer pointers differ and the old buffer
     * was specified as autofree, the old buffer is destroyed.
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     * "_size" is the size of the array
     * "_autofree" is if true, the array will be freed when discarded
     */
    void reset(T *_data, size_t _avail, size_t _size,
        bool _autofree = false)
    {
        mystore.reset(_data, _avail * sizeof(Elem),
            _size * sizeof(Elem), _autofree);
    }

    /**
     * Sets the amount of available data using the current buffer
     * and resets the read index to the beginning of the buffer.
     *
     * "_avail" is the amount of data available for reading
     */
    void setavail(size_t _avail)
    {
        mystore.setavail(_avail * sizeof(Elem));
    }
};



/**
 * A buffer that wraps a pre-allocated array and provides
 * read-only access to its elements.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvConstInPlaceBufBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvConstInPlaceBufStore mystore;

public:
    /**
     * Creates a new buffer backed by the supplied array.
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     */
    WvConstInPlaceBufBase(const T *_data, size_t _avail) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _data, _avail * sizeof(Elem)) { }

    /** Creates a new empty buffer with no backing array. */
    WvConstInPlaceBufBase() :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), NULL, 0) { }

    /**
     * Destroys the buffer.
     * 
     * Never frees the underlying array.
     * 
     */
    virtual ~WvConstInPlaceBufBase() { }

    /**
     * Returns the underlying array pointer.
     *
     * Returns: the element pointer
     */
    const T *ptr() const
    {
        return static_cast<const T*>(mystore.ptr());
    }

    /**
     * Resets the underlying buffer pointer and properties.
     * 
     * Never frees the old buffer.
     * 
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     */
    void reset(const T *_data, size_t _avail)
    {
        mystore.reset(_data, _avail * sizeof(Elem));
    }

    /**
     * Sets the amount of available data using the current buffer
     * and resets the read index to the beginning of the buffer.
     *
     * "_avail" is the amount of data available for reading
     */
    void setavail(size_t _avail)
    {
        mystore.setavail(_avail * sizeof(Elem));
    }
};



/**
 * A buffer that wraps a pre-allocated array and provides
 * read-write access to its elements using a circular buffering
 * scheme rather than a purely linear one, as used by
 * WvInPlaceBuf.  
 *
 * When there is insufficient contigous free/used space to
 * satisfy a read or write request, the data is automatically
 * reordered in-place to coalesce the free/used spaces into
 * sufficiently large chunks.  The process may also be manually
 * triggered to explicitly renormalize the array and shift its
 * contents to the front.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvCircularBufBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvCircularBufStore mystore;

public:
    /**
     * Creates a new circular buffer backed by the supplied array.
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     *               at the beginning of the buffer
     * "_size" is the size of the array
     * "_autofree" is if true, the array will be freed when discarded
     */
    WvCircularBufBase(T *_data, size_t _avail, size_t _size,
        bool _autofree = false) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _data, _avail * sizeof(Elem),
            _size * sizeof(Elem), _autofree) { }

    /**
     * Creates a new empty circular buffer backed by a new array.
     *
     * "_size" is the size of the array
     */
    explicit WvCircularBufBase(size_t _size) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _size * sizeof(Elem)) { }

    /** Creates a new empty buffer with no backing array. */
    WvCircularBufBase() :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), NULL, 0, 0, false) { }

    /**
     * Destroys the buffer.
     * 
     * Frees the underlying array if autofree().
     * 
     */
    virtual ~WvCircularBufBase() { }

    /**
     * Returns the underlying array pointer.
     *
     * Returns: the element pointer
     */
    T *ptr() const
    {
        return static_cast<T*>(mystore.ptr());
    }

    /**
     * Returns the total size of the buffer.
     *
     * Returns: the number of elements
     */
    size_t size() const
    {
        return mystore.size() / sizeof(Elem);
    }

    /**
     * Returns the autofree flag.
     *
     * Returns: the autofree flag
     */
    bool get_autofree() const
    {
        return mystore.get_autofree();
    }

    /**
     * Sets or clears the autofree flag.
     *
     * "_autofree" is if true, the array will be freed when discarded
     */
    void set_autofree(bool _autofree)
    {
        mystore.set_autofree(_autofree);
    }

    /**
     * Resets the underlying buffer pointer and properties.
     *
     * If the old and new buffer pointers differ and the old buffer
     * was specified as autofree, the old buffer is destroyed.
     *
     * "_data" is the array of data to wrap
     * "_avail" is the amount of data available for reading
     *               at the beginning of the buffer
     * "_size" is the size of the array
     * "_autofree" is if true, the array will be freed when discarded
     */
    void reset(T *_data, size_t _avail, size_t _size,
        bool _autofree = false)
    {
        mystore.reset(_data, _avail * sizeof(Elem),
            _size * sizeof(Elem), _autofree);
    }

    /**
     * Sets the amount of available data using the current buffer
     * and resets the read index to the beginning of the buffer.
     *
     * "_avail" is the amount of data available for reading
     *               at the beginning of the buffer
     */
    void setavail(size_t _avail)
    {
        mystore.setavail(_avail * sizeof(Elem));
    }

    /**
     * Normalizes the arrangement of the data such that the
     * contents of the buffer are stored at the beginning of
     * the array starting with the next element that would be
     * returned by get(size_t).
     * 
     * After invocation, ungettable() may equal 0.
     * 
     */
    void normalize()
    {
        mystore.normalize();
    }
};



/**
 * A buffer that dynamically grows and shrinks based on demand.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvDynBufBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvDynBufStore mystore;
    
public:
    /**
     * Creates a new buffer.
     * 
     * Provides some parameters for tuning response to buffer
     * growth.
     * 
     * "_minalloc" is the minimum number of elements to allocate
     *      at once when creating a new internal buffer segment
     * "_maxalloc" is the maximum number of elements to allocate
     *      at once when creating a new internal buffer segment
     *      before before reverting to a linear growth pattern
     */
    explicit WvDynBufBase(size_t _minalloc = 1024,
        size_t _maxalloc = 1048576) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _minalloc * sizeof(Elem),
            _maxalloc * sizeof(Elem)) { }
};



/**
 * A buffer that is always empty.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvNullBufBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvNullBufStore mystore;

public:
    /** Creates a new buffer. */
    WvNullBufBase() :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem)) { }
};



/**
 * A buffer that acts like a cursor over a portion of another buffer.
 * The underlying buffer's get() position is not affected by
 * reading from this buffer.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvBufCursorBase : public WvBufBase<T>
{
protected:
    typedef T Elem;

    WvBufCursorStore mystore;

public:
    /**
     * Creates a new buffer.
     * 
     * Does not take ownership of the supplied buffer.
     * 
     *
     * "_buf" is a pointer to the buffer to be wrapped
     * "_start" is the buffer offset of the window start position
     * "_length" is the length of the window
     */
    WvBufCursorBase(WvBufBase<T> &_buf, int _start,
        size_t _length) :
        WvBufBase<T>(& mystore),
        mystore(sizeof(Elem), _buf.getstore(),
            _start * sizeof(Elem), _length * sizeof(Elem)) { }
};


/**
 * A buffer that provides a read-write view over another buffer
 * with a different datatype.  Reading and writing through this
 * buffer implicitly performs the equivalent of reinterpret_cast
 * on each element.
 *
 * Most useful for manipulating data backed by a raw memory buffer.
 *
 * "T" is the type of object to store, must be a primitive or a struct
 *        without special initialization, copy, or assignment semantics
 */
template<class T>
class WvBufViewBase : public WvBufBase<T>
{
public:
    /**
     * Creates a new buffer.
     * 
     * Does not take ownership of the supplied buffer.
     * 
     *
     * "_buf" is a pointer to the buffer to be wrapped
     */
    template<typename S>
    WvBufViewBase(WvBufBase<S> &_buf) :
        WvBufBase<T>(_buf.getstore()) { }
};

#endif // __WVBUFFERBASE_H
