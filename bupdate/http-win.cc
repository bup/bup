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
    print("Getting: %s\n", url);
    
    WvComStatus err("http");
    if (startbyte < 0)
	return err.set_both(EINVAL, "startbyte must be >= 0");
    if (!(bytelen > 0 || bytelen == -1))
	return err.set_both(EINVAL, "bytelen must be -1 or positive, not 0");

    bool wantrange = (startbyte > 0 || bytelen > 0);
    
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
    
    int expected = wantrange ? 206 : 200;
    if (status != expected)
    {
	int nstatus = status ? status : -1;
	return err.set_both(nstatus,
			    "status code: %s (expected %s)",
			    status, expected);
    }

    unsigned char *b = NULL;
    size_t len = 0;
    WvVariant v = req.get("responseBody");
    v.blob(&b, &len);
    
    if (wantrange && (int)len != bytelen)
    {
	delete[] b;
	return err.set("server sent %s bytes (expected %s)", len, bytelen);
    }
    buf.put(b, len);
    delete[] b;
    
    return err;
}


int main()
{
    for (int i = 0; i < 10; i++)
    {
	WvDynBuf buf;
	WvError e = http_get(buf,
		       "http://afterlife/~apenwarr/music/01 Volcanic Jig.m4a",
			     i, 10*i);
	if (!e.isok())
	    print("  ERROR: %s\n", e.str());
	else
	    print("  got %s bytes\n", buf.used());
    }
    return 0;
}
