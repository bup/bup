#include "wvcom.h"
#include "wvcomstatus.h"
#include "wvbuf.h"


void print(WvStringParm s)
{
    printf("%s", s.cstr());
    fflush(stdout);
}


void print(WVSTRING_FORMAT_DECL)
{
    print(WvString(WVSTRING_FORMAT_CALL));
}


// FIXME: support multiple ranges in a single request?
WvError http_get(WvBuf &buf, WvStringParm url, int startbyte, int bytelen)
{
    WvComStatus err("http");
    if (startbyte < 0)
	return err.set_both(EINVAL, "startbyte must be >= 0");
    if (!(bytelen > 0 || bytelen == -1))
	return err.set_both(EINVAL, "bytelen must be -1 or positive, not 0");

    bool wantrange = (startbyte > 0 || bytelen > 0);
    print("Getting: %s\n", url);
    
    WvCom req("Microsoft.XMLHTTP");
    if (!err.isok())
	return err;
    req.call("Open", "GET", url, false);
    if (wantrange)
    {
	WvString rangestr;
	if (bytelen > 0)
	    rangestr = WvString("bytes=%s-%s", startbyte, startbyte+bytelen-1);
	else
	    rangestr = WvString("bytes=%s-", startbyte);
	req.call("setRequestHeader", "Range", rangestr);
    }
    
    req.call("Send", "");
    int status = req.get("Status");
    
    if (!err.isok())
	return err;
    else if ((wantrange && status != 206) || (!wantrange && status != 200))
    {
	if (!status) status = -1;
	return WvError().set_both(status, "HTTP Status code: %s", status);
    }

    unsigned char *b = NULL;
    size_t len = 0;
    WvVariant v = req.get("responseBody");
    v.blob(&b, &len);
    buf.put(b, len);
    delete[] b;
    
    return err;
}


int main()
{
    WvComStatus err;
    
    for (int i = 0; i < 10; i++)
    {
	WvDynBuf buf;
	WvError e = http_get(buf,
		       "http://afterlife/~apenwarr/music/01 Volcanic Jig.m4a",
			     i, 10*i);
	print("Got %s bytes; status=%s\n", buf.used(), e.str());
    }
    return 0;
}
