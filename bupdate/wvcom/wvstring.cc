/*
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 * 
 * Implementation of a simple and efficient printable-string class.  Most
 * of the class is actually inlined and can be found in wvstring.h.
 */
#include "wvstring.h"
#include <ctype.h>
#include <assert.h>

WvStringBuf WvFastString::nullbuf = { 0, 1 };
const WvFastString WvFastString::null;

const WvString WvString::empty("");


// always a handy function
static inline int _max(int x, int y)
{
    return x>y ? x : y;
}


void WvFastString::setsize(size_t i)
{
    unlink();
    newbuf(i);
}



WvFastString::WvFastString()
{
    link(&nullbuf, NULL);
}


WvFastString::WvFastString(const WvFastString &s)
{
    link(s.buf, s.str);
}


WvFastString::WvFastString(const WvString &s)
{
    link(s.buf, s.str);
}


void WvFastString::construct(const char *_str)
{
    // just copy the pointer - no need to allocate memory!
    str = (char *)_str; // I promise not to change anything!
    buf = NULL;
}


WvFastString::WvFastString(const char *_str)
{
    construct(_str);
}


void WvString::copy_constructor(const WvFastString &s)
{
    unlink();	// WvFastString has already been created by now

    if (!s.buf)
    {
	link(&nullbuf, s.str);
	unique();
    }
    else
	link(s.buf, s.str); // already in a nice, safe WvStreamBuf
}


WvFastString WvFastString::offset(size_t i) const
{ 
    WvFastString retval(*this);
    size_t l = retval.len(); 
    retval.str += (i < l ? i : l); 
    return retval;
}


WvString::WvString(const char *_str)
{
    unlink();	// WvFastString has already been created by now
    construct(_str);
}


// This function returns the NULL of a reversed string representation
// for unsigned integers
template <typename T>
inline static char *wv_uitoar(char *begin, T i)
{
    if (!begin)
	return NULL;

    char *end = begin;

    if (i == 0)
	*end++ = '0';
    else
    {
	while (i > 0)
	{
	    switch (i % 10)
	    {
	    case 0: *end++ = '0'; break;
	    case 1: *end++ = '1'; break;
	    case 2: *end++ = '2'; break;
	    case 3: *end++ = '3'; break;
	    case 4: *end++ = '4'; break;
	    case 5: *end++ = '5'; break;
	    case 6: *end++ = '6'; break;
	    case 7: *end++ = '7'; break;
	    case 8: *end++ = '8'; break;
	    case 9: *end++ = '9'; break;
	    default: ;
	    }
	    i /= 10;
	}
    }

    *end = '\0';
    return end;
}

// This function returns the NULL of a reversed string representation
// for signed integers
template <typename T>
inline static char *wv_itoar(char *begin, T i)
{
    if (!begin)
	return NULL;

    bool negative = false;
    if (i < 0)
    {
	negative = true;
	i = -i;
    }
    char *end = wv_uitoar(begin, i);
    if (negative)
    {
	*end++ = '-';
	*end = '\0';
    }
    return end;
}


inline static void wv_strrev(char *begin, char *end)
{
    if (!begin && !end)
	return;

    --end;

    while (begin < end)
    {
	*begin ^= *end;
	*end ^= *begin;
	*begin ^= *end;
	++begin;
	--end;
    }
}



// NOTE: make sure that 32 bytes is big enough for your longest int.
// This is true up to at least 64 bits.
WvFastString::WvFastString(short i)
{
    newbuf(32);
    wv_strrev(str, wv_itoar(str, i));
}


WvFastString::WvFastString(unsigned short i)
{
    newbuf(32);
    wv_strrev(str, wv_uitoar(str, i));
}


WvFastString::WvFastString(int i)
{
    newbuf(32);
    wv_strrev(str, wv_itoar(str, i));
}


WvFastString::WvFastString(unsigned int i)
{
    newbuf(32);
    wv_strrev(str, wv_uitoar(str, i));
}


WvFastString::WvFastString(long i)
{
    newbuf(32);
    wv_strrev(str, wv_itoar(str, i));
}


WvFastString::WvFastString(unsigned long i)
{
    newbuf(32);
    wv_strrev(str, wv_uitoar(str, i));
}


WvFastString::WvFastString(long long i)
{
    newbuf(32);
    wv_strrev(str, wv_itoar(str, i));
}


WvFastString::WvFastString(unsigned long long i)
{
    newbuf(32);
    wv_strrev(str, wv_uitoar(str, i));
}


WvFastString::WvFastString(double i)
{
    newbuf(32);
    sprintf(str, "%g", i);
}


WvFastString::~WvFastString()
{
    unlink();
}


void WvFastString::unlink()
{ 
    if (buf && ! --buf->links)
    {
	free(buf);
        buf = NULL;
    }
}
    

void WvFastString::link(WvStringBuf *_buf, const char *_str)
{
    buf = _buf;
    if (buf)
	buf->links++;
    str = (char *)_str; // I promise not to change it without asking!
}
    

WvStringBuf *WvFastString::alloc(size_t size)
{
    const size_t s = (WVSTRINGBUF_SIZE(buf) + size + WVSTRING_EXTRA) | 3;
    WvStringBuf *abuf = (WvStringBuf *)calloc(s, sizeof(char));
    abuf->size = s;
    abuf->links = 0;
    return abuf;
}


WvString &WvString::append(WvStringParm s)
{
    if (s)
    {
	if (*this)
	    *this = WvString("%s%s", *this, s);
	else
	    *this = s;
    }
    
    return *this;
}


size_t WvFastString::len() const
{
    return str ? strlen(str) : 0;
}


void WvFastString::newbuf(size_t size)
{
    buf = alloc(size);
    buf->links = 1;
    str = buf->data;
}


// If the string is linked to more than once, we need to make our own copy 
// of it.  If it was linked to only once, then it's already "unique".
WvString &WvString::unique()
{
    if (!is_unique() && str)
    {
	size_t mylen = len();
	WvStringBuf *newb = alloc(mylen);
	memcpy(newb->data, str, mylen);
	unlink();
	link(newb, newb->data);
    }
	    
    return *this; 
}


bool WvString::is_unique() const
{
    return (buf->links <= 1);
}


WvFastString &WvFastString::operator= (const WvFastString &s2)
{
    if (s2.buf == buf && s2.str == str)
	return *this; // no change
    else
    {
	unlink();
	link(s2.buf, s2.str);
    }
    return *this;
}


WvString &WvString::operator= (int i)
{
    unlink();
    newbuf(32);
    sprintf(str, "%d", i);
    return *this;
}


WvString &WvString::operator= (const WvFastString &s2)
{
    if (s2.str == str && (!s2.buf || s2.buf == buf))
	return *this; // no change
    else if (!s2.buf)
    {
	// We have a string, and we're about to free() it.
	if (str && buf && buf->links == 1)
	{
	    // FIXME:  This assert has to go, but I'm not sure why the previous
	    // code (which just set buf->size) was actually here, so I'll keep
	    // it here for now and remove it if I find no issues.
	    assert(buf->size > 0);

	    if (str < s2.str && s2.str <= (str + buf->size))
	    {
		// If the two strings overlap, we'll just need to
		// shift s2.str over to here.
		memmove(buf->data, s2.str, strlen(s2.str) + 1);
		return *this;
	    }
	}
	// assigning from a non-copied string - copy data if needed.
	unlink();
	link(&nullbuf, s2.str);
	unique();
    }
    else
    {
	// just a normal string link
	unlink();
	link(s2.buf, s2.str);
    }
    return *this;
}


// string comparison
bool WvFastString::operator== (WvStringParm s2) const
{
    return (str==s2.str) || (str && s2.str && !strcmp(str, s2.str));
}


bool WvFastString::operator!= (WvStringParm s2) const
{
    return (str!=s2.str) && (!str || !s2.str || strcmp(str, s2.str));
}


bool WvFastString::operator< (WvStringParm s2) const
{
    if (str == s2.str) return false;
    if (str == 0) return true;
    if (s2.str == 0) return false;
    return strcmp(str, s2.str) < 0;
}


bool WvFastString::operator== (const char *s2) const
{
    return (str==s2) || (str && s2 && !strcmp(str, s2));
}


bool WvFastString::operator!= (const char *s2) const
{
    return (str!=s2) && (!str || !s2 || strcmp(str, s2));
}


bool WvFastString::operator< (const char *s2) const
{
    if (str == s2) return false;
    if (str == 0) return true;
    if (s2 == 0) return false;
    return strcmp(str, s2) < 0;
}


// not operator is 'true' if string is empty
bool WvFastString::operator! () const
{
    return !str || !str[0];
}


bool WvFastString::endswith(WvStringParm ending) const
{
    int mylen = len(), elen = ending.len();
    return *this && ending 
	&& mylen >= elen && !strncmp(str+(mylen-elen), ending, elen);
}
    

bool WvFastString::startswith(WvStringParm starting) const
{
    return *this && starting && !strncmp(*this, starting, starting.len());
}


/** 
 * parse a 'percent' operator from a format string.  For example:
 *        cptr      out:  zeropad  justify   maxlen argnum  return pointer
 *        "%s"             false      0         0     0         "s"
 *        "%-15s"          false    -15         0     0         "s"
 *        "%15.5s"         false     15         5     0         "s"
 *        "%015.5s"        true      15         5     0         "s"
 *        "%15$2s"         false     15         0     2         "s"
 * and so on.  On entry, cptr should _always_ point at a percent '%' char.
 * argnum is the argument number.
 */
static const char *pparse(const char *cptr, bool &zeropad,
			  int &justify, int &maxlen, int &argnum)
{
    assert(*cptr == '%');
    cptr++;

    zeropad = (*cptr == '0');

    justify = atoi(cptr);
    
    for (; *cptr && *cptr!='.' && *cptr!='%' && *cptr!='$' 
                                        && !isalpha(*cptr); cptr++)
	;
    if (!*cptr) return cptr;
    
    if (*cptr == '.')
	maxlen = atoi(cptr+1);
    else
	maxlen = 0;
    
    for (; *cptr && *cptr!='%' && *cptr!='$' && !isalpha(*cptr); cptr++)
	;
    if (!*cptr) return cptr;
    
    if (*cptr == '$')
	argnum = atoi(cptr+1);
    else
	argnum = 0;

    for (; *cptr && *cptr!='%' && !isalpha(*cptr); cptr++)
	;

    return cptr;
}


/**
 * Accept a printf-like format specifier (but more limited) and an array
 * of WvStrings, and render them into another WvString.  For example:
 *          WvString x[] = {"foo", "blue", 1234};
 *          WvString ret = WvString::do_format("%s%10.2s%-10s", x);
 *
 * The 'ret' string will be:  "foo        bl1234      "
 * Note that only '%s' is supported, though integers can be rendered
 * automatically into WvStrings.  %d, %f, etc are not allowed!
 *
 * This function is usually called from some other function which allocates
 * the array automatically.
 *
 * %$ns (n > 0) is also supported for internationalization purposes. e.g.
 *   ("%$2s is arg2, and %$1s ia arg1", arg1, arg2) 
 */
void WvFastString::do_format(WvFastString &output, const char *format,
			     const WvFastString * const *argv)
{
    static const char blank[] = "(nil)";
    const WvFastString * const *argptr = argv;
    const WvFastString * const *argP;
    const char *iptr = format, *arg;
    char *optr;
    int total = 0, aplen, ladd, justify, maxlen, argnum;
    bool zeropad;
    
    // count the number of bytes we'll need
    while (*iptr)
    {
	if (*iptr != '%')
	{
	    total++;
	    iptr++;
	    continue;
	}
	
	// otherwise, iptr is at a percent expression
        argnum=0;
	iptr = pparse(iptr, zeropad, justify, maxlen, argnum);
	if (*iptr == '%') // literal percent
	{
	    total++;
	    iptr++;
	    continue;
	}
	
	assert(*iptr == 's' || *iptr == 'c');

	if (*iptr == 's')
	{
            argP = (argnum > 0 ) ?  (argv + argnum -1): argptr;
	    if (!*argP || !(**argP).cstr())
		arg = blank;
	    else
		arg = (**argP).cstr();
	    ladd = _max(abs(justify), strlen(arg));
	    if (maxlen && maxlen < ladd)
		ladd = maxlen;
	    total += ladd;
	    if ( argnum <= 0 ) 
                argptr++;
	    iptr++;
	    continue;
	}
	
	if (*iptr++ == 'c')
	{
	    if (argnum <= 0)
                argptr++;
	    total++;
	}
    }
    
    output.setsize(total);
    
    // actually render the final string
    iptr = format;
    optr = output.str;
    argptr = argv;
    while (*iptr)
    {
	if (*iptr != '%')
	{
	    *optr++ = *iptr++;
	    continue;
	}
	
	// otherwise, iptr is at a "percent expression"
        argnum=0;
	iptr = pparse(iptr, zeropad, justify, maxlen, argnum);
	if (*iptr == '%')
	{
	    *optr++ = *iptr++;
	    continue;
	}
	if (*iptr == 's')
	{
            argP = (argnum > 0 ) ?  (argv + argnum -1): argptr;
	    if (!*argP || !(**argP).cstr())
		arg = blank;
	    else
		arg = (**argP).cstr();
	    aplen = strlen(arg);
	    if (maxlen && maxlen < aplen)
		aplen = maxlen;
	
	    if (justify > aplen)
	    {
	        if (zeropad)
		    memset(optr, '0', justify-aplen);
		else
		    memset(optr, ' ', justify-aplen);
		optr += justify-aplen;
	    }
	
	    strncpy(optr, arg, aplen);
	    optr += aplen;
	
	    if (justify < 0 && -justify > aplen)
	    {
	        if (zeropad)
		    memset(optr, '0', -justify-aplen);
		else
		    memset(optr, ' ', -justify-aplen);
		optr += -justify - aplen;
	    }
	    
	    if ( argnum <= 0 ) 
               argptr++;
	    iptr++;
	    continue;
	}
	if (*iptr++ == 'c')
	{
            argP = (argnum > 0 ) ?  (argv + argnum -1): argptr++;
	    if (!*argP || !(**argP))
		arg = " ";
	    else
		arg = (**argP);
	    *optr++ = (char)atoi(arg);
	}
    }
    *optr = 0;
}
