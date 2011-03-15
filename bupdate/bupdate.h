#ifndef __BUPDATE_H
#define __BUPDATE_H

#ifdef __cplusplus
extern "C" {
#endif
    
typedef void bupdate_log_t(const char *s);
typedef void bupdate_progress_t(long long bytes, long long total_bytes,
				const char *s);
typedef void bupdate_voidfunc_t();
    
struct bupdate_callbacks {
    bupdate_log_t *log;
    bupdate_progress_t *progress;
    bupdate_voidfunc_t *progress_done;
};
    
int bupdate(const char *baseurl, struct bupdate_callbacks *callbacks);
    
#ifdef __cplusplus
}
#endif

#endif // __BUPDATE_H
