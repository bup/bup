#include "bupdate.h"
#include <stdio.h>


static void simple_print(const char *s)
{
    fprintf(stderr, "%s", s);
    fflush(stderr);
}


static void simple_progress(long long bytes, long long total,
			    const char *s)
{
    
    fprintf(stderr, "    %.2f/%.2f Mbytes - %-50.40s\r",
	    bytes/1024./1024., total/1024./1024., s);
    fflush(stderr);
}


static void simple_progress_done()
{
    fprintf(stderr, "    %-70s\r", "");
    fflush(stderr);
}


struct bupdate_callbacks callbacks = {
    simple_print,
    simple_progress,
    simple_progress_done,
};


int main(int argc, char **argv)
{
    if (argc != 2)
    {
	fprintf(stderr, "usage: %s <url>\n", argv[0]);
	return 1;
    }
    
    return bupdate(argv[1], &callbacks);
}
