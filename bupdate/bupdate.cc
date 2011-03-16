#include "progress.h"
#include "bigfile.h"
#include "bupdate.h"
#include "httpget.h"
#include "fidx.h"
#include "wvcomstatus.h"
#include "wvbuf.h"
#include "wvstringlist.h"
#include "wvstrutils.h"
#include "wvdiriter.h"
#include <unistd.h>
#include <errno.h>
#include <sys/types.h>
#include <utime.h>

#define MAX_QUEUE_SIZE (1*1024*1024)

typedef unsigned char  byte;

// reassign this to change progress message printing functions
static struct bupdate_callbacks *callbacks;


void print(WvStringParm s)
{
    if (callbacks && callbacks->log)
	callbacks->log(s);
}


void print(WVSTRING_FORMAT_DECL)
{
    print(WvString(WVSTRING_FORMAT_CALL));
}


void progress(long long bytes, long long total_bytes,
	      WvStringParm status)
{
    if (callbacks && callbacks->progress)
	callbacks->progress(bytes, total_bytes, status);
}


void progress_done()
{
    if (callbacks && callbacks->progress_done)
	callbacks->progress_done();
}


WvError _file_get(WvBuf &buf, WvStringParm filename,
	       int startbyte, int bytelen)
{
    WvComStatus errb;
    
    BigFile f(filename, "rb");
    if (!errb.isok()) return errb;
    
    f.seek(0, SEEK_END);
    off64_t filesize = f.tell();
    
    WvComStatus err(filename);
    if (startbyte < 0)
	return err.set("startbyte must be >= 0");
    if (startbyte >= filesize)
	return err.set("startbyte(%s) must be <= filesize(%s)",
		       startbyte, filesize);
    if (!(bytelen == -1 || bytelen > 0))
	return err.set("bytelen(%s) must be -1 or >0", bytelen);
    if (bytelen>0 && startbyte+bytelen > filesize)
	return err.set("startbyte(%s)+bytelen(%s) >= filesize(%s)",
		       startbyte, bytelen, filesize);
    
    f.seek(startbyte, SEEK_SET);
    if (bytelen < 0)
	bytelen = filesize - startbyte;
    byte *p = buf.alloc(bytelen);
    ssize_t len = f.read(p, bytelen);
    if (len != bytelen)
    {
	buf.unalloc(bytelen);
	err.set("read: expected %s bytes, got %s", bytelen, len);
    }
    return err;
}


WvError http_get(WvBuf &buf, WvStringParm url, int startbyte, int bytelen)
{
    //print("    getting %s (%s,%s)\n", url, startbyte, bytelen);
    if (url.startswith("file://"))
	return _file_get(buf, url+7, startbyte, bytelen);
    else
	return _http_get(buf, url, startbyte, bytelen);
}


WvString http_get_str(WvStringParm url)
{
    WvComStatus err(WvString("http(%s)", url));
    WvDynBuf b;
    err.set(http_get(b, url, 0, -1));
    if (err.isok())
	return b.getstr();
    else
	return WvString::null;
}


void http_get_to_file(WvStringParm filename, WvStringParm url)
{
    WvDynBuf b;
    WvComStatus err;
    err.set(http_get(b, url, 0, -1));
    if (!err.isok())
	return;
    size_t len = b.used();
    
    //print("Writing to: %s (%s bytes)\n", filename, b.used());
    BigFile f(filename, "wb");
    if (!err.isok()) return;
    f.write(b.get(len), len);
}


bool is_url(WvStringParm s)
{
    return strstr(s, "://");
}


void targets_from_file(WvStringList &l, WvStringParm s)
{
    if (s.startswith("<"))
    {
	// it's HTML; pick out the anchors
	const char *cptr = s;
	while (cptr)
	{
	    cptr = strstr(cptr, "<a href=");
	    if (!cptr)
		break;
	    cptr += 8;
	    char quote = *cptr;
	    if (quote != '/' && quote != '\"')
		continue;
	    cptr++;
	    const char *eptr = strchr(cptr, quote);
	    if (!eptr)
		continue;
	    WvString ns;
	    size_t len = eptr-cptr;
	    ns.setsize(len+1);
	    char *optr = ns.edit();
	    strncpy(optr, cptr, len);
	    optr[len] = 0;
	    l.append(url_decode(ns));
	}
    }
    else
    {
	// it's not HTML; assume it's a one-per-line list of filenames
	l.split(s, "\n");
    }
}


WvString readfile_str(WvStringParm filename)
{
    byte buf[65536];
    WvDynBuf b;
    WvComStatus err;
    
    BigFile f(filename, "rb");
    if (!err.isok()) return WvString::null;
    size_t len;
    while ((len = f.read(buf, sizeof(buf))) >= 1)
	b.put(buf, len);
    return b.getstr();
}


bool exists(WvStringParm filename)
{
    struct stat st;
    return stat(filename, &st) == 0;
}


class Fidx;


struct FidxMapping
{
    Fidx *fidx;
    Sha sha;
    size_t ofs, size;
};


void eatsuffix(WvString &s, WvStringParm suffix)
{
    if (s.endswith(suffix))
    {
	char *cptr = s.edit();
	cptr[s.len() - suffix.len()] = 0;
    }
}


class Fidx
{
public:
    WvString filename, fidxname;
    WvDynBuf buf;
    const byte *bytes;
    WvError err;
    Sha filesha;
    size_t filesize;
    bool mismatch_ok;
    
    Fidx(WvStringParm _name, bool _mismatch_ok) 
	: filename(_name), fidxname(_name)
    {
	mismatch_ok = _mismatch_ok;
	eatsuffix(filename, ".fidx");
	refresh();
    }
    
    void refresh()
    {
	buf.zap();
	err.noerr();
	
	WvComStatusIgnorer ig; // any errors in here don't propagate out
	err.set("fidx", _file_get(buf, fidxname, 0, -1));
	bytes = NULL;
	filesize = 0;
	if (!mismatch_ok)
	{
	    if (!exists(filename))
	    {
		err.set_both(ENOENT, "%s does not exist", filename);
		return;
	    }
	
	    struct stat st1, st2;
	    if (stat(filename, &st1) != 0)
		err.set(filename, errno);
	    if (stat(fidxname, &st2) != 0)
		err.set(fidxname, errno);
	    if (err.isok() && st1.st_mtime != st2.st_mtime)
		err.set("file mtime doesn't match its fidx");
	    if (!err.isok())
		return;
	}
	
	if (buf.used() < sizeof(FidxHdr)+20)
	{
	    err.set(".fidx length < len(FidxHdr)"); 
	    return;
	}
	
	quick_sha(filesha.sha, buf.peek(0, buf.used()), buf.used()-20);
	
	FidxHdr *h = (FidxHdr *)buf.get(sizeof(FidxHdr));
	assert(h);
	if (memcmp(h->marker, "FIDX", 4) != 0)
	{
	    err.set(".fidx has invalid FIDX header");
	    return;
	}
	uint32_t ver = ntohl(h->ver);
	if (ver != FIDX_VERSION)
	{
	    err.set(".fidx: got version %s, wanted %s", ver, FIDX_VERSION);
	    return;
	}
	
	bytes = buf.peek(0, buf.used());
	assert(bytes);
	
	Sha filesha_expect = *(Sha *)(bytes + buf.used() - 20);
	buf.unalloc(20);
	if (filesha_expect != filesha)
	{
	    err.set(".fidx: fidx sha1 does not match stored sha1");
	    return;
	}
	
	int ln = len();
	for (int e = 0; e < ln; e++)
	    filesize += ntohs(get(e)->size);
    }
    
    void regen()
    {
	err.noerr();
	print("    Regenerating index for %s.\n", filename);
	int rv = fidx(filename, callbacks);
	if (rv != 0)
	    err.set("fidx regeneration for %s failed", filename);
	else
	    refresh();
    }
    
    int len() const
    {
	return buf.used() / sizeof(FidxEntry);
    }
    
    FidxEntry *get(int elem) const
    {
	assert(elem >= 0);
	assert(elem < len());
	return (FidxEntry *)(bytes + elem*sizeof(FidxEntry));
    }
};

DeclareWvList(Fidx);


static int _fidx_mapping_compare(const void *_a, const void *_b)
{
    FidxMapping *a = (FidxMapping *)_a;
    FidxMapping *b = (FidxMapping *)_b;
    return memcmp(&a->sha, &b->sha, sizeof(a->sha));
}


static int _fidx_mapping_search(const void *_key, const void *_member)
{
    Sha *key = (Sha *)_key;
    FidxMapping *member = (FidxMapping *)_member;
    return memcmp(key, &member->sha, sizeof(member->sha));
}


class FidxMappings
{
public:
    FidxMapping *list;
    int count;
    
    FidxMappings(FidxList &l)
    {
	count = 0;
	FidxList::Iter i(l);
	for (i.rewind(); i.next(); )
	    count += i->len();
	
	list = new FidxMapping[count];
	
	int o = 0;
	for (i.rewind(); i.next(); )
	{
	    int len = i->len();
	    size_t ofs = 0;
	    for (int e = 0; e < len; e++)
	    {
		FidxEntry *ent = i->get(e);
		FidxMapping *m = list + (o++);
		memset(m, 0, sizeof(*m));
		m->fidx = i.ptr();
		m->sha = ent->sha;
		m->ofs = ofs;
		m->size = ntohs(ent->size);
		assert(m->ofs <= i->filesize);
		assert(m->ofs + ntohs(ent->size) <= i->filesize);
		ofs += ntohs(ent->size);
	    }
	}
	
	print("Mappings: %s total objects loaded.\n", count);
	qsort(list, count, sizeof(FidxMapping), _fidx_mapping_compare);
	print("Mappings sorted.\n", count);
    };
    
    ~FidxMappings()
    {
	delete[] list;
    }
    
    FidxMapping *find(Sha &sha)
    {
	return (FidxMapping *)bsearch(&sha, list, count, sizeof(FidxMapping),
				      _fidx_mapping_search);
    }
};


struct DlQueue
{
    size_t ofs, size;
};


static void flushq(BigFile &outf, DlQueue &q, WvStringParm url,
		   size_t &got, size_t missing)
{
    if (q.size)
    {
	WvComStatus err("flushq");
	WvDynBuf b;
	err.set(http_get(b, url, q.ofs, q.size));
	got += q.size;
	if (b.used() == q.size)
	    outf.write(b.get(q.size), q.size);
	q.ofs = q.size = 0;
	//progress(got, missing, "Downloading...");
    }
}


int bupdate(const char *_baseurl, bupdate_callbacks *_callbacks)
{
    callbacks = _callbacks;
    
    WvComStatus err("bupdate");
    WvString baseurl(_baseurl);
    for (char *cptr = baseurl.edit(); cptr && *cptr; cptr++)
	if (*cptr == '\\')
	    *cptr = '/';
    
    WvStringList targets;
    if (baseurl.endswith(".fidx"))
    {
	// the baseurl is a particular fidx, not a file list, so just use
	// a file list of one.
	targets.append(getfilename(baseurl));
    }
    else if (is_url(baseurl))
    {
	// it's an actual URL; download it
	print("Downloading base: %s\n", baseurl);
	WvString s = http_get_str(baseurl);
	// FIXME: what if we got http redirected?  We should save the new url
	targets_from_file(targets, s);
    }
    else
    {
	// not an URL, so it's a disk file
	struct stat st;
	while (baseurl.endswith("/"))
	    *strrchr(baseurl.edit(), '/') = 0;
	if (stat(baseurl, &st) != 0)
	    err.set("stat", errno);
	else if (S_ISDIR(st.st_mode))
	{
	    // a directory
	    print("it's a dir\n");
	    WvDirIter di(baseurl, false);
	    for (di.rewind(); di.next(); )
		targets.append(di->name);
	    if (!baseurl.endswith("/"))
		baseurl.append("/");
	}
	else
	{
	    // an index file
	    print("it's a file\n");
	    targets_from_file(targets, readfile_str(baseurl));
	}
	baseurl = WvString("file://%s", baseurl);
    }
    
    if (!baseurl.endswith("/"))
	baseurl = getdirname(baseurl);
    while (baseurl.endswith("/"))
	*strrchr(baseurl.edit(), '/') = 0;
    if (!is_url(baseurl))
	baseurl = WvString("file://%s", baseurl);
    
    {
	WvStringList::Iter i(targets);
	for (i.rewind(); i.next(); )
	{
	    *i = trim_string(i->edit());
	    if (!*i || i->startswith(".") || !i->endswith(".fidx"))
		i.xunlink();
	}
    }
    
    print("baseurl is: '%s'\n"
	  "Targets (%s):\n",
	  baseurl, targets.count());
    {
	WvStringList::Iter i(targets);
	for (i.rewind(); i.next(); )
	    print("    '%s'\n", *i);
    }
    
    if (targets.isempty())
	err.set("no target names found in baseurl");
    
    // load existing fidxes
    print("Reading existing fidx files.\n");
    FidxList fidxes;
    {
	WvDirIter di(".", true);
	for (di.rewind(); di.next(); )
	{
	    if (di->name.endswith(".fidx") || di->name.endswith(".tmp"))
		continue;
	    WvString fidxname("%s.fidx", di->relname);
	    Fidx *f = new Fidx(fidxname, true);
	    if (!f->err.isok())
	    {
		print("    %s: %s\n", fidxname, f->err.str());
		f->regen();
	    }
	    if (f->err.isok())
	    {
		print("    %s\n", fidxname);
		fidxes.append(f, true);
	    }
	    else
		delete f;
	}
    }
    FidxMappings mappings(fidxes);
    
    WvStringList::Iter i(targets);
    for (i.rewind(); i.next(); )
    {
	print("\n%s\n", *i);
	assert(!strchr(*i, '/'));
	assert(i->endswith(".fidx"));
	WvString fidxname = *i;
	WvString tmpname("%s.tmp", fidxname);
	WvString outname = fidxname;
	outname.edit()[outname.len()-5] = 0;  // remove .fidx
	WvString outtmpname("%s.tmp", outname);
	WvComStatus errx(outname);
	
	http_get_to_file(tmpname, WvString("%s/%s", baseurl, fidxname));
	if (!errx.isok())
	{
	    print("    error: %s\n", errx.str());
	    continue;
	}
	
	Fidx fidx(tmpname, true), oldfidx(fidxname, true);

	if (!oldfidx.err.isok() && oldfidx.err.get() != ENOENT)
	    print("    old fidx: %s\n", oldfidx.err.str());
	
	if (oldfidx.err.isok() && fidx.err.isok() &&
	    fidx.filesha == oldfidx.filesha)
	{
	    print("    already up to date.\n");
	    unlink(tmpname);
	    unlink(outtmpname);
	    continue;
	}
	
	print("    changed! (old=%s, new=%s)\n",
	      oldfidx.err.isok(), fidx.err.isok());
	
	if (!fidx.err.isok())
	{
	    print("    skipping: %s\n", fidx.err.str());
	    continue;
	}
	
	// predict the download
	int len = fidx.len();
	size_t missing = 0, chunks = 0, ofs = 0;
	for (int e = 0; e < len; e++)
	{
	    FidxEntry *ent = fidx.get(e);
	    FidxMapping *m = mappings.find(ent->sha);
	    if (!m)
	    {
		//print("        %-10s %s\n", ofs, ntohs(ent->size));
		missing += ntohs(ent->size);
		chunks++;
	    }
	    ofs += ntohs(ent->size);
	}
	print("    need to download %s/%s bytes in %s chunks.\n",
	      missing, fidx.filesize, chunks);
	
	// do the download
	BigFile outf(outtmpname, "wb");
	if (!errx.isok())
	    continue;
	size_t rofs = 0, got = 0;
	DlQueue queue = {0,0};
	WvString url("%s/%s", baseurl, outname);
	WvDynBuf b;
	for (int e = 0; e < len && errx.isok(); e++)
	{
	    FidxEntry *ent = fidx.get(e);
	    size_t esz = ntohs(ent->size);
	    FidxMapping *m = mappings.find(ent->sha);
	    if (m)
	    {
		flushq(outf, queue, url, got, missing);
		assert(m->size == esz);
		{
		    WvComStatusIgnorer ig;
		    _file_get(b, m->fidx->filename, m->ofs, m->size);
		}
		size_t amt = b.used();
		if (amt)
		{
		    const byte *buf = b.get(amt);
		    Sha sha;
		    blob_sha(sha.sha, buf, amt);
		    if (sha == ent->sha)
			outf.write(buf, amt);
		    else
		    {
			print("    checksum mismatch @%s (%s)              \n",
			      m->ofs, m->size);
			m = NULL;
		    }
		}
		else
		    m = NULL;
	    }
	    if (!m)
	    {
		if (queue.size && (queue.ofs+queue.size != rofs
				   || queue.size > MAX_QUEUE_SIZE))
		    flushq(outf, queue, url, got, missing);
		if (!queue.size)
		    queue.ofs = rofs;
		queue.size += esz;
	    }
	    rofs += esz;
	    if ((e % 64) == 0)
		progress(outf.tell(), fidx.filesize,
			 "Downloading components...");
	}
	flushq(outf, queue, url, got, missing);
	outf.close();
	progress_done();
	
	if (errx.isok())
	{
	    unlink(fidxname);
	    unlink(outname);
	    if (rename_overwrite(outtmpname, outname) == 0 &&
		rename_overwrite(tmpname, fidxname) == 0)
	    {
		time_t now = time(NULL);
		struct utimbuf tb = { now, now };
		utime(outname, &tb);
		utime(fidxname, &tb);
	    }
	}
    }
    
    if (!err.isok())
    {
	print("\nerror was:\n%s\n", err.str());
	return 1;
    }
    return 0;
}


