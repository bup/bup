
#include <stdio.h>
#include <sys/acl.h>
#include <acl/libacl.h>

int main(int argc, char **argv)
{
    printf("%p\n", acl_from_text);
    printf("%p\n", acl_get_file);
    printf("%p\n", acl_set_file);
    //These are linux specific, but we need them (for now?)
    printf("%p\n", acl_extended_file);
    printf("%p\n", acl_to_any_text);
    return 0;
}
