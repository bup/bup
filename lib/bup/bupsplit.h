#ifndef __BUPSPLIT_H
#define __BUPSPLIT_H

#define BUP_BLOBBITS (13)
#define BUP_BLOBSIZE (1<<BUP_BLOBBITS)
#define BUP_WINDOWBITS (7)
#define BUP_WINDOWSIZE (1<<(BUP_WINDOWBITS-1))

#ifdef __cplusplus
extern "C" {
#endif
    
int bupsplit_find_ofs(const unsigned char *buf, int len, int *bits);
int bupsplit_selftest(void);

#ifdef __cplusplus
}
#endif
    
#endif /* __BUPSPLIT_H */
