#include "wvcomstatus.h"
#ifndef assert
#include <assert.h>
#endif

WvComStatus *WvComStatus::topmost;

void WvComStatus::init()
{
    last_topmost = topmost;
    topmost = this;
}

WvComStatus::~WvComStatus()
{
    assert(topmost == this);
    topmost = last_topmost;
    if (topmost)
	topmost->seterr(*this);
}

WvString WvComStatus::errstr() const
{
    if (!!prefix)
	return WvString("%s: %s", prefix, WvError::errstr());
    else
	return WvError::errstr();
}
