#include "httpget.h"
#include <curl/curl.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <unistd.h>

WvError _http_get(WvBuf &buf, WvStringParm url, int startbyte, int bytelen)
{
    return WvError().set("http not supported on unix yet");
}


int xmain(int argc, char **argv)
{
    CURLM *multi_handle;
    CURL *url1, *url2;
    
    int still_running; /* keep number of running handles */
    
    multi_handle = curl_multi_init();
    url1 = curl_easy_init();
    url2 = curl_easy_init();
    
    curl_easy_setopt(url1, CURLOPT_URL, "http://www.haxx.se/");
    curl_easy_setopt(url2, CURLOPT_URL, "http://apenwarr.ca/");
    curl_multi_add_handle(multi_handle, url1);
    curl_multi_add_handle(multi_handle, url2);
    
    /* we start some action by calling perform right away */
    while (CURLM_CALL_MULTI_PERFORM ==
	   curl_multi_perform(multi_handle, &still_running))
	;
    
    while (still_running)
    {
	struct timeval timeout;
	int rc;
	
	fd_set rfd, wfd, xfd;
	int maxfd = 0;
	
	FD_ZERO(&rfd);
	FD_ZERO(&wfd);
	FD_ZERO(&xfd);
	
	timeout.tv_sec = 1;
	timeout.tv_usec = 0;
	
	curl_multi_fdset(multi_handle, &rfd, &wfd, &xfd, &maxfd);
	rc = select(maxfd+1, &rfd, &wfd, &xfd, &timeout);
	
	switch(rc) {
	case -1:
	    /* select error */
	    still_running = 0;
	    printf("select() returns error, this is badness\n");
	    break;
	case 0:
	default:
	    /* timeout or readable/writable sockets */
	    while(CURLM_CALL_MULTI_PERFORM ==
		  curl_multi_perform(multi_handle, &still_running));
	    break;
	}
    }
    
    curl_easy_cleanup(url1);
    curl_easy_cleanup(url2);
    curl_multi_cleanup(multi_handle);
    return 0;
}
