
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    return (int) MINCORE_INCORE;
}
