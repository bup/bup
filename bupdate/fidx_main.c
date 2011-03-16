#include "fidx.h"
#include "bupsplit.h"
#include "sha1.h"

int main(int argc, char **argv)
{
    int i, errcount = 0;
    for (i = 1; i < argc; i++)
	errcount += fidx(argv[i]);
    
    if (errcount)
    {
	msg("WARNING: %d errors encountered while hashing.\n", errcount);
	return 1;
    }
    else
	return 0;
}
