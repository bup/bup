#include "wvcomstring.h"

void WvComString::init(WvStringParm _s)
{
    s = NULL;
    int needed = MultiByteToWideChar(CP_UTF8, 0, _s, -1, s, 0);
    s = (WCHAR *)malloc(sizeof(WCHAR) * (needed+1));
    s[0] = 0;
    MultiByteToWideChar(CP_UTF8, 0, _s, -1, s, needed);
}
    

WvString WvComString::wide_to_wvstring(const WCHAR *_s)
{
    char *s = NULL;
    int needed = WideCharToMultiByte(CP_UTF8, 0, _s, -1, s, 0, NULL, NULL);
    s = (char *)malloc(needed+1);
    s[0] = 0;
    WideCharToMultiByte(CP_UTF8, 0, _s, -1, s, needed, NULL, NULL);
    WvString r(s);
    free(s);
    return r;
}
