#include "fidx.h"
#include "bupsplit.h"
#include "sha1.h"
#include <stdio.h>
#include <stdarg.h>
#include <assert.h>
#include <string.h>
#include <malloc.h>
#include <errno.h>
#include <unistd.h>
#include <stdint.h>

static int errcount = 0;

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
    char tmp[1024];
    sprintf(tmp, "blob %d", len);
    blk_SHA_CTX s;
    blk_SHA1_Init(&s);
    blk_SHA1_Update(&s, tmp, strlen(tmp)+1);
    blk_SHA1_Update(&s, buf, len);
    blk_SHA1_Final(sha, &s);
}


int fwrite_and_sum(void *buf, size_t len, FILE *outf, blk_SHA_CTX *filesha)
{
    blk_SHA1_Update(filesha, buf, len);
    return fwrite(buf, 1, len, outf);
}


int _do_block(byte buf[BLOB_READ_SIZE], size_t used, FILE *outf,
	      blk_SHA_CTX *filesha, bool finish)
{
    int ofs, bits = 0, level;
    struct FidxEntry e;
    
    ofs = bupsplit_find_ofs(buf, used, &bits);
    if (ofs <= 0)
    {
	if (finish)
	{
	    ofs = used;
	    level = 0;
	}
	else
	    return 0;
    }
    else
    {
	assert(bits >= BUP_BLOBBITS);
	level = (bits-BUP_BLOBBITS) / FANOUT_BITS;
    }
    
    if (ofs > BLOB_MAX)
    {
	ofs = BLOB_MAX;
	level = 0;
    }
    
    if (ofs)
    {
	blob_sha(e.sha.sha, buf, ofs);
	//printf("%d %d\n", level, ofs);
	e.size = htons(ofs);
	e.level = htons(level);
	if (fwrite_and_sum(&e, sizeof(e), outf, filesha) != sizeof(e))
	{
	    xperror("fwrite");
	    return -1;
	}
    }
    
    return ofs;
}


bool write_fidx(FILE *outf, FILE *inf)
{
    byte buf[BLOB_READ_SIZE];
    size_t used, ofs, got;
    int rv;
    struct FidxHdr h;
    blk_SHA_CTX filesha;
    
    blk_SHA1_Init(&filesha);
    
    memcpy(h.marker, "FIDX", 4);
    h.ver = htonl(FIDX_VERSION);
    if (fwrite_and_sum(&h, sizeof(h), outf, &filesha) != sizeof(h))
    {
	xperror("fwrite");
	return FALSE;
    }
    
    ofs = used = 0;
    while ((got = fread(buf+used, 1, sizeof(buf)-used, inf)) > 0)
    {
	used += got;
	do {
	    rv = _do_block(buf+ofs, used-ofs, outf, &filesha,
			   FALSE || sizeof(buf)==used);
	    if (rv < 0)
		return FALSE;
	    ofs += rv;
	} while (rv > 0);
	used -= ofs;
	memmove(buf, buf+ofs, used);
	ofs = 0;
    }
    do {
	rv = _do_block(buf+ofs, used-ofs, outf, &filesha, TRUE);
	if (rv < 0)
	    return FALSE;
	ofs += rv;
    } while (rv > 0);
    
    if (got < 0)
    {
	xperror("fread");
	return FALSE;
    }
    
    {
	byte sha[20];
	blk_SHA1_Final(sha, &filesha);
	if (fwrite(sha, 1, sizeof(sha), outf) != sizeof(sha))
	{
	    xperror("fwrite");
	    return FALSE;
	}
    }
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
