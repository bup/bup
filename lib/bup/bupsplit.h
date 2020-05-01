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
#ifndef __BUPSPLIT_H
#define __BUPSPLIT_H
#include <string.h>
#include <stdint.h>

#define BUP_BLOBBITS (13)
#define BUP_BLOBSIZE (1<<BUP_BLOBBITS)
#define BUP_WINDOWBITS (6)
#define BUP_WINDOWSIZE (1<<BUP_WINDOWBITS)

// According to librsync/rollsum.h:
// "We should make this something other than zero to improve the
// checksum algorithm: tridge suggests a prime number."
// apenwarr: I unscientifically tried 0 and 7919, and they both ended up
// slightly worse than the librsync value of 31 for my arbitrary test data.
#define ROLLSUM_CHAR_OFFSET 31

typedef struct {
    unsigned s1, s2;
    uint8_t window[BUP_WINDOWSIZE];
    int wofs;
} Rollsum;

static inline void rollsum_init(Rollsum *r)
{
    r->s1 = BUP_WINDOWSIZE * ROLLSUM_CHAR_OFFSET;
    r->s2 = BUP_WINDOWSIZE * (BUP_WINDOWSIZE-1) * ROLLSUM_CHAR_OFFSET;
    r->wofs = 0;
    memset(r->window, 0, BUP_WINDOWSIZE);
}

// These formulas are based on rollsum.h in the librsync project.
static inline void rollsum_add(Rollsum *r, uint8_t drop, uint8_t add)
{
    r->s1 += add - drop;
    r->s2 += r->s1 - (BUP_WINDOWSIZE * (drop + ROLLSUM_CHAR_OFFSET));
}

// For some reason, gcc 4.3 (at least) optimizes badly if find_ofs()
// is static and rollsum_roll is an inline function.  Let's use a macro
// here instead to help out the optimizer.
#define rollsum_roll(r, ch) do { \
    rollsum_add((r), (r)->window[(r)->wofs], ch); \
    (r)->window[(r)->wofs] = ch; \
    (r)->wofs = ((r)->wofs + 1) % BUP_WINDOWSIZE; \
} while (0)

static inline uint32_t rollsum_digest(Rollsum *r)
{
    return (r->s1 << 16) | (r->s2 & 0xffff);
}
    
int bupsplit_find_ofs(const unsigned char *buf, int len, int *bits);
int bupsplit_selftest(void);

#endif /* __BUPSPLIT_H */
