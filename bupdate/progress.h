#ifndef __PROGRESS_H
#define __PROGRESS_H

typedef void bupdate_log_t(const char *s);
typedef void bupdate_progress_t(long long bytes, long long total_bytes,
				const char *s);
typedef void bupdate_voidfunc_t();
    
struct bupdate_callbacks {
    bupdate_log_t *log;
    bupdate_progress_t *progress;
    bupdate_voidfunc_t *progress_done;
};
    
#endif // __PROGRESS_H
