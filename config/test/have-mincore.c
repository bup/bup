
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    BUF_TYPE buf[32];
    const long sc_page_size = sysconf(_SC_PAGESIZE);
    return mincore(main, sc_page_size, buf);
}
