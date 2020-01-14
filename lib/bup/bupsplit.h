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

typedef struct {
    unsigned s1, s2;
    uint8_t window[BUP_WINDOWSIZE];
    int wofs;
} Rollsum;


// For some reason, gcc 4.3 (at least) optimizes badly if find_ofs()
// is static and rollsum_roll is an inline function.  Let's use a macro
// here instead to help out the optimizer.
#define rollsum_roll(r, ch) do { \
    rollsum_add((r), (r)->window[(r)->wofs], ch); \
    (r)->window[(r)->wofs] = ch; \
    (r)->wofs = ((r)->wofs + 1) % BUP_WINDOWSIZE; \
} while (0)

#ifdef __cplusplus
extern "C" {
#endif
    
int bupsplit_find_ofs(const unsigned char *buf, int len, int *bits);
int bupsplit_selftest(void);

void rollsum_init(Rollsum *r);
void rollsum_add(Rollsum *r, uint8_t drop, uint8_t add);
uint32_t rollsum_digest(Rollsum *r);

#ifdef __cplusplus
}
#endif
    
#endif /* __BUPSPLIT_H */
