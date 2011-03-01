/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 * 
 * A class for managing error numbers and strings.  See wverror.h.
 */
#include "wverror.h"
#include <assert.h>

#ifdef _WIN32
#include "windows.h"

struct WvErrMap {
    int num;
    const char *str;
};

static WvErrMap wverrmap[] = {
    { WSAEINTR, "Interrupted" },
    { WSAEBADF, "Bad file descriptor" },
    { WSAEACCES, "Access denied" },
    { WSAEFAULT, "Bad address" },
    { WSAEINVAL, "Invalid argument" },
    { WSAEMFILE, "Too many open files" },
    { WSAEWOULDBLOCK, "Operation would block" },
    { WSAEINPROGRESS, "Operation now in progress" },
    { WSAEALREADY, "Operation already in progress" },
    { WSAENOTSOCK, "Socket operation on non-socket" },
    { WSAEDESTADDRREQ, "Destination address required" },
    { WSAEMSGSIZE, "Message too long" },
    { WSAEPROTOTYPE, "Protocol wrong type for socket" },
    { WSAENOPROTOOPT, "Protocol not available" },
    { WSAEPROTONOSUPPORT, "Protocol not supported" },
    { WSAESOCKTNOSUPPORT, "Socket type not supported" },
    { WSAEOPNOTSUPP, "Operation not supported on transport endpoint" },
    { WSAEPFNOSUPPORT, "Protocol family not supported" },
    { WSAEAFNOSUPPORT, "Address family not supported by protocol" },
    { WSAEADDRINUSE, "Address already in use" },
    { WSAEADDRNOTAVAIL, "Cannot assign requested address" },
    { WSAENETDOWN, "Network is down" },
    { WSAENETUNREACH, "Network is unreachable" },
    { WSAENETRESET, "Network dropped connection because of reset" },
    { WSAECONNABORTED, "Software caused connection abort" },
    { WSAECONNRESET, "Connection reset by peer" },
    { WSAENOBUFS, "No buffer space available" },
    { WSAEISCONN, "Transport endpoint is already connected" },
    { WSAENOTCONN, "Transport endpoint is not connected" },
    { WSAESHUTDOWN, "Cannot send after transport endpoint shutdown" },
    { WSAETOOMANYREFS, "Too many references: cannot splice" },
    { WSAETIMEDOUT, "Connection timed out" },
    { WSAECONNREFUSED, "Connection refused" },
    { WSAELOOP, "Too many symbolic links encountered" },
    { WSAENAMETOOLONG, "File name too long" },
    { WSAEHOSTDOWN, "Host is down" },
    { WSAEHOSTUNREACH, "No route to host" },
    { WSAENOTEMPTY, "Directory not empty" },
    { WSAEPROCLIM, "Process limit reached" },
    { WSAEUSERS, "Too many users" },
    { WSAEDQUOT, "Disk quota exceeded" },
    { WSAESTALE, "Stale file handle" },
    { WSAEREMOTE, "Object is remote" },
    { WSAEDISCON, "Disconnected" },
    { WSAENOMORE, "No more data" },
    { WSAECANCELLED, "Operation cancelled" },
    { WSAEINVALIDPROCTABLE, "Invalid process table" },
    { WSAEINVALIDPROVIDER, "Invalid provider" },
    { WSAEPROVIDERFAILEDINIT, "Provider failed to initialize" },
    { WSAEREFUSED, "Operation refused" },
    { 0, NULL }
};

static const char *wv_errmap(int errnum)
{
    for (WvErrMap *i = wverrmap; i->num; i++)
	if (i->num == errnum)
	    return i->str;
    return NULL;
}

#endif

WvErrorBase::~WvErrorBase()
{
    // nothing special
}


// win32's strerror() function is incredibly weak, so we'll provide a better
// one.
WvString WvErrorBase::strerror(int errnum)
{
    assert(errnum >= 0);

#ifndef _WIN32
    return ::strerror(errnum);
#else
    const char *wverr = wv_errmap(errnum);
    if (wverr)
        return wverr;
    else if (errnum >= WSABASEERR && errnum < WSABASEERR+2000)
    {
        // otherwise, an unrecognized winsock error: try getting the error
        // message from win32.
        char msg[4096];
        const HMODULE module = GetModuleHandle("winsock.dll");
        DWORD result = FormatMessage(FORMAT_MESSAGE_FROM_SYSTEM,
    			 module, errnum, 0, msg, sizeof(msg), 0);
        if (result)
    	    return msg;
	    
	DWORD e = GetLastError();
	return WvString("Unknown format %s for error %s", e, errnum);
    }
    else
    {
        const char *str = ::strerror(errnum);
        if (!strcmp(str, "Unknown error"))
    	    return WvString("Unknown win32 error #%s", errnum);
	else
	    return str;
    }
#endif
}


WvString WvErrorBase::errstr() const
{
    int errnum = geterr();
    
    if (errnum < 0)
    {
	assert(!!errstring);
	return errstring;
    }
    else
    {
	if (!!errstring) return errstring;
	return WvErrorBase::strerror(errnum);
    }
}


void WvErrorBase::seterr(int _errnum)
{
    if (!errnum)
    {
        assert((_errnum != -1 || !!errstring)
	    && "attempt to set errnum to -1 without also setting errstring");
#ifdef _WIN32
	if (_errnum == WSAECONNABORTED)
	    _errnum = WSAECONNREFUSED; // work around WINE bug
#endif
	errnum = _errnum;
	
	if (errnum && onerror_cb)
	    onerror_cb(*this);
    }
}


void WvErrorBase::seterr(WvStringParm specialerr)
{
    seterr_both(-1, specialerr);
}


void WvErrorBase::seterr(const WvErrorBase &err)
{
    if (!errnum) // don't do it if an error is already set
    {
	// careful! we only want to copy err.errstr() if it's the non-default
	// string.  errstr() always returns a valid string even if errstring
	// isn't set.  We want the true value of errstring, not errstr().
	if (!!err.errstring) errstring = err.errstr();
	seterr(err.geterr());
    }
}


void WvErrorBase::seterr_both(int _errnum, WvStringParm specialerr)
{
    assert(!!specialerr);
    if (!errnum) // don't do it if an error is already set
    {
	errstring = specialerr;
	seterr(_errnum);
    }
}
