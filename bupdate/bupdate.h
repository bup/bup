#ifndef __BUPDATE_H
#define __BUPDATE_H

#ifdef __cplusplus
extern "C" {
#endif
    
typedef void bupdate_progress_t(const char *s);
    
int bupdate(const char *baseurl, bupdate_progress_t *progress);
    
#ifdef __cplusplus
}
#endif

#endif // __BUPDATE_H
