#ifndef __BUPDATE_H
#define __BUPDATE_H

#ifdef __cplusplus
extern "C" {
#endif
    
struct bupdate_callbacks;
    
int bupdate(const char *baseurl, struct bupdate_callbacks *callbacks);
    
#ifdef __cplusplus
}
#endif

#endif // __BUPDATE_H
