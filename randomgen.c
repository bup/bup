#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <assert.h>

int main(int argc, char **argv)
{
    if (argc != 2)
    {
	fprintf(stderr, "usage: %s <kbytes>\n", argv[0]);
	return 1;
    }
    
    int kbytes = atoi(argv[1]);
    uint32_t buf[1024/4];
    ssize_t written;
    int i;
    
    for (; kbytes > 0; kbytes--)
    {
	for (i = 0; i < sizeof(buf)/sizeof(buf[0]); i++)
	    buf[i] = random();
	written = write(1, buf, sizeof(buf));
	assert(written = sizeof(buf)); // we'd die from SIGPIPE otherwise
	if (!(kbytes%1024))
	    fprintf(stderr, ".");
    }
    
    return 0;
}
