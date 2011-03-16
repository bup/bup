#include "bupdate.h"
#include <stdio.h>
#include <windows.h>
#include <commctrl.h>
#include "nsis/exdll.h"

#define WCLASS_DIALOG "#32770"  // windows global dialog box class id
#define IDC_PROGRESS  1004  // progress bar in the nsis window
#define IDC_INTROTEXT 1006  // status text in the nsis window
#define IDC_LIST1     1016  // details listbox

static HWND hdlg, hstatus, hprogress, hlist;
static int prog_start, prog_count;


static void _print(const char *s)
{
    LVITEM it;
    memset(&it, 0, sizeof(it));
    
    it.iItem = SendMessage(hlist, LVM_GETITEMCOUNT, 0, 0) + 1;
    it.pszText = (char *)s;
    it.mask = LVIF_TEXT;
    it.stateMask = LVIS_FOCUSED;
    it.state = LVIS_FOCUSED;
    
    SendMessage(hlist, LVM_INSERTITEM, 0, (long)&it);
    SendMessage(hlist, LVM_SCROLL, 0, 12);
}


static void print(const char *_s)
{
    char *s, *sptr, *eptr;
    s = sptr = eptr = strdup(_s);
    while (eptr && *eptr)
    {
	eptr = strchr(sptr, '\n');
	if (eptr)
	{
	    *eptr = 0;
	    _print(sptr);
	    *eptr = '\n';
	    sptr = eptr+1;
	}
	else if (*sptr)
	    _print(sptr);
    }
    free(s);
}


static void status(const char *s)
{
    SetWindowText(hstatus, s);
}


static void _progress(long long bytes, long long total_bytes)
{
    if (total_bytes == 0) total_bytes = bytes = 1;
    SendMessage(hprogress, PBM_SETPOS,
		prog_start + prog_count*bytes/total_bytes,
		0);
}


static void progress(long long bytes, long long total_bytes,
		     const char *s)
{
    char buf[1024];
    _progress(bytes, total_bytes);
    snprintf(buf, sizeof(buf)-1, "%s (%.1f/%.1f Mbytes)",
	     s, bytes/1024./1024., total_bytes/1024./1024.);
    buf[sizeof(buf)-1] = 0;
    status(buf);
}


static void progress_done()
{
    status("Done.");
    _progress(1, 1);
}


struct bupdate_callbacks callbacks = {
    print,
    progress,
    progress_done,
};


static void _do_test(const char *url)
{
    int i;
    for (i = 0; i <= 5; i++)
    {
	progress(i*1024*1024, 5*1024*1024, "Segment");
	Sleep(250);
    }
    progress_done();
}


void nsis(HWND hwnd, int string_size, char *variables,
	  stack_t **stacktop, extra_parameters *extra)
{
    int is_test = 0;
    char url[string_size], buf[string_size];
    
    EXDLL_INIT();
    hdlg = FindWindowEx(hwnd, NULL, WCLASS_DIALOG, NULL);
    hstatus = GetDlgItem(hdlg, IDC_INTROTEXT);
    hprogress = GetDlgItem(hdlg, IDC_PROGRESS);
    hlist = GetDlgItem(hdlg, IDC_LIST1);
    
    do
    {
	if (popstring(url) != 0)
	    url[0] = 0;
	if (stricmp(url, "/test") == 0)
	    is_test = 1;
    } while (stricmp(url, "/test") == 0);
    
    sprintf(buf, "Download: %.900s", url);
    print(buf);
    
    //prog_start = (int)SendMessage(hprogress, PBM_GETPOS, 0, 0);
    prog_start = (popstring(buf)==0 ? atoi(buf) : 0) * 30000/100;
    prog_count = (popstring(buf)==0 ? atoi(buf) : 0) * 30000/100;
    prog_count -= prog_start;
    if (prog_count < 0)
	prog_count = 0;
    
    if (is_test)
    {
	_do_test(url);
	pushstring("0");
    }
    else
    {
	char buf[100];
	sprintf(buf, "%d", bupdate(url, &callbacks));
	pushstring(buf);
    }
}
