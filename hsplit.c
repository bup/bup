#include <stdio.h>
#include <stdint.h>
#include <assert.h>
#include <memory.h>

#define BLOBBITS (14)
#define BLOBSIZE (1<<(BLOBBITS-1))
#define WINDOWBITS (7)
#define WINDOWSIZE (1<<(WINDOWBITS-1))


static uint32_t rol(uint32_t v, unsigned bits)
{
    bits = bits % 32;
    return (v << bits) | (v >> (32-bits));
}


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
    assert(rol(1,0) == 1);
    assert(rol(1,1) == 2);
    assert(rol(1,32) == 1);
    assert(rol(1,33) == 2);
    assert(rol(0x12345678, 16) == 0x56781234);
    assert(rol(0x12345678, 34) == 0x48d159e0);
    assert(rol(0x92345678, 34) == 0x48d159e2);
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
	
	//int cprint = (c >= 32 && c <= 126) ? c : '.';
	//fprintf(stderr, "[%05X] %02X '%c' %08X\n", i, c, cprint, sum);
	
	i = (i + 1) % WINDOWSIZE;
	count++;
	
	if ((sum & (BLOBSIZE-1)) == 0)
	{
	    fprintf(stderr, "SPLIT @ %d (%d)\n", count, BLOBSIZE);
	    count = i = 0;
	    memset(buf, 0, sizeof(buf));
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
