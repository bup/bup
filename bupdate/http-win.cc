#include "wvstring.h"

int main()
{
    WvString s("foo");
    printf("'%s'\n", s.cstr());
    return 0;
}
