#include "wvvariant.h"
#include "wvcom.h"
#include "wvstringlist.h"
#ifndef assert
#include <assert.h>
#endif

void WvVariant::init(const WvComString &s)
{
    inner.vt = VT_EMPTY;
    if (s)
    {
	inner.vt = VT_BSTR;
	inner.bstrVal = SysAllocString(s);
    }
}


void WvVariant::init_from_dispatch(IDispatch *d, bool take_ownership)
{
    inner.vt = VT_NULL;
    if (d)
    {
	inner.vt = VT_DISPATCH;
	inner.pdispVal = d;
	if (!take_ownership)
	    ref();
    }
}


void WvVariant::unref()
{
    /* VariantClear doesn't mess with IUnknown/IDispatch, 
     * but we did in ref() */
    switch (inner.vt)
    {
    case VT_UNKNOWN:
	if (inner.punkVal) inner.punkVal->Release();
	VariantInit(&inner);
	break;
    case VT_DISPATCH:
	if (inner.pdispVal) inner.pdispVal->Release();
	VariantInit(&inner);
	break;
    }
    VariantClear(&inner); // auto-frees BSTR (supposedly?)
}


WvVariant::WvVariant(const WvCom &c)
{
    init_from_dispatch(c.dispatch(), false);
}


WvVariant::WvVariant(const unsigned char *buf, size_t len)
{
    inner.vt = VT_UI1|VT_ARRAY;
    inner.parray = SafeArrayCreateVector(VT_UI1, 0, len);
    assert(inner.parray);
    
    void *p = NULL;
    HRESULT hr = SafeArrayAccessData(inner.parray, &p);
    assert(hr == S_OK);
    memcpy(p, buf, len);
    hr = SafeArrayUnaccessData(inner.parray);
    assert(hr == S_OK);
}


WvVariant::WvVariant(std::vector<WvVariant> arr)
{
    inner.vt = VT_ARRAY|VT_VARIANT;
    inner.parray = SafeArrayCreateVector(VT_VARIANT, 0, arr.size());
    assert(inner.parray);
    long i = 0;
    for (std::vector<WvVariant>::iterator vi = arr.begin();
	    vi != arr.end(); ++vi, ++i)
    {
	VARIANT v = *vi;
	SafeArrayPutElement(inner.parray, &i, &v);
    }
}


WvVariant &WvVariant::operator=(const WvVariant &v)
{
    if (&v != this)
    {
	unref();
	inner = v.inner;
	ref();
    }
    return *this;
}


void WvVariant::blob(unsigned char **buf, size_t *len)
{
    assert(buf);
    assert(len);
    *buf = NULL;
    *len = 0;
    if (inner.vt != (VT_UI1|VT_ARRAY))
    {
	fprintf(stderr, "WvCom-WARNING-b: unexpected vtype %d\n", inner.vt);
	return;
    }
    
    void *p = NULL;
    HRESULT hr = SafeArrayAccessData(inner.parray, &p);
    assert(hr == S_OK);
    *len = inner.parray->rgsabound->cElements;
    *buf = new unsigned char[*len];
    memcpy(*buf, p, *len);
    hr = SafeArrayUnaccessData(inner.parray);
    assert(hr == S_OK);
}


static VARIANT *get_safe_vararray(SAFEARRAY *a)
{
    // This union works around a:
    //   dereferencing type-punned pointer will break strict-aliasing
    //   rules
    // error that GCC throws at us with -O2.
    union
    {
	VARIANT *p;
	void *p_ugly;
    };
    HRESULT hr = SafeArrayAccessData(a, &p_ugly);
    assert(hr == S_OK);

    return p;
}


WvComString WvVariant::wstr() const
{
    char buf[200];
    switch (inner.vt)
    {
    case VT_EMPTY:
    case VT_NULL:
	return "(nil)";
    case VT_DISPATCH:
	if (inner.pdispVal)
	    return "(ptr)";
	return "(nil)";
    case VT_UNKNOWN:
	if (inner.punkVal)
	    return "(ptr)";
	return "(nil)";
    case VT_BSTR:
	return WvComString(inner.bstrVal);
    case VT_UI1|VT_ARRAY:
	// this is a bit weird: we assume it's a unicode string, even if
	// it thinks it's a VT_UI1 array and not a VT_UI2 array.  This is
	// because if you insert value "whatever" into a dbLongBinary array,
	// it'll assume the string is unicode and use that.  However,
	// the number of elements is the number of *bytes*, not characters.
	{
	    void *p = NULL;
	    HRESULT hr = SafeArrayAccessData(inner.parray, &p);
	    assert(hr == S_OK);
	    int nelem = inner.parray->rgsabound->cElements;
	    WCHAR *cptr = new WCHAR[nelem/2+1];
	    memcpy(cptr, p, nelem);
	    cptr[nelem/2] = 0;
	    hr = SafeArrayUnaccessData(inner.parray);
	    assert(hr == S_OK);
	    WvComString s(cptr);
	    delete[] cptr;
	    return s;
	}
    case VT_UI1:
	return WvComString(WvString(inner.bVal));
    case VT_I1:
	return WvComString(WvString(inner.cVal));
    case VT_I2:
	return WvComString(WvString(inner.iVal));
    case VT_I4:
	return WvComString(WvString(inner.lVal));
    case VT_INT:
	return WvComString(WvString(inner.intVal));
    case VT_R4:
	return WvComString(WvString(inner.fltVal));
    case VT_R8:
	return WvComString(WvString(inner.dblVal));
    case VT_CY: // currency
	{
	    long long v = inner.cyVal.int64;
	    long long w = v/10000;
	    long long f = v - w*10000;
	    if (f < 0) f = -f;
	    WvString vs("%s.%04s", w, f);
	    return WvComString(vs);
	}
    case VT_BOOL:
	return WvComString(inner.boolVal ? "1" : "0");
    case VT_DATE:
	{
	    time_t t = ms_to_time(inner.date);
	    struct tm *tm = gmtime(&t);
	    if (!tm)
	    {
		t = -1;
		tm = gmtime(&t);
	    }
	    if (!tm) // wine is buggy?
	    {
		t = 0;
		tm = gmtime(&t);
	    }
	    assert(tm);
	    strftime(buf, sizeof(buf), "%Y/%m/%d %H:%M:%S", tm);
	    return WvComString(buf);
	}
    case VT_ARRAY|VT_VARIANT:
	{
	    VARIANT *p = get_safe_vararray(inner.parray);

	    int nelem = inner.parray->rgsabound->cElements;
	    WvStringList retl;
	    for (int i = 0; i < nelem; ++i)
	    {
		WvVariant vi(p[i], false);
		retl.append(WvString("\"%s\"", vi.str()));
	    }
	    SafeArrayUnaccessData(inner.parray);
	    return WvComString(retl.join(","));
	}
    default:
	fprintf(stderr, "WvCom-WARNING1: unexpected vtype %d\n", inner.vt);
	return WvComString(WvString());
    }
}


WvVariant::operator int() const
{
    switch (inner.vt)
    {
    case VT_EMPTY:
    case VT_NULL:
	return 0;
    case VT_BSTR:
	return atoi(str());
    case VT_INT:
	return inner.intVal;
    case VT_I4:
	return inner.lVal;
    case VT_I2:
	return inner.iVal;
    case VT_BOOL:
	return inner.boolVal;
    case VT_DATE:
	return ms_to_time(inner.date);
    default:
	fprintf(stderr, "WvCom-WARNING2: unexpected vtype %d\n", inner.vt);
	return 0;
    }
}


WvVariant::operator HWND() const
{
    if (inner.vt == VT_UI4 || inner.vt == VT_I4)
	return (HWND)inner.lVal;
    else
    {
	fprintf(stderr, "WvCom-WARNING-h: unexpected vtype %d\n", inner.vt);
	return 0;
    }
}


WvVariant::operator IUnknown*() const
{
    if (inner.vt == VT_DISPATCH)
	return inner.pdispVal;
    else if (inner.vt == VT_UNKNOWN)
	return inner.punkVal;
    return NULL;
}

WvVariant::operator std::vector<WvVariant> *() const
{
    if (inner.vt != (VT_ARRAY|VT_VARIANT))
	return NULL;

    int nelem = inner.parray->rgsabound->cElements;
    std::vector<WvVariant> *r = new std::vector<WvVariant>();

    VARIANT *p = get_safe_vararray(inner.parray);

    for (int i = 0; i < nelem; ++i)
    {
	WvVariant vi(p[i], false);
	r->push_back(vi);
    }

    SafeArrayUnaccessData(inner.parray);
    return r;
}
