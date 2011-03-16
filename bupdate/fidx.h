#ifndef __FIDX_H
#define __FIDX_H

#include <stdint.h>
#include <stdio.h>

#ifdef __WIN32__
#include <winsock.h>
#else
#include <arpa/inet.h>
#endif

#define FIDX_VERSION 1

// FIXME duplicated with content in hashsplit.py
#define BLOB_MAX (8192*4)
#define BLOB_READ_SIZE (1024*1024)
#define FANOUT_BITS 4

#define msg(fmt, args...) fprintf(stderr, fmt, ##args)
#define xperror(s) do { perror(s); errcount++; } while (0)

#ifndef __cplusplus
typedef int bool;
#endif

typedef unsigned char  byte;
#define TRUE 1
#define FALSE 0

struct Sha
{
    byte sha[20];
    
    #ifdef __cplusplus
    bool operator== (Sha &s) const
        { return memcmp(this, &s, sizeof(this)) == 0; }
    #endif
};

struct FidxHdr
{
    byte marker[4];
    uint32_t ver;
};

struct FidxEntry
{
    struct Sha sha;
    uint16_t size;
    uint16_t level;
};

#ifdef __cplusplus
extern "C" {
#endif
    
int rename_overwrite(const char *oldname, const char *newname);

void quick_sha(byte sha[20], const byte *buf, int len);
void blob_sha(byte sha[20], const byte *buf, int len);

bool fwrite_fidx(FILE *outf, FILE *inf);
int fidx(const char *filename);

#ifdef __cplusplus
}
#endif

#endif // __FIDX_H
