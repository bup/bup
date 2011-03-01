#ifndef __WVCOMSTATUS_H
#define __WVCOMSTATUS_H

#include "wverror.h"

/**
 * A stackable WvError, stuitable for use with WvCom.
 * 
 * Every time you create a WvComStatus, it pushes itself onto the stack
 * (ie. WvComStatus::topmost).  When WvCom needs to set an error, it sets the
 * topmost WvComStatus object, which you can check whenever you want.
 * 
 * When a not-isok() WvComStatus is deleted, it copies its error status up to
 * the next WvComStatus in the stack.  (And because of standard WvError
 * semantics, this only has an effect if that WvComStatus is currently isok().)
 * 
 * The net result is that you can avoid checking for errors until you feel like
 * it; just create a WvComStatus, run some stuff, then check the status when
 * you're done.  If you want to create a special context and catch errors
 * during that context, then report them differently, just create a WvComStatus
 * on the stack, do your thing, and (if appropriate) reset() it before deleting.
 * That way, you can control whether the error in your context propagates up to
 * whoever called you.
 */
class WvComStatus : public WvError
{
    static WvComStatus *topmost;
    WvComStatus *last_topmost;
    WvString prefix;

    void init();

public:
    WvComStatus(WvStringParm _prefix = WvString::null, WvErrorCallback ecb = 0)
	: WvError(ecb), prefix(!!_prefix ? _prefix : WvString::null)
    {
	init();
    }

    ~WvComStatus();

    virtual WvString errstr() const;
};


/**
 * A WvComStatus that never propagates up the stack.
 * 
 * Create one of these if you want to just ignore any errors that occur during
 * a particular timeframe.
 */
class WvComStatusIgnorer : public WvComStatus
{
public:
    ~WvComStatusIgnorer()
    {
	reset();
    }
};

#endif // __WVCOMSTATUS_H
