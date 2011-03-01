#ifndef __HTTPGET_H
#define __HTTPGET_H

#include "wverror.h"
#include "wvbuf.h"

WvError _http_get(WvBuf &buf, WvStringParm url, int startbyte, int bytelen);

#endif // __HTTPGET_H
