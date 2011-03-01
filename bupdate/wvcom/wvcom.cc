#include "wvcom.h"
#include "wvcomstatus.h"
#include "wvstringlist.h"

int WvComBase::refcount;


void WvCom::seterr(int num, WvStringParm _str) const
{
    WvComStatus st(objname);
    WvString str = _str;
    if (!str)
	st.set_both(num, "%s (#%s)\n", WvError::strerror(num), num);
    else
	st.set_both(num, str);
}


WvVariant WvCom::_invokev(int autoType, DISPID &id, WvStringParm name,
			  int cArgs, va_list &val) const
{
    VARIANT empty;
    empty.vt = VT_EMPTY;

    WvComStatus st;
    if (!p)
    {
	seterr(EINVAL, "IDispatch is NULL");
	return WvVariant();
    }

    if (!id)
    {
	id = name_to_id(name);
	if (!st.isok())
	    return WvVariant();
    }

    VARIANT result;
    VariantInit(&result);

    DISPPARAMS dp = { NULL, NULL, 0, 0 };
    DISPID dispidNamed = DISPID_PROPERTYPUT;
    HRESULT hr;
    unsigned argerr = 0;
    EXCEPINFO ei;
    memset(&ei, 0, sizeof(ei));

    // The arguments need to be in reverse order, because that's how Invoke
    // expects them.  Weird, but true.
    VARIANT *pArgs = new VARIANT[cArgs+1];
    for(int i = cArgs-1; i >= 0; i--)
	pArgs[i] = va_arg(val, VARIANT);

    // Build DISPPARAMS
    dp.cArgs = cArgs;
    dp.rgvarg = pArgs;

    // for PUT and PUTREF, the docs say you have to set the DISPPARAM as
    // follows.
    if (   (autoType & DISPATCH_PROPERTYPUT)
	   || (autoType & DISPATCH_PROPERTYPUTREF))
    {
	dp.cNamedArgs = 1;
	dp.rgdispidNamedArgs = &dispidNamed;
    }

    hr = p->Invoke(id, IID_NULL, LOCALE_SYSTEM_DEFAULT, autoType,
		   &dp, &result, &ei, &argerr);

    if (FAILED(hr))
    {
	WvStringList l;
	for (int i = 0; i < cArgs; i++)
	{
	    WvVariant v(pArgs[cArgs-i-1], false);
	    l.append(v);
	}
	WvString callinfo("%s(%s)", name, l.join(","));

	if (ei.pfnDeferredFillIn)
	    ei.pfnDeferredFillIn(&ei);

	switch (hr)
	{
	case DISP_E_BADPARAMCOUNT:
	    seterr(EINVAL, "%s: wrong parameter count", callinfo);
	    break;
	case DISP_E_BADVARTYPE:
	    seterr(EINVAL, "%s: not a valid variant type", callinfo);
	    break;
	case DISP_E_EXCEPTION:
	    seterr(EIO, "%s: (EX#%s/%s) %s", callinfo,
		   ei.wCode, ei.scode,
		   WvComString(ei.bstrDescription));
	    break;
	case DISP_E_MEMBERNOTFOUND:
	    seterr(EINVAL, "%s: requested member not found", callinfo);
	    break;
	case DISP_E_NONAMEDARGS:
	    seterr(EINVAL, "%s: named args not supported", callinfo);
	    break;
	case DISP_E_OVERFLOW:
	    seterr(EINVAL, "%s: value too large for data type", callinfo);
	    break;
	case DISP_E_PARAMNOTFOUND:
	    seterr(EINVAL, "%s: parameter %s not found", callinfo, argerr);
	    break;
	case DISP_E_TYPEMISMATCH:
	    seterr(EINVAL, "%s: type mismatch on parameter %s",
		   callinfo, argerr);
	    break;
	case DISP_E_UNKNOWNINTERFACE:
	    seterr(EINVAL, "%s: riid is not IID_NULL", callinfo);
	    break;
	case DISP_E_UNKNOWNLCID:
	    seterr(ENOENT, "%s: Unknown locale", callinfo);
	    break;
	case DISP_E_PARAMNOTOPTIONAL:
	    seterr(EINVAL, "%s: parameter not optional", callinfo);
	default:
	    char buf[200];
	    sprintf(buf, "0x%08lx", hr);
	    seterr(EINVAL, "%s => code %s", callinfo, buf);
	    break;
	}
	result = empty;

	if (ei.bstrDescription) SysFreeString(ei.bstrDescription);
	if (ei.bstrSource)      SysFreeString(ei.bstrSource);
	if (ei.bstrHelpFile)    SysFreeString(ei.bstrHelpFile);
    }

    delete[] pArgs;
    return WvVariant(result, true);
}


WvVariant WvCom::invokev(int autoType, const WvComString &name, int cArgs,
			 va_list &val) const
{
    DISPID id = 0;
    return _invokev(autoType, id, name, cArgs, val);
}


WvVariant WvCom::_invoke(int autoType, DISPID &id, WvStringParm name, 
			 int cArgs, ...)
    const
{
    va_list val;
    va_start(val, cArgs);
    WvVariant v = _invokev(autoType, id, name, cArgs, val);
    va_end(val);
    return v;
}


WvVariant WvCom::invoke(int autoType, const WvComString &name, int cArgs, ...)
    const
{
    va_list val;
    va_start(val, cArgs);
    WvVariant v = invokev(autoType, name, cArgs, val);
    va_end(val);
    return v;
}


WvCom WvCom::invokeobj(int autoType, const WvComString &name, int cArgs, ...)
    const
{
    va_list val;
    
    WvString args("");
    if (cArgs)
    {
	va_start(val, cArgs);
	args = WvString("(%s)", WvVariant(va_arg(val, VARIANT), false));
	va_end(val);
    }
    
    va_start(val, cArgs);
    WvVariant v = invokev(autoType, name, cArgs, val);
    va_end(val);
    
    WvString newobjname;
    if (!!objname)
	newobjname = WvString("%s.%s", objname, name);
    else
	newobjname = name;
    return WvCom(v, WvString("%s%s", newobjname, args));
}
