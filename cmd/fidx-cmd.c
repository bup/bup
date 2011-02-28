#include "bupsplit.h"
#include <stdio.h>
#include <stdarg.h>
#include <assert.h>
#include <string.h>
#include <malloc.h>
#include <errno.h>
#include <unistd.h>
#include <stdint.h>
#include <arpa/inet.h>

#define FIDX_VERSION 1

// FIXME duplicated with content in hashsplit.py
#define BLOB_MAX (8192*4)
#define BLOB_READ_SIZE (1024*1024)
#define FANOUT_BITS 4

#define msg(fmt, args...) fprintf(stderr, fmt, ##args)
#define xperror(s) do { perror(s); errcount++; } while (0)

typedef int bool;
typedef unsigned char  byte;
#define TRUE 1
#define FALSE 0

int errcount = 0;

struct FidxHdr
{
    byte marker[4];
    uint32_t ver;
};

struct FidxEntry
{
    byte sha[20];
    uint16_t size;
    uint16_t level;
};


// FIXME: this does dynamic allocation, but we caller never frees it
// because we're lazy right now.
char *joinl(char *sep, ...)
{
    va_list ap;
    size_t len, n;
    char *out, *outp, *s;
    
    assert(sep);
    
    len = n = 0;
    va_start(ap, sep);
    while ((s = va_arg(ap, char *)) != NULL)
    {
	if (n) len += strlen(sep);
	len += strlen(s);
	n++;
    }
    va_end(ap);
    
    n = 0;
    out = outp = (char *)malloc(len+1);
    va_start(ap, sep);
    while ((s = va_arg(ap, char *)) != NULL)
    {
	if (n)
	{
	    strcpy(outp, sep);
	    outp += strlen(sep);
	}
	n++;
	strcpy(outp, s);
	outp += strlen(s);
    }
    va_end(ap);
    
    return out;
}


char *cat2(char *a, char *b)
{
    return joinl("", a, b, NULL);
}


void blob_sha(byte sha[20], byte *buf, int len)
{
    memset(sha, 0, sizeof(sha));
}


struct SillySha {};

int fwrite_and_sum(void *buf, size_t len, FILE *outf, struct SillySha *s)
{
    // FIXME update sha
    return fwrite(buf, 1, len, outf);
}


bool write_fidx(FILE *outf, FILE *inf)
{
    byte buf[BLOB_READ_SIZE];
    size_t used = 0, got;
    struct FidxHdr h;
    struct SillySha filesha;
    
    memcpy(h.marker, "FIDX", 4);
    h.ver = htonl(FIDX_VERSION);
    if (fwrite_and_sum(&h, sizeof(h), outf, &filesha) != sizeof(h))
    {
	xperror("fwrite");
	return FALSE;
    }
    
    // FIXME this is inefficient: don't memmove() so often, and drain the
    // buffer before the next fread().  And factor out the bupsplit stuff
    // so it can be reused elsewhere.
    while ((got = fread(buf, 1, sizeof(buf)-used, inf)) > 0)
    {
	int ofs, bits = 0;
	struct FidxEntry e;
	msg("got=%d\n", got);
	used += got;
	
	ofs = bupsplit_find_ofs(buf, used, &bits);
	if (ofs <= 0)
	    ofs = used;
	else
	    assert(bits >= BUP_BLOBBITS);
	
	blob_sha(e.sha, buf, ofs);
	e.size = htons(ofs);
	e.level = htons((bits-BUP_BLOBBITS) / FANOUT_BITS);
	if (fwrite_and_sum(&e, sizeof(e), outf, &filesha) != sizeof(e))
	{
	    xperror("fwrite");
	    return FALSE;
	}
	
	used -= ofs;
	memmove(buf, buf+ofs, used);
    }
    msg("got=%d\n", got);
    
    if (got < 0)
    {
	xperror("fread");
	return FALSE;
    }
    
    // FIXME write filesha here
    
    return TRUE;
}


int main(int argc, char **argv)
{
    int i;
    for (i = 1; i < argc; i++)
    {
	FILE *inf, *outf;
	int ok;
	inf = fopen(argv[i], "rb");
	if (!inf)
	{
	    xperror(argv[i]);
	    continue;
	}
	outf = fopen(cat2(argv[i], ".fidx.tmp"), "wb");
	printf("file: %s\n", argv[i]);
	
	ok = write_fidx(outf, inf);
	
	fclose(outf);
	fclose(inf);
	
	if (ok)
	{
	    if (rename(cat2(argv[i], ".fidx.tmp"), cat2(argv[i], ".fidx")))
		xperror("rename");
	}
	else
	{
	    if (unlink(cat2(argv[i], ".fidx.tmp")))
		xperror("unlink");
	}
    }
    
    if (errcount)
    {
	msg("WARNING: %d errors encountered while hashing.\n", errcount);
	return 1;
    }
    else
	return 0;
}
