#ifndef __WVCOM_H
#define __WVCOM_H

#include "wvvariant.h"

/**
 * A base class that makes sure COM is initialized/deinitialized correctly.
 */
class WvComBase
{
    static int refcount;
    WvComBase(const WvComBase &); // doesn't exist
public:
    WvComBase()
    {
//	if (!refcount)
	    CoInitialize(NULL);
	refcount++;
    }

    virtual ~WvComBase()
    {
	refcount--;
//	if (!refcount)
	    CoUninitialize();
    }
};


/**
 * A wrapper for COM IDispatch pointers.
 * 
 * You can use this to call functions and get/set properties via IDispatch.
 * You might also want to create derived classes that provide a nicer API to
 * certain kinds of COM objects.
 */
class WvCom : public WvComBase
{
public:
    void seterr(int num, WvStringParm _str) const;
    
    void seterr(int num, WVSTRING_FORMAT_DECL) const
        { seterr(num, WvString(WVSTRING_FORMAT_CALL)); }
    
private:
    WvString objname;
    IDispatch *p;
    
    void init(const WvComString &progid)
    {
	objname = progid;
	create_from_clsid(progid_to_clsid(progid), progid);
    }
    
    static CLSID empty_clsid()
    {
	CLSID clsid;
	memset(&clsid, 0, sizeof(clsid));
	return clsid;
    }
    
    void create_from_clsid(CLSID clsid, WvStringParm name_hint = WvString())
    {
	p = NULL;
	void *_p;
	
	// supposedly you can just use CLSCTX_ALL here instead of specifying
	// one type or the other.  But when I do that, Access.Application
	// refuses to start.  So let's do it like this instead.
	HRESULT hr = CoCreateInstance(clsid, NULL, CLSCTX_INPROC_SERVER,
				      IID_IDispatch, &_p);
	if (FAILED(hr))
	    hr = CoCreateInstance(clsid, NULL, CLSCTX_LOCAL_SERVER,
				  IID_IDispatch, &_p);
	if (FAILED(hr))
	{
	    if (!!name_hint)
		seterr(EINVAL, "CoCreateInstance(%s) failed: %s",
		       name_hint, hr);
	    else
		seterr(EINVAL, "CoCreateInstance failed");
	}
	p = (IDispatch *)_p;
    }
    
    CLSID progid_to_clsid(const WvComString &progid) const
    {
	CLSID clsid;
	HRESULT hr = CLSIDFromProgID(progid, &clsid);
	if (FAILED(hr))
	{
	    seterr(ENOENT, "CLSIDFromProgID(%s) failed", progid);
	    return empty_clsid();
	}
	return clsid;
    }

    DISPID name_to_id(const WvComString &name) const
    {
	DISPID d;
	const WCHAR *wname = name;
	if (!p)
	{
	    seterr(EINVAL, "GetIDsOfNames(%s): IDispatch was NULL", name);
	    memset(&d, 0, sizeof(d));
	    return d;
	}
	HRESULT hr = p->GetIDsOfNames(IID_NULL, (WCHAR **)&wname, 1, 
				      LOCALE_USER_DEFAULT, &d);
	if (FAILED(hr))
	{
	    seterr(ENOENT, "GetIDsOfNames(%s) failed", name);
	    memset(&d, 0, sizeof(d));
	    return d;
	}
	return d;
    }
    
    void ref()
    {
	if (p) 
	    p->AddRef();
    }
    
    void unref()
    {
	if (p)
	    p->Release();
    }
    
public:
    WvCom()
    {
	p = NULL;
	ref();
    }
    
    WvCom(IDispatch *_p, WvStringParm objname_hint)
    {
	objname = objname_hint;
	p = _p;
	ref();
    }
    
    WvCom(const WvCom &c)
    {
	objname = c.objname;
	p = c.p;
	ref();
    }
    
    WvCom(const WvVariant &v, WvStringParm objname_hint)
    {
	objname = objname_hint;
	p = v;
	if (p)
	    p->AddRef();
	else
	    seterr(EINVAL, "creation: V.IDispatch is NULL");
    }
    
    WvCom(const WvComString &progid)
    {
	init(progid);
    }
    
    WvCom(const char *progid)
    {
	init(progid);
    }
    
    virtual ~WvCom()
    {
	unref();
    }
    
    WvCom &operator= (const WvCom &c)
    {
	if (&c != this)
	{
	    unref();
	    objname = c.objname;
	    p = c.p;
	    ref();
	}
	return *this;
    }
    
    IDispatch *dispatch() const
        { return p; }

    WvString name() const
        { return objname; }
    
    bool isok() const
        { return dispatch() != NULL; }
    
    WvVariant _invokev(int autoType, DISPID &id, WvStringParm name, int cArgs,
		      va_list &val) const;
    WvVariant invokev(int autoType, const WvComString &name, int cArgs,
		      va_list &val) const;
    WvVariant _invoke(int autoType, DISPID &id, WvStringParm name, 
		     int cArgs, ...) 
	const;
    WvVariant invoke(int autoType, const WvComString &name, int cArgs, ...) 
	const;
    WvCom invokeobj(int autoType, const WvComString &name, int cArgs, ...)
	const;
    
    void _set(DISPID &id, WvStringParm name, WvVariant val)
        { _invoke(DISPATCH_PROPERTYPUT, id, name, 1, (VARIANT)val); }
    void set(const WvComString &propname, WvVariant val)
        { invoke(DISPATCH_PROPERTYPUT, propname, 1, (VARIANT)val); }
    
    WvVariant get(const WvComString &propname) const
        { return invoke(DISPATCH_PROPERTYGET, propname, 0); }
    
    WvCom getobj(const WvComString &propname) const
        { return invokeobj(DISPATCH_PROPERTYGET, propname, 0); }

    WvVariant get(const WvComString &propname, WvVariant param) const
        { return invoke(DISPATCH_PROPERTYGET, propname, 1, (VARIANT)param); }

    WvCom getobj(const WvComString &propname, WvVariant param)
        { return invokeobj(DISPATCH_PROPERTYGET, propname, 1, (VARIANT)param); }

    // Support up to 12 parameters.  If you want more, add more functions.
    // 
    // The following would be a lot less stupid if C++ had a sane varargs.
    // Sigh.
    
    WvVariant _call(DISPID &id, const WvComString &name)
        { return _invoke(DISPATCH_METHOD, id, name, 0); }
    WvVariant call(const WvComString &name)
        { return invoke(DISPATCH_METHOD, name, 0); }
    
    WvVariant call(const WvComString &name, WvVariant p1)
        { return invoke(DISPATCH_METHOD, name, 1, (VARIANT)p1); }
    
    WvVariant call(const WvComString &name, WvVariant p1, WvVariant p2)
        { return invoke(DISPATCH_METHOD, name, 2, (VARIANT)p1, (VARIANT)p2); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2, WvVariant p3)
        { return invoke(DISPATCH_METHOD, name, 3,
		(VARIANT)p1, (VARIANT)p2, (VARIANT)p3);
	}
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2, WvVariant p3, WvVariant p4)
        { return invoke(DISPATCH_METHOD, name, 4,
		(VARIANT)p1, (VARIANT)p2, (VARIANT)p3, (VARIANT)p4); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5)
        { return invoke(DISPATCH_METHOD, name, 5,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6)
        { return invoke(DISPATCH_METHOD, name, 6,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7)
        { return invoke(DISPATCH_METHOD, name, 7,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8)
        { return invoke(DISPATCH_METHOD, name, 8,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9)
        { return invoke(DISPATCH_METHOD, name, 9,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10)
        { return invoke(DISPATCH_METHOD, name, 10,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10, WvVariant p11)
        { return invoke(DISPATCH_METHOD, name, 11,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10, (VARIANT)p11); }
    
    WvVariant call(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10, WvVariant p11, WvVariant p12)
        { return invoke(DISPATCH_METHOD, name, 12,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10, (VARIANT)p11, (VARIANT)p12); }
    
    // Same as the preceding, but assumes the returned object is an IDispatch*
    // instead of an arbitrary variant.
    
    WvCom callobj(const WvComString &name)
        { return invokeobj(DISPATCH_METHOD, name, 0); }
    
    WvCom callobj(const WvComString &name, WvVariant p1)
        { return invokeobj(DISPATCH_METHOD, name, 1, (VARIANT)p1); }
    
    WvCom callobj(const WvComString &name, WvVariant p1, WvVariant p2)
        { return invokeobj(DISPATCH_METHOD, name, 2, (VARIANT)p1, (VARIANT)p2); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2, WvVariant p3)
        { return invokeobj(DISPATCH_METHOD, name, 3,
		(VARIANT)p1, (VARIANT)p2, (VARIANT)p3);
	}
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2, WvVariant p3, WvVariant p4)
        { return invokeobj(DISPATCH_METHOD, name, 4,
		(VARIANT)p1, (VARIANT)p2, (VARIANT)p3, (VARIANT)p4); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5)
        { return invokeobj(DISPATCH_METHOD, name, 5,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6)
        { return invokeobj(DISPATCH_METHOD, name, 6,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7)
        { return invokeobj(DISPATCH_METHOD, name, 7,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8)
        { return invokeobj(DISPATCH_METHOD, name, 8,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9)
        { return invokeobj(DISPATCH_METHOD, name, 9,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10)
        { return invokeobj(DISPATCH_METHOD, name, 10,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10, WvVariant p11)
        { return invokeobj(DISPATCH_METHOD, name, 11,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10, (VARIANT)p11); }
    
    WvCom callobj(const WvComString &name,
		   WvVariant p1, WvVariant p2,  WvVariant p3,  WvVariant p4,
		   WvVariant p5, WvVariant p6,  WvVariant p7,  WvVariant p8,
		   WvVariant p9, WvVariant p10, WvVariant p11, WvVariant p12)
        { return invokeobj(DISPATCH_METHOD, name, 12,
		(VARIANT)p1, (VARIANT)p2,  (VARIANT)p3,  (VARIANT)p4,
		(VARIANT)p5, (VARIANT)p6,  (VARIANT)p7,  (VARIANT)p8,
		(VARIANT)p9, (VARIANT)p10, (VARIANT)p11, (VARIANT)p12); }
};


#endif // __WVCOM_H
