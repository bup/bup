#ifndef __BIGFILE_H
#define __BIGFILE_H

#include "wvcomstatus.h"
#include <stdio.h>
#include <assert.h>
#include <errno.h>


class BigFile
{
    WvString filename;
    FILE *f;
public:
    BigFile(WvStringParm _filename, const char *mode)
	: filename(_filename)
    {
	errno = 0;
	f = fopen(filename, mode);
	if (!f)
	{
	    WvComStatus(filename).set("fopen", errno);
	    return;
	}
    }
    
    void close()
    {
	if (f)
	{
	    fclose(f);
	    f = NULL;
	}
    }
    
    ~BigFile()
    {
	close();
    }
    
    size_t read(void *buf, size_t len)
    {
	if (f)
	{
	    assert(len >= 0);
	    errno = 0;
	    size_t got = fread(buf, 1, len, f);
	    if (errno)
	    {
		WvComStatus(filename).set("fread", errno);
		return 0;
	    }
	    return got;
	}
	return 0;
    }
    
    void write(const void *buf, size_t len)
    {
	if (f)
	{
	    assert(len >= 0);
	    errno = 0;
	    size_t wrote = fwrite(buf, 1, len, f);
	    if (errno || wrote != len)
	    {
		WvComStatus(filename).set("short fwrite", errno);
		return;
	    }
	}
    }
    
    void seek(off64_t ofs, int whence)
    {
	if (f)
	{
	    errno = 0;
	    int rv = fseeko64(f, ofs, whence);
	    if (rv != 0)
	    {
		WvComStatus(filename).set("fseek", errno);
		return;
	    }
	}
    }
    
    off64_t tell()
    {
	if (f)
	{
	    errno = 0;
	    off64_t rv = ftello64(f);
	    if (rv < 0)
	    {
		WvComStatus(filename).set("ftell", errno);
		return -1;
	    }
	    return rv;
	}
	return 0;
    }
};


#endif // __BIGFILE_H
