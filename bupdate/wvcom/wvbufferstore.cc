/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 * 
 * Defines basic buffer storage classes.
 * These are not intended for use directly by clients.
 * See "wvbufbase.h" for the public API.
 */
#include "wvbufstore.h"
#include <string.h>
#include <sys/types.h>

/**
 * An abstraction for memory transfer operations.
 *
 * This is in preparation for supporting buffers of full-blown
 * objects that have special copy and destruction semantics,
 * someday...
 */
struct MemOps
{
    /** Copies initialized region to uninitialized region. */
    inline void uninit_copy(void *target, const void *source,
        size_t count)
    {
        memcpy(target, source, count);
    }
    /** Copies initialized region to initialized region. */
    inline void copy(void *target, const void *source, size_t count)
    {
        uninit(target, count);
        memcpy(target, source, count);
    }
    /**
     * Moves initialized region to uninitialized region.
     * Source data becomes uninitialized.
     */
    inline void uninit_move(void *target, void *source,
        size_t count)
    {
        memmove(target, source, count);
        uninit(source, count);
    }
    /** Swaps initialized regions. */
    inline void swap(void *target, void *source, size_t count)
    {
        register unsigned char *t1 = (unsigned char*)target;
        register unsigned char *t2 = (unsigned char*)source;
        while (count-- > 0)
        {
            register unsigned char temp;
            temp = *t1;
            *(t1++) = *t2;
            *(t2++) = temp;
        }
    }
    /** Uninitializes a region. */
    inline void uninit(void *target, size_t count)
    {
    }
    /** Creates a new array. */
    inline void *newarray(size_t count)
    {
        return new unsigned char[count];
    }
    /** Deletes an uninitialized array. */
    inline void deletearray(void *buf)
    {
        delete[] (unsigned char*)buf;
    }
} memops;

/** Rounds the value up to the specified boundary. */
inline size_t roundup(size_t value, size_t boundary)
{
    size_t mod = value % boundary;
    return mod ? value + boundary - mod : value;
}



/***** WvBufStore *****/

WvBufStore::WvBufStore(int _granularity) :
    granularity(_granularity)
{
}


size_t WvBufStore::peekable(int offset) const
{
    if (offset == 0)
    {
        return used();
    }
    else if (offset < 0)
    {
        if (size_t(-offset) <= ungettable())
            return size_t(-offset) + used();
    }
    else
    {
        int avail = int(used()) - offset;
        if (avail > 0)
            return avail;
    }
    return 0; // out-of-bounds
}


void WvBufStore::move(void *buf, size_t count)
{
    while (count > 0)
    {
        size_t amount = count;
        assert(amount != 0 ||
            !"attempted to move() more than used()");
        if (amount > count)
            amount = count;
        const void *data = get(amount);
        memops.uninit_copy(buf, data, amount);
        buf = (unsigned char*)buf + amount;
        count -= amount;
    }
}


void WvBufStore::copy(void *buf, int offset, size_t count)
{
    while (count > 0)
    {
        size_t amount = optpeekable(offset);
        assert(amount != 0 ||
            !"attempted to copy() with invalid offset");
        if (amount > count)
            amount = count;
        const void *data = peek(offset, amount);
        memops.uninit_copy(buf, data, amount);
        buf = (unsigned char*)buf + amount;
        count -= amount;
        offset += amount;
    }
}


void WvBufStore::put(const void *data, size_t count)
{
    while (count > 0)
    {
        size_t amount = optallocable();
        assert(amount != 0 ||
            !"attempted to put() more than free()");
        if (amount > count)
            amount = count;
        void *buf = alloc(amount);
        memops.uninit_copy(buf, data, amount);
        data = (const unsigned char*)data + amount;
        count -= amount;
    }
}


void WvBufStore::fastput(const void *data, size_t count)
{
    void *buf = alloc(count);
    memops.uninit_copy(buf, data, count);
}


void WvBufStore::poke(const void *data, int offset, size_t count)
{
    int limit = int(used());
    assert(offset <= limit ||
        !"attempted to poke() beyond end of buffer");
    int end = offset + count;
    if (end >= limit)
    {
        size_t tail = end - limit;
        count -= tail;
        put((const unsigned char*)data + count, tail);
    }
    while (count > 0)
    {
        size_t amount = optpeekable(offset);
        assert(amount != 0 ||
            !"attempted to poke() with invalid offset");
        if (amount > count)
            amount = count;
        void *buf = mutablepeek(offset, amount);
        memops.copy(buf, data, amount);
        data = (const unsigned char*)data + amount;
        count -= amount;
        offset += amount;
    }
}


void WvBufStore::merge(WvBufStore &instore, size_t count)
{
    if (count == 0)
        return;

    if (usessubbuffers() && instore.usessubbuffers())
    {
        // merge quickly by stealing subbuffers from the other buffer
        for (;;)
        {
            WvBufStore *buf = instore.firstsubbuffer();
            if (! buf)
                break; // strange!

            size_t avail = buf->used();
            if (avail > count)
                break;
                
            // move the entire buffer
            bool autofree = instore.unlinksubbuffer(buf, false);
            appendsubbuffer(buf, autofree);
            count -= avail;
            if (count == 0)
                return;
        }
    }
    // merge slowly by copying data
    basicmerge(instore, count);
}


void WvBufStore::basicmerge(WvBufStore &instore, size_t count)
{
    // move bytes as efficiently as we can using only the public API
    if (count == 0)
        return;
    const void *indata = NULL;
    void *outdata = NULL;
    size_t inavail = 0;
    size_t outavail = 0;
    for (;;)
    {
        if (inavail == 0)
        {
            inavail = instore.optgettable();
            assert(inavail != 0 ||
                !"attempted to merge() more than instore.used()");
            if (inavail > count)
                inavail = count;
            indata = instore.get(inavail);
        }
        if (outavail == 0)
        {
            outavail = optallocable();
            assert(outavail != 0 ||
                !"attempted to merge() more than free()");
            if (outavail > count)
                outavail = count;
            outdata = alloc(outavail);
        }
        if (inavail < outavail)
        {
            memops.uninit_copy(outdata, indata, inavail);
            count -= inavail;
            outavail -= inavail;
            if (count == 0)
            {
                unalloc(outavail);
                return;
            }
            outdata = (unsigned char*)outdata + inavail;
            inavail = 0;
        }
        else
        {
            memops.uninit_copy(outdata, indata, outavail);
            count -= outavail;
            if (count == 0) return;
            inavail -= outavail;
            indata = (const unsigned char*)indata + outavail;
            outavail = 0;
        }
    }
}



/***** WvInPlaceBufStore *****/

WvInPlaceBufStore::WvInPlaceBufStore(int _granularity,
    void *_data, size_t _avail, size_t _size, bool _autofree) :
    WvBufStore(_granularity), data(NULL)
{
    reset(_data, _avail, _size, _autofree);
}


WvInPlaceBufStore::WvInPlaceBufStore(int _granularity, size_t _size) :
    WvBufStore(_granularity), data(NULL)
{
    reset(memops.newarray(_size), 0, _size, true);
}


WvInPlaceBufStore::~WvInPlaceBufStore()
{
    if (data && xautofree)
        memops.deletearray(data);
}


void WvInPlaceBufStore::reset(void *_data, size_t _avail,
    size_t _size, bool _autofree = false)
{
    assert(_data != NULL || _avail == 0);
    if (data && _data != data && xautofree)
        memops.deletearray(data);
    data = _data;
    xautofree = _autofree;
    xsize = _size;
    setavail(_avail);
}


void WvInPlaceBufStore::setavail(size_t _avail)
{
    assert(_avail <= xsize);
    readidx = 0;
    writeidx = _avail;
}


size_t WvInPlaceBufStore::used() const
{
    return writeidx - readidx;
}


const void *WvInPlaceBufStore::get(size_t count)
{
    assert(count <= writeidx - readidx ||
        !"attempted to get() more than used()");
    const void *tmpptr = (const unsigned char*)data + readidx;
    readidx += count;
    return tmpptr;
}


void WvInPlaceBufStore::unget(size_t count)
{
    assert(count <= readidx ||
        !"attempted to unget() more than ungettable()");
    readidx -= count;
}


size_t WvInPlaceBufStore::ungettable() const
{
    return readidx;
}


void WvInPlaceBufStore::zap()
{
    readidx = writeidx = 0;
}


size_t WvInPlaceBufStore::free() const
{
    return xsize - writeidx;
}


void *WvInPlaceBufStore::alloc(size_t count)
{
    assert(count <= xsize - writeidx ||
        !"attempted to alloc() more than free()");
    void *tmpptr = (unsigned char*)data + writeidx;
    writeidx += count;
    return tmpptr;
}


void WvInPlaceBufStore::unalloc(size_t count)
{
    assert(count <= writeidx - readidx ||
        !"attempted to unalloc() more than unallocable()");
    writeidx -= count;
}


size_t WvInPlaceBufStore::unallocable() const
{
    return writeidx - readidx;
}


void *WvInPlaceBufStore::mutablepeek(int offset, size_t count)
{
    if (count == 0)
        return NULL;
    assert(((offset <= 0) ? 
        size_t(-offset) <= readidx :
        size_t(offset) < writeidx - readidx) ||
        ! "attempted to peek() with invalid offset or count");
    return (unsigned char*)data + readidx + offset;
}



/***** WvConstInPlaceBufStore *****/

WvConstInPlaceBufStore::WvConstInPlaceBufStore(int _granularity,
    const void *_data, size_t _avail) :
    WvReadOnlyBufferStoreMixin<WvBufStore>(_granularity), data(NULL)
{
    reset(_data, _avail);
}


void WvConstInPlaceBufStore::reset(const void *_data, size_t _avail)
{
    assert(_data != NULL || _avail == 0);
    data = _data;
    setavail(_avail);
}


size_t WvConstInPlaceBufStore::used() const
{
    return avail - readidx;
}


void WvConstInPlaceBufStore::setavail(size_t _avail)
{
    avail = _avail;
    readidx = 0;
}


const void *WvConstInPlaceBufStore::get(size_t count)
{
    assert(count <= avail - readidx ||
        ! "attempted to get() more than used()");
    const void *ptr = (const unsigned char*)data + readidx;
    readidx += count;
    return ptr;
}


void WvConstInPlaceBufStore::unget(size_t count)
{
    assert(count <= readidx ||
        ! "attempted to unget() more than ungettable()");
    readidx -= count;
}


size_t WvConstInPlaceBufStore::ungettable() const
{
    return readidx;
}


const void *WvConstInPlaceBufStore::peek(int offset, size_t count)
{
    if (count == 0)
        return NULL;
    assert(((offset <= 0) ? 
        size_t(-offset) <= readidx :
        size_t(offset) < avail - readidx) ||
        ! "attempted to peek() with invalid offset or count");
    return (const unsigned char*)data + readidx + offset;
}


void WvConstInPlaceBufStore::zap()
{
    readidx = avail = 0;
}



/***** WvCircularBufStore *****/

WvCircularBufStore::WvCircularBufStore(int _granularity,
    void *_data, size_t _avail, size_t _size, bool _autofree) :
    WvBufStore(_granularity), data(NULL)
{
    reset(_data, _avail, _size, _autofree);
}


WvCircularBufStore::WvCircularBufStore(int _granularity, size_t _size) :
    WvBufStore(_granularity), data(NULL)
{
    reset(memops.newarray(_size), 0, _size, true);
}


WvCircularBufStore::~WvCircularBufStore()
{
    if (data && xautofree)
        memops.deletearray(data);
}


void WvCircularBufStore::reset(void *_data, size_t _avail,
    size_t _size, bool _autofree = false)
{
    assert(_data != NULL || _avail == 0);
    if (data && _data != data && xautofree)
        memops.deletearray(data);
    data = _data;
    xautofree = _autofree;
    xsize = _size;
    setavail(_avail);
}


void WvCircularBufStore::setavail(size_t _avail)
{
    assert(_avail <= xsize);
    head = 0;
    totalused = totalinit = _avail;
}


size_t WvCircularBufStore::used() const
{
    return totalused;
}


size_t WvCircularBufStore::optgettable() const
{
    size_t avail = xsize - head;
    if (avail > totalused)
        avail = totalused;
    return avail;
}


const void *WvCircularBufStore::get(size_t count)
{
    assert(count <= totalused ||
        ! "attempted to get() more than used()");
    size_t first = ensurecontiguous(0, count, false /*keephistory*/);
    const void *tmpptr = (const unsigned char*)data + first;
    head = (head + count) % xsize;
    totalused -= count;
    return tmpptr;
}


void WvCircularBufStore::unget(size_t count)
{
    assert(count <= totalinit - totalused ||
        !"attempted to unget() more than ungettable()");
    head = (head + xsize - count) % xsize;
    totalused += count;
}


size_t WvCircularBufStore::ungettable() const
{
    return totalinit - totalused;
}


void WvCircularBufStore::zap()
{
    head = 0;
    totalused = totalinit = 0;
}


size_t WvCircularBufStore::free() const
{
    return xsize - totalused;
}


size_t WvCircularBufStore::optallocable() const
{
    size_t tail = head + totalused;
    if (tail >= xsize)
        return xsize - totalused;
    return xsize - tail;
}


void *WvCircularBufStore::alloc(size_t count)
{
    assert(count <= xsize - totalused ||
        !"attempted to alloc() more than free()");
    totalinit = totalused; // always discard history
    size_t first = ensurecontiguous(totalused, count,
        false /*keephistory*/);
    void *tmpptr = (unsigned char*)data + first;
    totalused += count;
    totalinit += count;
    return tmpptr;
}


void WvCircularBufStore::unalloc(size_t count)
{
    assert(count <= totalused ||
        !"attempted to unalloc() more than unallocable()");
    totalused -= count;
    totalinit -= count;
}


size_t WvCircularBufStore::unallocable() const
{
    return totalused;
}


void *WvCircularBufStore::mutablepeek(int offset, size_t count)
{
    if (count == 0)
        return NULL;
    assert(((offset <= 0) ? 
        size_t(-offset) <= totalinit - totalused :
        size_t(offset) < totalused) ||
        ! "attempted to peek() with invalid offset or count");
    size_t first = ensurecontiguous(offset, count,
        true /*keephistory*/);
    void *tmpptr = (unsigned char*)data + first;
    return tmpptr;
}


void WvCircularBufStore::normalize()
{
    // discard history to minimize data transfers
    totalinit = totalused;

    // normalize the buffer
    compact(data, xsize, head, totalused);
    head = 0;
}


size_t WvCircularBufStore::ensurecontiguous(int offset,
    size_t count, bool keephistory)
{
    // determine the region of interest
    size_t start = (head + offset + xsize) % xsize;
    if (count != 0)
    {   
        size_t end = start + count;
        if (end > xsize)
        {
            // the region is not entirely contiguous
            // determine the region that must be normalized
            size_t keepstart = head;
            if (keephistory)
            {
                // adjust the region to include history
                keepstart += totalused - totalinit + xsize;
            }
            else
            {
                // discard history to minimize data transfers
                totalinit = totalused;
            }
            keepstart %= xsize;

            // normalize the buffer over this region
            compact(data, xsize, keepstart, totalinit);
            head = totalinit - totalused;

            // compute the new start offset
            start = (head + offset + xsize) % xsize;
        }
    }
    return start;
}


void WvCircularBufStore::compact(void *data, size_t size,
    size_t head, size_t count)
{
    if (count == 0)
    {
        // Case 1: Empty region
        // Requires 0 moves
        return;
    }

    if (head + count <= size)
    {
        // Case 2: Contiguous region
        // Requires count moves
        memops.uninit_move(data, (unsigned char*)data + head, count);
        return;
    }
    
    size_t headcount = size - head;
    size_t tailcount = count - headcount;
    size_t freecount = size - count;
    if (freecount >= headcount)
    {
        // Case 3: Non-contiguous region, does not require swapping
        // Requires count moves
        memops.uninit_move((unsigned char*)data + headcount,
            data, tailcount);
        memops.uninit_move(data, (unsigned char*)data + head,
            headcount);
        return;
    }

    // Case 4: Non-contiguous region, requires swapping
    // Requires count * 2 moves
    unsigned char *start = (unsigned char*)data;
    unsigned char *end = (unsigned char*)data + head;
    while (tailcount >= headcount)
    {
        memops.swap(start, end, headcount);
        start += headcount;
        tailcount -= headcount;
    }
    // Now the array looks like: |a|b|c|g|h|_|d|e|f|   
    // FIXME: this is an interim solution
    void *buf = memops.newarray(tailcount);
    memops.uninit_move(buf, start, tailcount);
    memops.uninit_move(start, end, headcount);
    memops.uninit_move(start + headcount, buf, tailcount);
    memops.deletearray(buf);
}



/***** WvLinkedBufferStore *****/

WvLinkedBufferStore::WvLinkedBufferStore(int _granularity) :
    WvBufStore(_granularity), totalused(0), maxungettable(0)
{
}


bool WvLinkedBufferStore::usessubbuffers() const
{
    return true;
}


size_t WvLinkedBufferStore::numsubbuffers() const
{
    return list.count();
}


WvBufStore *WvLinkedBufferStore::firstsubbuffer() const
{
    return list.first();
}


void WvLinkedBufferStore::appendsubbuffer(WvBufStore *buffer,
    bool autofree)
{
    list.append(buffer, autofree);
    totalused += buffer->used();
}


void WvLinkedBufferStore::prependsubbuffer(WvBufStore *buffer,
    bool autofree)
{
    list.prepend(buffer, autofree);
    totalused += buffer->used();
    maxungettable = 0;
}


bool WvLinkedBufferStore::unlinksubbuffer(WvBufStore *buffer,
    bool allowautofree)
{
    WvBufStoreList::Iter it(list);
    WvLink *link = it.find(buffer);
    assert(link);
    
    bool autofree = it.get_autofree();
    totalused -= buffer->used();
    if (buffer == list.first())
        maxungettable = 0;
    if (! allowautofree)
        it.set_autofree(false);
    it.unlink(); // do not recycle the buffer
    return autofree;
}


size_t WvLinkedBufferStore::used() const
{
    assert(!totalused || !list.isempty());
    return totalused;
}


size_t WvLinkedBufferStore::optgettable() const
{
    // find the first buffer with an optgettable() and return that
    size_t count;
    WvBufStoreList::Iter it(list);
    for (it.rewind(); it.next(); )
        if ((count = it->optgettable()) != 0)
            return count;
    return 0;
}


const void *WvLinkedBufferStore::get(size_t count)
{
    assert(!totalused || !list.isempty());
    if (count == 0)
        return NULL;

    assert(count <= totalused);
    assert(count > 0);
    
    totalused -= count;

    assert(totalused >= 0);
    
    // search for first non-empty buffer
    WvBufStore *buf;
    size_t availused;
    WvBufStoreList::Iter it(list);
    for (;;)
    {
        it.rewind(); it.next();
        buf = it.ptr();
        assert(buf && "attempted to get() more than used()" &&
                "totalused is wrong!");

        availused = buf->used();
        if (availused != 0)
            break;

        // unlink the leading empty buffer
        do_xunlink(it);
    }

    // return the data
    if (availused < count)
        buf = coalesce(it, count);

    maxungettable += count;
    return buf->get(count);
}


void WvLinkedBufferStore::unget(size_t count)
{
    assert(!totalused || !list.isempty());
    if (count == 0)
        return;
    assert(count > 0);
    assert(!list.isempty());
    assert(count <= maxungettable);
    totalused += count;
    maxungettable -= count;
    list.first()->unget(count);
}


size_t WvLinkedBufferStore::ungettable() const
{
    assert(!totalused || !list.isempty());
    if (list.isempty())
    {
        assert(maxungettable == 0);
        return 0;
    }

    // maxungettable and list.first()->ungettable() can get out of sync in two ways:
    // - coalescing moves data from later buffers to the first one, which
    // leaves it as ungettable in those buffers.  So when we first start to
    // use a buffer, its ungettable() count may be too high.  (This is the
    // reason maxungettable exists.) 
    // - some calls (ie. alloc) may clear all ungettable data from the first
    // buffer without telling us.  So there might be less data to unget than we
    // think.
    size_t avail = list.first()->ungettable();
    if (avail > maxungettable)
        avail = maxungettable;
    return avail;
}


void WvLinkedBufferStore::zap()
{
    totalused = 0;
    maxungettable = 0;
    WvBufStoreList::Iter it(list);
    for (it.rewind(); it.next(); )
        do_xunlink(it);
}


size_t WvLinkedBufferStore::free() const
{
    if (!list.isempty())
        return list.last()->free();
    return 0;
}


size_t WvLinkedBufferStore::optallocable() const
{
    if (!list.isempty())
        return list.last()->optallocable();
    return 0;
}


void *WvLinkedBufferStore::alloc(size_t count)
{
    if (count == 0)
        return NULL;
    assert(!list.isempty() && "attempted to alloc() more than free()");
    totalused += count;
    return list.last()->alloc(count);
}


void WvLinkedBufferStore::unalloc(size_t count)
{
    assert(count <= totalused);

    totalused -= count;
    while (count > 0)
    {
        assert(!list.isempty() &&
                "attempted to unalloc() more than unallocable()" &&
                "totalused is wrong");
        WvBufStore *buf = list.last();
        size_t avail = buf->unallocable();
        if (count < avail)
        {
            buf->unalloc(count);
            break;
        }
        
        WvBufStoreList::Iter it(list);
        it.find(buf);
        do_xunlink(it);
        
        count -= avail;
    }
}


size_t WvLinkedBufferStore::unallocable() const
{
    return totalused;
}


size_t WvLinkedBufferStore::optpeekable(int offset) const
{
    // search for the buffer that contains the offset
    WvBufStoreList::Iter it(list);
    int newoffset = search(it, offset);
    WvBufStore *buf = it.ptr();
    if (!buf)
        return 0; // out of bounds
    return buf->optpeekable(newoffset);
}


void *WvLinkedBufferStore::mutablepeek(int offset, size_t count)
{
    if (count == 0)
        return NULL;
    
    // search for the buffer that contains the offset
    WvBufStoreList::Iter it(list);
    offset = search(it, offset);
    WvBufStore *buf = it.ptr();
    assert(buf && "attempted to peek() with invalid offset or count");
    
    // return data if we have enough
    size_t availpeek = buf->peekable(offset);
    if (availpeek < count)
        buf = coalesce(it, count);
    return buf->mutablepeek(offset, count);
}


WvBufStore *WvLinkedBufferStore::newbuffer(size_t minsize)
{
    minsize = roundup(minsize, granularity);
    //return new WvInPlaceBufStore(granularity, minsize);
    return new WvCircularBufStore(granularity, minsize);
}


void WvLinkedBufferStore::recyclebuffer(WvBufStore *buffer)
{
    delete buffer;
}


int WvLinkedBufferStore::search(WvBufStoreList::Iter &it,
    int offset) const
{
    it.rewind();
    if (it.next())
    {
        if (offset < 0)
        {
            // inside unget() region
            WvBufStore *buf = it.ptr();
            if (size_t(-offset) <= buf->ungettable())
                return offset;
            it.rewind(); // mark out of bounds
        }
        else
        {
            // inside get() region
            do
            {
                WvBufStore *buf = it.ptr();
                size_t avail = buf->used();
                if (size_t(offset) < avail)
                    return offset;
                offset -= avail;
            }
            while (it.next());
        }
    }
    return 0;
}


WvBufStore *WvLinkedBufferStore::coalesce(WvBufStoreList::Iter &it,
					  size_t count)
{
    WvBufStore *buf = it.ptr();
    size_t availused = buf->used();
    if (count <= availused)
        return buf;

    // allocate a new buffer if there is not enough room to coalesce
    size_t needed = count - availused;
    size_t availfree = buf->free();
    size_t mustskip = 0;
    if (availfree < needed)
    {
        // if this is the first buffer, then we need to unget as
        // much as possible to ensure it does not get discarded
        // during the coalescing phase
        if (buf == list.first() && totalused != 0)
        {
            // use ungettable() instead of buf->ungettable() because we might
            // have reset it to 0
	    // FIXME: uh... who might have reset it to 0, and why?
            mustskip = ungettable();
            buf->unget(mustskip);
        }

        needed = count + mustskip;
        buf = newbuffer(needed);

        // insert the buffer before the previous link
        list.add_after(it.prev, buf, true);
        it.find(buf);
    }
    
    // coalesce subsequent buffers into the first
    while (it.next())
    {
        WvBufStore *itbuf = it.ptr();
        size_t chunk = itbuf->used();
        if (chunk > 0)
        {
            if (chunk > needed)
                chunk = needed;
            buf->merge(*itbuf, chunk);
            needed -= chunk;
            if (needed == 0)
            {
                buf->skip(mustskip);
                return buf;
            }
        }
        do_xunlink(it); // buffer is now empty
    }
    assert(false && "invalid count during get() or peek()");
    return NULL;
}


void WvLinkedBufferStore::do_xunlink(WvBufStoreList::Iter &it)
{
    WvBufStore *buf = it.ptr();
    if (buf == list.first())
        maxungettable = 0;

    bool autofree = it.get_autofree();
    it.set_autofree(false);
    it.xunlink();
    if (autofree)
        recyclebuffer(buf);
}



/***** WvDynBufStore *****/

WvDynBufStore::WvDynBufStore(size_t _granularity,
    size_t _minalloc, size_t _maxalloc) :
    WvLinkedBufferStore(_granularity),
    minalloc(_minalloc), maxalloc(_maxalloc)
{
    assert(maxalloc >= minalloc);
}


size_t WvDynBufStore::free() const
{
    return UNLIMITED_FREE_SPACE;
}


size_t WvDynBufStore::optallocable() const
{
    size_t avail = WvLinkedBufferStore::optallocable();
    if (avail == 0)
        avail = UNLIMITED_FREE_SPACE;
    return avail;
}


void *WvDynBufStore::alloc(size_t count)
{
    if (count > WvLinkedBufferStore::free())
    {
        WvBufStore *buf = newbuffer(count);
        appendsubbuffer(buf, true);
    }
    return WvLinkedBufferStore::alloc(count);
}


WvBufStore *WvDynBufStore::newbuffer(size_t minsize)
{
    // allocate a new buffer
    // try to approximate exponential growth by at least doubling
    // the amount of space available for immediate use
    size_t size = used();
    if (size < minsize * 2)
        size = minsize * 2;
    if (size < minalloc)
        size = minalloc;
    else if (size > maxalloc)
        size = maxalloc;
    if (size < minsize)
        size = minsize;
    return WvLinkedBufferStore::newbuffer(size);
}



/***** WvNullBufStore *****/

WvNullBufStore::WvNullBufStore(size_t _granularity) :
    WvWriteOnlyBufferStoreMixin<
        WvReadOnlyBufferStoreMixin<WvBufStore> >(_granularity)
{
}



/***** WvBufCursorStore *****/

WvBufCursorStore::WvBufCursorStore(size_t _granularity,
    WvBufStore *_buf, int _start, size_t _length) :
    WvReadOnlyBufferStoreMixin<WvBufStore>(_granularity),
    buf(_buf), start(_start), length(_length), shift(0)
{
}


bool WvBufCursorStore::isreadable() const
{
    return buf->isreadable();
}


size_t WvBufCursorStore::used() const
{
    return length - shift;
}


size_t WvBufCursorStore::optgettable() const
{
    size_t avail = buf->optpeekable(start + shift);
    assert(avail != 0 || length == shift ||
        ! "buffer cursor operating over invalid region");
    if (avail > length)
        avail = length;
    return avail;
}


const void *WvBufCursorStore::get(size_t count)
{
    assert(count <= length - shift ||
        ! "attempted to get() more than used()");
    const void *data = buf->peek(start + shift, count);
    shift += count;
    return data;
}


void WvBufCursorStore::skip(size_t count)
{
    assert(count <= length - shift ||
        ! "attempted to skip() more than used()");
    shift += count;
}


void WvBufCursorStore::unget(size_t count)
{
    assert(count <= shift ||
        ! "attempted to unget() more than ungettable()");
    shift -= count;
}


size_t WvBufCursorStore::ungettable() const
{
    return shift;
}


void WvBufCursorStore::zap()
{
    shift = length;
}


size_t WvBufCursorStore::peekable(int offset) const
{
    offset += shift;
    offset -= start;
    if (offset < 0 || offset > int(length))
        return 0;
    return length - size_t(offset);
}


size_t WvBufCursorStore::optpeekable(int offset) const
{
    size_t avail = buf->optpeekable(start + shift + offset);
    assert(avail != 0 || length == shift ||
        ! "buffer cursor operating over invalid region");
    size_t max = peekable(offset);
    if (avail > max)
        avail = max;
    return avail;
}


const void *WvBufCursorStore::peek(int offset, size_t count)
{
    offset += shift;
    assert((offset >= start && offset - start + count <= length) ||
        ! "attempted to peek() with invalid offset or count");
    return buf->peek(offset, count);
}


bool WvBufCursorStore::iswritable() const
{
    // check if mutablepeek() is supported
    return buf->iswritable();
}


void *WvBufCursorStore::mutablepeek(int offset, size_t count)
{
    offset += shift;
    assert((offset >= start && offset - start + count <= length) ||
        ! "attempted to peek() with invalid offset or count");
    return buf->mutablepeek(offset, count);
}
