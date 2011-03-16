#include "fidx.h"
#include "progress.h"
#include "bupsplit.h"
#include "sha1.h"


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


static struct bupdate_callbacks callbacks = {
    simple_print,
    simple_progress,
    simple_progress_done,
};


int main(int argc, char **argv)
{
    int i, errcount = 0;
    for (i = 1; i < argc; i++)
	errcount += fidx(argv[i], &callbacks);
    
    if (errcount)
    {
	msg("WARNING: %d errors encountered while hashing.\n", errcount);
	return 1;
    }
    else
	return 0;
}
