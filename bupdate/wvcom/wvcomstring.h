#ifndef __WVCOMSTRING_H
#define __WVCOMSTRING_H

#include "wvstring.h"
#include <wtypes.h>

/**
 * A crappy string class that uses WCHAR instead of char.
 *
 * Knows how to auto-convert itself between wide characters and UTF-8, and
 * cooperates with WvString.
 */
class WvComString
{
    WCHAR *s;
    
    void init(WvStringParm _s);
    static WvString wide_to_wvstring(const WCHAR *_s);
    
public:
    WvComString(WvStringParm _s)
        { init(_s); }
    
    WvComString(const WvComString &_s)
        { init(_s); }
    
    WvComString(const char *_s)
        { init(_s); }
    
    WvComString(const unsigned char *_s) // needed for SQLCHAR
        { init((const char *)_s); }
    
    WvComString(const WCHAR *_s)
        { init(wide_to_wvstring(_s)); }
    
    WvComString(const uint16_t *_s) // needed for SQLWCHAR
        { init(wide_to_wvstring((const WCHAR *)_s)); }
    
    ~WvComString()
        { free(s); }
    
    operator const WCHAR * () const
        { return s; }
    
    operator WCHAR * ()
        { return s; }
    
    operator WvString () const
        { return wide_to_wvstring(s); }
};


#endif // __WVCOMSTRING_H
