#include "bupdate.h"
#include <stdio.h>


static void simple_print(const char *s)
{
    printf("%s", s);
    fflush(stdout);
}


int main(int argc, char **argv)
{
    if (argc != 2)
    {
	fprintf(stderr, "usage: %s <url>\n", argv[0]);
	return 1;
    }
    
    return bupdate(argv[1], simple_print);
}
