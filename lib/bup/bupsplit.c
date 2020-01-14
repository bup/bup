/*
 * Copyright 2011 Avery Pennarun. All rights reserved.
 * 
 * (This license applies to bupsplit.c and bupsplit.h only.)
 * 
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 * 
 *    1. Redistributions of source code must retain the above copyright
 *       notice, this list of conditions and the following disclaimer.
 * 
 *    2. Redistributions in binary form must reproduce the above copyright
 *       notice, this list of conditions and the following disclaimer in
 *       the documentation and/or other materials provided with the
 *       distribution.
 * 
 * THIS SOFTWARE IS PROVIDED BY AVERY PENNARUN AND CONTRIBUTORS ``AS
 * IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL
 * <COPYRIGHT HOLDER> OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
 * OF THE POSSIBILITY OF SUCH DAMAGE.
 */
#include "bupsplit.h"
#include <stdint.h>
#include <memory.h>
#include <stdlib.h>
#include <stdio.h>

// According to librsync/rollsum.h:
// "We should make this something other than zero to improve the
// checksum algorithm: tridge suggests a prime number."
// apenwarr: I unscientifically tried 0 and 7919, and they both ended up
// slightly worse than the librsync value of 31 for my arbitrary test data.
#define ROLLSUM_CHAR_OFFSET 31

// These formulas are based on rollsum.h in the librsync project.
void rollsum_add(Rollsum *r, uint8_t drop, uint8_t add)
{
    r->s1 += add - drop;
    r->s2 += r->s1 - (BUP_WINDOWSIZE * (drop + ROLLSUM_CHAR_OFFSET));
}


void rollsum_init(Rollsum *r)
{
    r->s1 = BUP_WINDOWSIZE * ROLLSUM_CHAR_OFFSET;
    r->s2 = BUP_WINDOWSIZE * (BUP_WINDOWSIZE-1) * ROLLSUM_CHAR_OFFSET;
    r->wofs = 0;
    memset(r->window, 0, BUP_WINDOWSIZE);
}


uint32_t rollsum_digest(Rollsum *r)
{
    return (r->s1 << 16) | (r->s2 & 0xffff);
}


static uint32_t rollsum_sum(uint8_t *buf, size_t ofs, size_t len)
{
    size_t count;
    Rollsum r;
    rollsum_init(&r);
    for (count = ofs; count < len; count++)
	rollsum_roll(&r, buf[count]);
    return rollsum_digest(&r);
}


int bupsplit_find_ofs(const unsigned char *buf, int len, int *bits)
{
    Rollsum r;
    int count;
    
    rollsum_init(&r);
    for (count = 0; count < len; count++)
    {
	rollsum_roll(&r, buf[count]);
	if ((r.s2 & (BUP_BLOBSIZE-1)) == ((~0) & (BUP_BLOBSIZE-1)))
	{
	    if (bits)
	    {
		unsigned rsum = rollsum_digest(&r);
		rsum >>= BUP_BLOBBITS;
		for (*bits = BUP_BLOBBITS; (rsum >>= 1) & 1; (*bits)++)
		    ;
	    }
	    return count+1;
	}
    }
    return 0;
}


#ifndef BUP_NO_SELFTEST
#define BUP_SELFTEST_SIZE 100000

int bupsplit_selftest()
{
    uint8_t *buf = malloc(BUP_SELFTEST_SIZE);
    uint32_t sum1a, sum1b, sum2a, sum2b, sum3a, sum3b;
    unsigned count;
    
    srandom(1);
    for (count = 0; count < BUP_SELFTEST_SIZE; count++)
	buf[count] = random();
    
    sum1a = rollsum_sum(buf, 0, BUP_SELFTEST_SIZE);
    sum1b = rollsum_sum(buf, 1, BUP_SELFTEST_SIZE);
    sum2a = rollsum_sum(buf, BUP_SELFTEST_SIZE - BUP_WINDOWSIZE*5/2,
			BUP_SELFTEST_SIZE - BUP_WINDOWSIZE);
    sum2b = rollsum_sum(buf, 0, BUP_SELFTEST_SIZE - BUP_WINDOWSIZE);
    sum3a = rollsum_sum(buf, 0, BUP_WINDOWSIZE+3);
    sum3b = rollsum_sum(buf, 3, BUP_WINDOWSIZE+3);
    
    fprintf(stderr, "sum1a = 0x%08x\n", sum1a);
    fprintf(stderr, "sum1b = 0x%08x\n", sum1b);
    fprintf(stderr, "sum2a = 0x%08x\n", sum2a);
    fprintf(stderr, "sum2b = 0x%08x\n", sum2b);
    fprintf(stderr, "sum3a = 0x%08x\n", sum3a);
    fprintf(stderr, "sum3b = 0x%08x\n", sum3b);
    
    free(buf);
    return sum1a!=sum1b || sum2a!=sum2b || sum3a!=sum3b;
}

#endif // !BUP_NO_SELFTEST
