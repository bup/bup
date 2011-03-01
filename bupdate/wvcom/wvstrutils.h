/* -*- Mode: C++ -*-
 * Worldvisions Weaver Software:
 *   Copyright (C) 1997-2002 Net Integration Technologies, Inc.
 *
 * Various little string functions...
 * 
 * FIXME: and some other assorted crap that belongs anywhere but here.
 */
#ifndef __WVSTRUTILS_H
#define __WVSTRUTILS_H

#include <sys/types.h> // for off_t
#include <time.h>
#include <ctype.h>
#include "wvstring.h"
#include "wvstringlist.h"
#ifndef _WIN32
#include "wvregex.h"
#endif

/** \file
 * Various little string functions
 */


/**
 * Add character c to the end of a string after removing 
 * terminating carriage returns/linefeeds if any.
 * 
 * You need a buffer that's at least one character bigger than the 
 * current length of the string, including the terminating NULL. 
 */
char *terminate_string(char *string, char c);

/**
 * Trims whitespace from the beginning and end of the character string, 
 * including carriage return / linefeed characters. Modifies the string 
 * in place. Returns the new first character of the string, which points 
 * either at 'string' itself or some character contained therein.
 *
 * string is allowed to be NULL; returns NULL in that case.
 */
char *trim_string(char *string);

/**
 * Similar to above, but trims the string starting at the first occurrence of
 * c.
 */
char *trim_string(char *string, char c);

/**
 * return the string formed by concatenating string 'a' and string 'b' with
 * the 'sep' character between them.  For example,
 *     spacecat("xx", "yy", ";");
 * returns "xx;yy", and
 *    spacecat("xx;;", "yy", ";")
 * returns "xx;;;yy", and
 *    spacecat("xx;;", "yy", ";", true)
 * returns "xx;yy".
 *
 * This function is much faster than the more obvious WvString("%s;%s", a, b),
 * so it's useful when you're producing a *lot* of string data.
 */
WvString spacecat(WvStringParm a, WvStringParm b, char sep = ' ',
		  bool onesep = false);

    
/**
 * Replaces all whitespace characters in the string with non-breaking spaces
 * (&nbsp;) for use with web stuff.
 */
char *non_breaking(const char *string);

/**
 * Replace all instances of c1 with c2 for the first 'length' characters in 
 * 'string'. Ignores terminating NULL, so make sure you set 'length' correctly.
 */
void replace_char(void *string, char c1, char c2, int length);

/**
 * Snip off the first part of 'haystack' if it consists of 'needle'.
 */
char *snip_string(char *haystack, char *needle);

#ifndef _WIN32
/**
 * In-place modify a character string so that all contained letters are 
 * in lower case. Returns 'string'.
 */
char *strlwr(char *string);

/**
 * In-place modify a character string so that all contained letters are 
 * in upper case. Returns 'string'.
 */
char *strupr(char *string);

#endif

/** Returns true if all characters in 'string' are isalnum() (alphanumeric). */
bool is_word(const char *string);

/**
 * Produce a hexadecimal dump of the data buffer in 'buf' of length 'len'. 
 * It is formatted with 16 bytes per line; each line has an address offset, 
 * hex representation, and printable representation.
 *
 * This is used mostly for debugging purposes. You can send the returned 
 * WvString object directly to a WvLog or any other WvStream for output.
 */
WvString hexdump_buffer(const void *buf, size_t len, bool charRep = true);

/**
 * Returns true if 'c' is a newline or carriage return character. 
 * Increases code readability a bit.
 */
bool isnewline(char c);

/**
 * Unescapes URL-encoded strings (with escape sequences such as %20, etc),
 * such as ones created by url_encode().
 * 
 * If no_space is false, "+" characters will be decoded to spaces, as
 * web servers typically do.  If no_space is true, "+" characters are decoded
 * as "+", and only %-escapes are done.
 */
WvString url_decode(WvStringParm str, bool no_space = false);


/**
 * Escapes strings in "URL style" with %xx sequences for any characters
 * not considered "safe" in a URL.
 * 
 * The default (blank) value of "unsafe" is very paranoid and only allows
 * basic ASCII alphanumerics and a few known-URL-safe punctuation marks.
 * This is even more conservative than RFC 2396, but will still be compatible
 * with any valid URL decoder.
 * 
 * If you specify a non-empty string for the 'unsafe' list, only the
 * characters in the list will be escaped.  You can use this if you want
 * to use URL-style encoding for something other than a URL, such as a
 * filename.
 * 
 * Note: The '%' character is always escaped, as otherwise the string would
 * not be decodable.
 */
WvString url_encode(WvStringParm str, WvStringParm unsafe = "");
 

/**
 * Returns the difference between to dates in a human readable format
 */
WvString  diff_dates(time_t t1, time_t t2);


/**
 * Returns an RFC822-compatible date made out of _when, or, if _when < 0, out of
 * the current time.
 */
WvString rfc822_date(time_t _when = -1);

/** Returns an RFC1123-compatible date made out of _when */
WvString rfc1123_date(time_t _when);

/** Return the local date (TZ applied) out of _when */
WvString local_date(time_t _when = -1);

/** Return the local time (in format of ISO 8601) out of _when */
WvString intl_time(time_t _when = -1);

/** Return the local date (in format of ISO 8601) out of _when */
WvString intl_date(time_t _when = -1);

/** Return the local date and time (in format of ISO 8601) out of _when */
WvString intl_datetime(time_t _when = -1);

time_t intl_gmtoff(time_t t);

#ifndef _WIN32
/**
 * Similar to crypt(), but this randomly selects its own salt.
 * This function is defined in strcrypt.cc.  It chooses to use the DES
 * engine.
 */
WvString passwd_crypt(const char *str);

#endif
/**
 * Similar to crypt(), but this randomly selects its own salt.
 * This function is defined in strcrypt.cc.  It chooses to use the MD5
 * engine.
 */
WvString passwd_md5(const char *str);

/**
 * Returns a string with a backslash in front of every non alphanumeric
 * character in s1.
 */
WvString backslash_escape(WvStringParm s1);

/** How many times does 'c' occur in "s"? */
int strcount(WvStringParm s, const char c);

/**
 * Example: encode_hostname_as_DN("www.fizzle.com")
 * will result in dc=www,dc=fizzle,dc=com,cn=www.fizzle.com
 */
WvString encode_hostname_as_DN(WvStringParm hostname);

/**
 * Given a hostname, turn it into a "nice" one.  It has to start with a
 * letter/number, END with a letter/number, have underscores converted to
 * hyphens, and have no more than one hyphen in a row.  If we can't do this
 * and have any sort of answer, return "UNKNOWN".
 */
WvString nice_hostname(WvStringParm name);

/**
 * Take a full path/file name and splits it up into respective pathname and
 * filename. This can also be useful for splitting the toplevel directory off a
 * path.
 */
WvString getfilename(WvStringParm fullname);
WvString getdirname(WvStringParm fullname);

/*
 * Possible rounding methods for numbers -- remember from school?
 */
enum RoundingMethod
{
    ROUND_DOWN,
    ROUND_DOWN_AT_POINT_FIVE,
    ROUND_UP_AT_POINT_FIVE,
    ROUND_UP
};

/**
 * Given a number of blocks and a blocksize (default==1 byte), return a 
 * WvString containing a human-readable representation of blocks*blocksize.
 * This function uses SI prefixes.
 */
WvString sizetoa(unsigned long long blocks, unsigned long blocksize = 1,
		 RoundingMethod rounding_method = ROUND_UP_AT_POINT_FIVE);

/**
 * Given a size in kilobyes, return a human readable size.
 * This function uses SI prefixes (1 MB = 1 000 KB = 1 000 000 B).
 */
WvString sizektoa(unsigned long long kbytes,
		  RoundingMethod rounding_method = ROUND_UP_AT_POINT_FIVE);

/**
 * Given a number of blocks and a blocksize (default==1 byte), return a 
 * WvString containing a human-readable representation of blocks*blocksize.
 * This function uses IEC prefixes.
 */
WvString sizeitoa(unsigned long long blocks, unsigned long blocksize = 1,
		  RoundingMethod rounding_method = ROUND_UP_AT_POINT_FIVE);

/**
 * Given a size in kilobytes, return a human readable size.
 * This function uses IEC prefixes.
 */
WvString sizekitoa(unsigned long long kbytes,
		   RoundingMethod rounding_method = ROUND_UP_AT_POINT_FIVE);

/** Given a number of seconds, returns a formatted human-readable string
 * saying how long the period is.
 */
WvString secondstoa(unsigned int total_seconds);

/**
 * Finds a string in an array and returns its index.
 * Returns -1 if not found.
 */
int lookup(const char *str, const char * const *table,
    bool case_sensitive = false);

/**
 * Splits a string and adds each substring to a collection.
 *   coll       : the collection of strings to add to
 *   _s         : the string to split
 *   splitchars : the set of delimiter characters
 *   limit      : the maximum number of elements to split
 */
template<class StringCollection>
void strcoll_split(StringCollection &coll, WvStringParm _s,
    const char *splitchars = " \t", int limit = 0)
{
    WvString s(_s);
    char *sptr = s.edit(), *eptr, oldc;
    
    // Simple if statement to catch (and add) empty (but not NULL) strings.
    if (sptr && !*sptr )
    {	
	WvString *emptyString = new WvString("");
	coll.add(emptyString, true);
    }
    
    // Needed to catch delimeters at the beginning of the string.
    bool firstrun = true;

    while (sptr && *sptr)
    {
	--limit;

	if (firstrun)
	{   
	    firstrun = false;
	}
	else
	{
	    sptr += strspn(sptr, splitchars);
	}

	if (limit)
	{
	    eptr = sptr + strcspn(sptr, splitchars);
	}
	else
	{
	    eptr = sptr + strlen(sptr);
	}
	
	oldc = *eptr;
	*eptr = 0;
	
	WvString *newstr = new WvString(sptr);
        coll.add(newstr, true);
	
	*eptr = oldc;
	sptr = eptr;
    }
}


/**
 * Splits a string and adds each substring to a collection.
 *   this behaves differently in that it actually delimits the 
 *   pieces as fields and returns them, it doesn't treat multiple
 *   delimeters as one and skip them.
 *
 *   ie., parm1::parm2 -> 'parm1','','parm2' when delimited with ':'
 *
 *   coll       : the collection of strings to add to
 *   _s         : the string to split
 *   splitchars : the set of delimiter characters
 *   limit      : the maximum number of elements to split
 */
template<class StringCollection>
void strcoll_splitstrict(StringCollection &coll, WvStringParm _s,
    const char *splitchars = " \t", int limit = 0)
{
    WvString s(_s);
    char *cur = s.edit();

    if (!cur) return;

    for (;;)
    {
        --limit;
        if (!limit)
        {
            coll.add(new WvString(cur), true);
            break;
        }

        int len = strcspn(cur, splitchars);

        char tmp = cur[len];
        cur[len] = 0;
        coll.add(new WvString(cur), true);
        cur[len] = tmp;

        if (!cur[len]) break;
        cur += len + 1;
    }
}


#ifndef _WIN32 // don't have regex on win32
/**
 * Splits a string and adds each substring to a collection.
 *   coll       : the collection of strings to add to
 *   _s         : the string to split
 *   splitchars : the set of delimiter characters
 *   limit      : the maximum number of elements to split
 */
template<class StringCollection>
void strcoll_split(StringCollection &coll, WvStringParm s,
    const WvRegex &regex, int limit = 0)
{
    int start = 0;
    int match_start, match_end;
    int count = 0;
    
    while ((limit == 0 || count < limit)
    	    && regex.continuable_match(&s[start], match_start, match_end)
    	    && match_end > 0)
    {
    	WvString *substr = new WvString;
    	int len = match_start;
    	substr->setsize(len+1);
    	memcpy(substr->edit(), &s[start], len);
    	substr->edit()[len] = '\0';
    	coll.add(substr, true);
    	start += match_end;
    	++count;
    }
    
    if (limit == 0 || count < limit)
    {
    	WvString *last = new WvString(&s[start]);
    	last->unique();
    	coll.add(last, true);
    }
}
#endif


/**
 * Concatenates all strings in a collection and returns the result.
 *   coll      : the collection of strings to read from
 *   joinchars : the delimiter string to insert between strings
 */
template<class StringCollection>
WvString strcoll_join(const StringCollection &coll,
    const char *joinchars = " \t")
{
    size_t joinlen = strlen(joinchars);
    size_t totlen = 1;
    typename StringCollection::Iter s(
        const_cast<StringCollection&>(coll));
    for (s.rewind(); s.next(); )
    {
        if (s->cstr())
            totlen += strlen(s->cstr());
        totlen += joinlen;
    }
    totlen -= joinlen; // no join chars at tail
    
    WvString total;
    total.setsize(totlen);

    char *te = total.edit();
    te[0] = 0;
    bool first = true;
    for (s.rewind(); s.next(); )
    {
        if (first)
            first = false;
        else
            strcat(te, joinchars);
        if (s->cstr()) 
            strcat(te, s->cstr());
    }
    return total;
}

/**
 * Replace any instances of "a" with "b" in "s".  Kind of like sed, only
 * much dumber.
 */
WvString strreplace(WvStringParm s, WvStringParm a, WvStringParm b);

/** Replace any consecutive instances of character c with a single one */
WvString undupe(WvStringParm s, char c);

/** Do gethostname() without a fixed-length buffer */
WvString hostname();

/** Get the fqdn of the local host, using gethostbyname() and gethostname() */
WvString fqdomainname();

/** Get the current working directory without a fixed-length buffer */
WvString wvgetcwd();

/**
 * Inserts SI-style spacing into a number
 * (eg passing 9876543210 returns "9 876 543 210")
 */
WvString metriculate(const off_t i);

/**
 * Returns everything in line (exclusively) after a.
 * If a is not in line, "" is returned.
 */
WvString afterstr(WvStringParm line, WvStringParm a);

/**
 * Returns everything in line (exclusively) before 'a'.
 * If a is not in line, line is returned.
 */
WvString beforestr(WvStringParm line, WvStringParm a);

/**
 * Returns the string of length len starting at pos in line.
 * Error checking prevents seg fault.
 * If pos > line.len()-1 return ""
 * if pos+len > line.len() simply return from pos to end of line
 */
WvString substr(WvString line, unsigned int pos, unsigned int len);

/** 
 * Removes any trailing punctuation ('.', '?', or '!') from the line, and
 * returns it in a new string.  Does not modify line.
 */
WvString depunctuate(WvStringParm line);

// Converts a string in decimal to an arbitrary numeric type
template<class T>
bool wvstring_to_num(WvStringParm str, T &n)
{
    bool neg = false;
    n = 0;

    for (const char *p = str; *p; ++p)
    {
        if (isdigit(*p))
        {
            n = n * T(10) + T(*p - '0');
        }
        else if ((const char *)str == p
                && *p == '-')
        {
            neg = true;
        }
        else return false;
    }

    if (neg)
    	n = -n;

    return true;
}

/*
 * Before using the C-style string escaping functions below, please consider
 * using the functions in wvtclstring.h instead; they usualy lead to much more
 * human readable and manageable results, and allow representation of
 * lists of strings.
 */

struct CStrExtraEscape
{
    char ch;
    const char *esc;
};
extern const CStrExtraEscape CSTR_TCLSTR_ESCAPES[];

/// Converts data into a C-style string constant.
//
// If data is NULL, returns WvString::null; otherwise, returns an allocated
// WvString containing the C-style string constant that represents the data.
//
// All printable characters including space except " and \ are represented with
// escaping.
//
// The usual C escapes are performed, such as \n, \r, \", \\ and \0.
//
// All other characters are escaped in uppercase hex form, eg. \x9E
//
// The extra_escapes parameter allows for additional characters beyond
// the usual ones escaped in C; setting it to CSTR_TCLSTR_ESCAPES will
// escape { and } as \< and \>, which allows the resulting strings to be
// TCL-string coded without ridiculous double-escaping.
//
WvString cstr_escape(const void *data, size_t size,
        const CStrExtraEscape extra_escapes[] = NULL);

/// Converts a C-style string constant into data.
// 
// This function does *not* include the trailing null that a C compiler would --
//   if you want this null, put \0 at the end of the C-style string
// 
// If cstr is correctly formatted and max_size is large enough for the
// resulting data, returns true and size will equal the size of the
// resulting data.  If data is not NULL it will contain this data.
//
// If cstr is correctly formatted but max_size is too small for the resulting
// data, returns false and size will equal the minimum value of min_size
// for this function to have returned true.  If data is non-NULL it will
// contain the first max_size bytes of resulting data.
// 
// If cstr is incorrectly formatted, returns false and size will equal 0.
//
// This functions works just as well on multiple, whitespace-separated
// C-style strings as well.  This allows you to concatenate strings produced
// by cstr_escape, and the result of cstr_unescape will be the data blocks
// concatenated together.  This implies that the empty string corresponds
// to a valid data block of length zero; however, a null string still returns
// an error.
//
// The extra_escapes parameter must match that used in the call to 
// cstr_escape used to produce the escaped strings.
//
bool cstr_unescape(WvStringParm cstr, void *data, size_t max_size, size_t &size,
        const CStrExtraEscape extra_escapes[] = NULL);

static inline bool is_int(const char *str)
{
    if (!str)
        return false;
    
    if (*str == '-')
        ++str;
    
    if (!*str)
        return false;
    
    while (*str)
    	if (!isdigit(*str++))
    	    return false;
    	    
    return true;
}

/// Converts a pointer into a string, like glibc's %p formatter would
/// do.
WvString ptr2str(void* ptr);

#endif // __WVSTRUTILS_H
