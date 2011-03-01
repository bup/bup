/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 * 
 * Specializations of the generic buffering API.
 */
#include "wvbuf.h"

/***** Specialization for raw memory buffers *****/

void WvBufBase<unsigned char>::putstr(WvStringParm str)
{
    put((const unsigned char*)str.cstr(), str.len());
}


WvString WvBufBase<unsigned char>::getstr()
{
    /* Copy the contents into the string.
     * We used to just return a reference to those bytes, but
     * that required modifying the buffer to append a null
     * terminator, which does not work with read-only buffers.
     * This method is also somewhat safer if a little slower.
     */ 
    WvString result;
    size_t len = used();
    result.setsize(len + 1);
    char *str = result.edit();
    move(str, len);
    str[len] = '\0';
    return result;
}


WvString WvBufBase<unsigned char>::getstr(size_t len)
{
    WvString result;
    result.setsize(len + 1);
    char *str = result.edit();
    move(str, len);
    str[len] = '\0';
    return result;
}


size_t WvBufBase<unsigned char>::strchr(int ch)
{
    size_t offset = 0;
    size_t avail = used();
    while (offset < avail)
    {
        size_t len = optpeekable(offset);
        const unsigned char *str = peek(offset, len);
        for (size_t i = 0; i < len; ++i)
            if (str[i] == ch)
                return offset + i + 1;
        offset += len;
    }
    return 0;
}


size_t WvBufBase<unsigned char>::_match(const void *bytelist,
    size_t numbytes, bool reverse)
{
    size_t offset = 0;
    size_t avail = used();
    const unsigned char *chlist = (const unsigned char*)bytelist;
    while (offset < avail)
    {
        size_t len = optpeekable(offset);
        const unsigned char *str = peek(offset, len);
        for (size_t i = 0; i < len; ++i)
        {
            int ch = str[i];
            size_t c;
            for (c = 0; c < numbytes; ++c)
                if (chlist[c] == ch)
                    break;
            if (reverse)
            {
                if (c == numbytes)
                    continue;
            }
            else
            {
                if (c != numbytes)
                    continue;
            }
            return offset + i;
        }
        offset += len;
    }
    return reverse ? offset : 0;
}


/***** WvConstStringBuffer *****/

WvConstStringBuffer::WvConstStringBuffer(WvStringParm _str)
{
    reset(_str);
}


WvConstStringBuffer::WvConstStringBuffer()
{
}


void WvConstStringBuffer::reset(WvStringParm _str)
{
    xstr = _str;
    WvConstInPlaceBuf::reset(xstr.cstr(), xstr.len());
}
