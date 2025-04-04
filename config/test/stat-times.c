
#include <sys/stat.h>

int main(int argc, char **argv)
{
    struct stat st;
    stat(argv[0], &st);
    return (int) st.BUP_TIME_FIELD;
}
