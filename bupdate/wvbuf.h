/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * Specializations of the generic buffering API and a few new buffers.
 */
#ifndef __WVBUFFER_H
#define __WVBUFFER_H
 
#include "wvstring.h"
#include "wvbufbase.h"

/***** Specialization for 'unsigned char' buffers *****/

/**
 * Specialization of WvBufBase for unsigned char type
 * buffers intended for use with raw memory buffers.
 * Refines the interface to add support for untyped pointers.
 * Adds some useful string operations.
 */
template <>
class WvBufBase<unsigned char> :
    public WvBufBaseCommonImpl<unsigned char>
{
public:
    explicit WvBufBase(WvBufStore *store) :
        WvBufBaseCommonImpl<unsigned char>(store) { }

    /**
     * Copies a WvString into the buffer, excluding the null-terminator.
     * "str" is the string
     */
    void putstr(WvStringParm str);
    void putstr(WVSTRING_FORMAT_DECL)
        { putstr(WvString(WVSTRING_FORMAT_CALL)); }

    /**
     * Returns the entire buffer as a null-terminated WvString.
     * 
     * If the buffer contains null characters, they will seem to
     * prematurely terminate the string.
     * 
     * After this operation, ungettable() >= length of the string.
     * 
     * Returns: the buffer contents as a string
     */
    WvString getstr();

    /**
     * Returns the first len characters in the buffer.
     *
     * This is equivalent to doing a get(len), but returns it as a WvString
     * instead of as an unsigned char *.
     */
    WvString getstr(size_t len);

    /*** Get/put characters as integer values ***/

    /**
     * Returns a single character from the buffer as an int.
     * 
     * The same constraints apply as for get(1).
     * 
     * Returns: the character
     */
    int getch()
        { return int(get()); }

    /**
     * Puts a single character into the buffer as an int.
     * 
     * The same constraints apply as for alloc(1).
     * 
     * "ch" is the character
     */
    void putch(int ch)
        { put((unsigned char)ch); }

    /**
     * Peeks a single character from the buffer as an int.
     * 
     * The same constraints apply as for peek(offset, 1).
     * 
     * "offset" is the offset
     * Returns: the character
     */
    int peekch(int offset = 0)
        { return int(peek(offset)); }
    
    /**
     * Returns the number of characters that would have to be read
     * to find the first instance of the character.
     * "ch" is the character
     * Returns: the number of bytes, or zero if the character is not
     *         in the buffer
     */
    size_t strchr(int ch);

    /**
     * Returns the number of leading buffer elements that match
     * any of those in the list.
     * "bytelist" is the list bytes to search for
     * "numbytes" is the number of bytes in the list
     * Returns: the number of leading buffer elements that match
     */
    size_t match(const void *bytelist, size_t numbytes)
        { return _match(bytelist, numbytes, false); }
        
    /**
     * Returns the number of leading buffer elements that match
     * any of those in the list.
     * "chlist" is a string of characters to search for
     * Returns: the number of leading buffer elements that match
     */
    size_t match(const char *chlist)
        { return match(chlist, strlen(chlist)); }

    /**
     * Returns the number of leading buffer elements that do not
     * match any of those in the list.
     * "bytelist" is the list bytes to search for
     * "numbytes" is the number of bytes in the list
     * Returns: the number of leading buffer elements that don't match
     */
    size_t notmatch(const void *bytelist, size_t numbytes)
        { return _match(bytelist, numbytes, true); }

    /**
     * Returns the number of leading buffer elements that do not
     * match any of those in the list.
     * "chlist" is a string of characters to search for
     * Returns: the number of leading buffer elements that don't match
     */
    size_t notmatch(const char *chlist)
        { return notmatch(chlist, strlen(chlist)); }

    /*** Overload put() and move() to accept void pointers ***/
    
    void put(unsigned char value)
        { WvBufBaseCommonImpl<unsigned char>::put(value); }
    void put(const void *data, size_t count)
        { WvBufBaseCommonImpl<unsigned char>::put(
            (const unsigned char*)data, count); }
    void move(void *data, size_t count)
        { WvBufBaseCommonImpl<unsigned char>::move(
            (unsigned char*)data, count); }
    void poke(void *data, int offset, size_t count)
        { WvBufBaseCommonImpl<unsigned char>::poke(
            (unsigned char*)data, offset, count); }

private:
    // moved here to avoid ambiguities between the match variants
    size_t _match(const void *bytelist, size_t numbytes, bool reverse);
};



/***** Declarations for some commonly used memory buffers *****/

/**
 * The in place raw memory buffer type.
 * Refines the interface to add support for untyped pointers.
 */
class WvInPlaceBuf : public WvInPlaceBufBase<unsigned char>
{
public:
    WvInPlaceBuf(void *_data, size_t _avail, size_t _size,
        bool _autofree = false) :
        WvInPlaceBufBase<unsigned char>((unsigned char*)_data,
            _avail, _size, _autofree) { }
    explicit WvInPlaceBuf(size_t _size) :
        WvInPlaceBufBase<unsigned char>(_size) { }
    WvInPlaceBuf() :
        WvInPlaceBufBase<unsigned char>() { }
    void reset(void *_data, size_t _avail, size_t _size,
        bool _autofree = false)
    {
        WvInPlaceBufBase<unsigned char>::reset(
            (unsigned char*)_data, _avail, _size, _autofree);
    }
};

/**
 * The const in place raw memory buffer type.
 * Refines the interface to add support for untyped pointers.
 */
class WvConstInPlaceBuf : public WvConstInPlaceBufBase<unsigned char>
{
public:
    WvConstInPlaceBuf(const void *_data, size_t _avail) :
        WvConstInPlaceBufBase<unsigned char>(
            (const unsigned char*)_data, _avail) { }
    WvConstInPlaceBuf() :
        WvConstInPlaceBufBase<unsigned char>() { }
    void reset(const void *_data, size_t _avail)
    {
        WvConstInPlaceBufBase<unsigned char>::reset(
            (const unsigned char*)_data, _avail);
    }
};

/**
 * The circular in place raw memory buffer type.
 * Refines the interface to add support for untyped pointers.
 */
class WvCircularBuf : public WvCircularBufBase<unsigned char>
{
public:
    WvCircularBuf(void *_data, size_t _avail, size_t _size,
        bool _autofree = false) :
        WvCircularBufBase<unsigned char>((unsigned char*)_data,
            _avail, _size, _autofree) { }
    explicit WvCircularBuf(size_t _size) :
        WvCircularBufBase<unsigned char>(_size) { }
    WvCircularBuf() :
        WvCircularBufBase<unsigned char>() { }
    void reset(void *_data, size_t _avail, size_t _size,
        bool _autofree = false)
    {
        WvCircularBufBase<unsigned char>::reset(
            (unsigned char*)_data, _avail, _size, _autofree);
    }
};

/** The base raw memory buffer type. */
typedef WvBufBase<unsigned char> WvBuf;

/** The dynamically resizing raw memory buffer type. */
typedef WvDynBufBase<unsigned char> WvDynBuf;

/** The empty raw memory buffer type. */
typedef WvNullBufBase<unsigned char> WvNullBuf;

/** The raw memory buffer cursor type. */
typedef WvBufCursorBase<unsigned char> WvBufCursor;

/** The raw memory buffer view type. */
typedef WvBufViewBase<unsigned char> WvBufView;

/** A raw memory read-only buffer backed by a constant WvString */
class WvConstStringBuffer : public WvConstInPlaceBuf
{
    WvString xstr;

public:
    /**
     * Creates a new buffer backed by a constant string.
     *
     * "_str" is the string
     */
    explicit WvConstStringBuffer(WvStringParm _str);

    /** Creates a new empty buffer backed by a null string. */
    WvConstStringBuffer();

    /**
     * Resets the buffer contents to a new string.
     *
     * "_str" is the new string
     */
    void reset(WvStringParm _str);

    /**
     * Returns the string that backs the array
     *
     * Returns: the string
     */
    WvString str()
        { return xstr; }
};

#endif // __WVBUFFER_H
