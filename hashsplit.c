#include <stdio.h>
#include <stdint.h>
#include <assert.h>
#include <memory.h>

#define BLOBBITS (14)
#define BLOBSIZE (1<<(BLOBBITS-1))
#define WINDOWBITS (7)
#define WINDOWSIZE (1<<(WINDOWBITS-1))


// FIXME: replace this with a not-stupid rolling checksum algorithm,
// such as the one used in rsync (Adler32?)
static uint32_t stupidsum_add(uint32_t old, uint8_t drop, uint8_t add)
{
    return ((old<<1) | (old>>31)) ^ drop ^ add;
}


static void test_sums()
{
    uint32_t sum = 0;
    int i;
    
    for (i = 0; i < WINDOWSIZE; i++)
	sum = stupidsum_add(sum, 0, i%256);
    uint32_t sum1 = sum;
    
    for (i = 0; i < WINDOWSIZE; i++)
	sum = stupidsum_add(sum, i%256, i%256);
    assert(sum1 == sum);
    
    for (i = 0; i < WINDOWSIZE; i++)
	sum = stupidsum_add(sum, i%256, 0);
    assert(sum == 0);
}


int main()
{
    assert(WINDOWSIZE >= 32);
    assert(BLOBSIZE >= 32);
    test_sums();
    
    uint8_t buf[WINDOWSIZE];
    uint32_t sum = 0;
    int i = 0, count = 0, c;
    FILE *pipe = NULL;
    
    memset(buf, 0, sizeof(buf));
    
    while ((c = fgetc(stdin)) != EOF)
    {
	sum = stupidsum_add(sum, buf[i], c);
	buf[i] = c;
	
	if (0)
	{
	    int j;
	    fprintf(stderr, "[%5X] %08X  '", i, sum);
	    for (j = i+1; j < i+1+WINDOWSIZE; j++)
	    {
		int d = buf[j % WINDOWSIZE];
		fputc((d >= 32 && d <= 126) ? d : '.', stderr);
	    }
	    fprintf(stderr, "'\n");
	}
	
	i = (i + 1) % WINDOWSIZE;
	count++;
	
	if ((sum & (BLOBSIZE-1)) == 0)
	{
	    fprintf(stderr, "SPLIT @ %-8d (%d/%d)\n",
		    count, BLOBSIZE, WINDOWSIZE);
	    i = 0;
	    memset(buf, 0, sizeof(buf));
	    sum = 0;
	    if (pipe)
	    {
		fflush(stderr);
		pclose(pipe);
		pipe = NULL;
	    }
	}
	
	if (!pipe)
	    pipe = popen("git hash-object --stdin -w", "w");
	fputc(c, pipe);
    }
    
    if (pipe)
	pclose(pipe);
    
    return 0;
}
