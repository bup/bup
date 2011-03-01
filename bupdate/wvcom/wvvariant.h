#ifndef __WVVARIANT_H
#define __WVVARIANT_H

#include "wvcomstring.h"
#include <ole2.h>
#include <vector>

class WvCom;

/**
 * A wrapper for VARIANT objects, with auto-typecasting and memory management.
 */
class WvVariant
{
    VARIANT inner;

    void init(const WvComString &s);

    void init_from_dispatch(IDispatch *d, bool take_ownership);
	
    void ref()
    {
	VARIANT copy;
	VariantInit(&copy);
	VariantCopy(&copy, &inner);
	inner = copy;
    }

    void unref();

    static time_t ms_to_time(double msdate)
    {
	return (time_t)((msdate - 25569) * 24 * 3600);
    }
    
public:
    /** Create a VT_EMPTY variant. */
    WvVariant()
    {
	VariantInit(&inner);
    }
    
    /** Safely copy an existing WvVariant, managing refcounts correctly. */
    WvVariant(const WvVariant &v)
    { 
	inner = v.inner;
	ref();
    }
    
    /**
     * Create a WvVariant from a VARIANT.
     * 
     * If take_ownership is true, we'll free the VARIANT automatically.  Exactly
     * one WvVariant should take ownership of a particular VARIANT object.
     * 
     * If you copy a WvVariant into another one, it'll make a copy of the
     * VARIANT, so both will (safely) be owners of their own VARIANT.
     */
    WvVariant(VARIANT _v, bool take_ownership)
    {
	inner = _v;
	if (!take_ownership)
	    ref();
    }
    
    /**
     * Create a WvVariant from an IDispatch*.
     */
    WvVariant(IDispatch *d, bool take_ownership)
    {
	init_from_dispatch(d, take_ownership);
    }
    
    /**
     * Create a WvVariant from a WvCom object (which contains an IDispatch*).
     */
    WvVariant(const WvCom &c);
    
    /** Create a WvVariant (VT_BSTR) from a string, converting to unicode. */
    WvVariant(const char *s)
    {
	init(s);
    }
    
    /**
     * Create a WvVariant (VT_BSTR) from a unicode string.  We make a copy of
     * the string, so you have to free the original yourself.
     */
    WvVariant(const WCHAR *s)
    {
	init(s);
    }
    
    /** Create a WvVariant (VT_BSTR) from a WvString, converting to unicode. */
    WvVariant(WvStringParm s)
    {
	init(WvString(s));
    }
    
    /** Create a WvVariant (VT_I4) from an int. */
    WvVariant(int i)
    {
	inner.vt = VT_I4;
	inner.lVal = i;
    }
    
    /** Create a WvVariant (VT_BOOL) from a bool. */
    WvVariant(bool b)
    {
	inner.vt = VT_BOOL;
	inner.boolVal = b;
    }
    
    /** Create a WvVariant (VT_R8) from a double. */
    WvVariant(double d)
    {
	inner.vt = VT_R8;
	inner.dblVal = d;
    }
    
    /** Create a WvVariant (VT_UI1|VT_ARRAY) from a blob */
    WvVariant(const unsigned char *buf, size_t len);

    WvVariant(std::vector<WvVariant> arr);

    ~WvVariant()
    {
	unref();
    }

    /** It's always safe to copy one WvVariant into another. */
    WvVariant &operator= (const WvVariant &v);

    /**
     * Return the binary blob stored in this variant... if it's an array
     * of VT_UI1.  This function allocates the buffer pointer and fills the
     * length field automatically.  You'll need to delete[] the buffer yourself
     * later.  The returned buffer may be NULL (if this variant is the wrong
     * type or the stored value is really NULL).
     */
    void blob(unsigned char **buf, size_t *len);

    /**
     * Return this variant's contents in the form of a WvComString.  Even if the
     * original variant isn't a string, this will convert it into a printable
     * string.
     */
    WvComString wstr() const;

    /** Like wstr(), but returns a UTF-8 string instead. */
    WvString str() const
    {
	return wstr();
    }

    /** An auto-typecast version of wstr(). */
    operator WvComString () const
    {
	return wstr();
    }

    /** An auto-typecast version of str(). */
    operator WvString () const
    {
	return str();
    }

    /** Auto-convert the variant into an int, if possible. */
    operator int () const;

    operator HWND () const;

    /** Auto-convert the variant into an int and check if it's nonzero. */
    operator bool () const
    {
	return (int)(*this);
    }
    
    /** If the variant is VT_DISPATCH, auto-convert it to IDispatch pointer. */
    operator IDispatch* () const
    {
	if (inner.vt == VT_DISPATCH)
	    return inner.pdispVal;
	return NULL;
    }
    
    /** If the variant is VT_UNKNOWN, auto-convert it to an IUnknown pointer. */
    operator IUnknown* () const;

    /** If the variant is VT_ARRAY|VT_VARIANT, give us a (new'd) vector of
     *  variants. */
    operator std::vector<WvVariant> *() const;

    /** True if the variant is uninitialized (VT_EMPTY) or NULL (VT_NULL).
     *  or VT_ERROR, because apparently an Optional variant via VBA qualifies
     *  as this. */
    bool isnull() const
    {
	return inner.vt == VT_EMPTY || inner.vt == VT_NULL ||
		inner.vt == VT_ERROR;
    }

    /** True if variant is uninitialized (VT_EMPTY).  VT_NULL is not empty. */
    bool isempty() const
    {
	return inner.vt == VT_EMPTY;
    }

    /**
     * Auto-convert back to a VARIANT.
     * 
     * WARNING: the resulting VARIANT is still owned by this object.  Be
     * careful when converting to VARIANT and back to a new WvVariant; you
     * should make sure to set take_ownership=false in the new object.
     */
    operator VARIANT ()
    {
	return inner;
    }
};


#endif // __WVVARIANT_H
