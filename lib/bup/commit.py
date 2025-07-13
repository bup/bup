
from binascii import hexlify
from collections import namedtuple
import re

from bup.helpers import utc_offset_str


def parse_tz_offset(s):
    """UTC offset in seconds."""
    tz_off = (int(s[1:3]) * 60 * 60) + (int(s[3:5]) * 60)
    if s[0] == b'-'[0]:
        return - tz_off
    return tz_off


def parse_commit_gpgsig(sig):
    """Return the original signature bytes.

    i.e. with the "gpgsig " header and the leading space character on
    each continuation line removed.

    """
    if not sig:
        return None
    assert sig.startswith(b'gpgsig ')
    sig = sig[7:]
    return sig.replace(b'\n ', b'\n')

# FIXME: derived from http://git.rsbx.net/Documents/Git_Data_Formats.txt
# Make sure that's authoritative.

# See also
# https://github.com/git/git/blob/master/Documentation/technical/signature-format.txt
# The continuation lines have only one leading space.

_start_end_char = br'[^ .,:;<>"\'\0\n]'
_content_char = br'[^\0\n<>]'
_safe_str_rx = br'(?:%s{1,2}|(?:%s%s*%s))' \
    % (_start_end_char,
       _start_end_char, _content_char, _start_end_char)
_tz_rx = br'[-+]\d\d[0-5]\d'
_parent_rx = br'(?:parent [abcdefABCDEF0123456789]{40}\n)'
# Assumes every following line starting with a space is part of the
# mergetag.  Is there a formal commit blob spec?
_mergetag_rx = br'(?:\nmergetag object [abcdefABCDEF0123456789]{40}(?:\n [^\0\n]*)*)'
_commit_rx = re.compile(br'''tree (?P<tree>[abcdefABCDEF0123456789]{40})
(?P<parents>%s*)author (?P<author_name>%s) <(?P<author_mail>%s)> (?P<asec>\d+) (?P<atz>%s)
committer (?P<committer_name>%s) <(?P<committer_mail>%s)> (?P<csec>\d+) (?P<ctz>%s)(?P<mergetag>%s?)
(?P<gpgsig>gpgsig .*\n(?: .*\n)*)?
(?P<message>(?:.|\n)*)''' % (_parent_rx,
                             _safe_str_rx, _safe_str_rx, _tz_rx,
                             _safe_str_rx, _safe_str_rx, _tz_rx,
                             _mergetag_rx))
_parent_hash_rx = re.compile(br'\s*parent ([abcdefABCDEF0123456789]{40})\s*')

# Note that the author_sec and committer_sec values are (UTC) epoch
# seconds, and for now the mergetag is not included.
CommitInfo = namedtuple('CommitInfo', ['tree', 'parents',
                                       'author_name', 'author_mail',
                                       'author_sec', 'author_offset',
                                       'committer_name', 'committer_mail',
                                       'committer_sec', 'committer_offset',
                                       'gpgsig',
                                       'message'])

def parse_commit(content):
    commit_match = re.match(_commit_rx, content)
    if not commit_match:
        raise Exception('cannot parse commit %r' % content)
    matches = commit_match.groupdict()
    return CommitInfo(tree=matches['tree'],
                      parents=re.findall(_parent_hash_rx, matches['parents']),
                      author_name=matches['author_name'],
                      author_mail=matches['author_mail'],
                      author_sec=int(matches['asec']),
                      author_offset=parse_tz_offset(matches['atz']),
                      committer_name=matches['committer_name'],
                      committer_mail=matches['committer_mail'],
                      committer_sec=int(matches['csec']),
                      committer_offset=parse_tz_offset(matches['ctz']),
                      gpgsig=parse_commit_gpgsig(matches['gpgsig']),
                      message=matches['message'])


def _local_git_date_str(epoch_sec):
    return b'%d %s' % (epoch_sec, utc_offset_str(epoch_sec))

def _git_date_str(epoch_sec, tz_offset_sec):
    offs =  tz_offset_sec // 60
    return b'%d %s%02d%02d' \
        % (epoch_sec,
           b'+' if offs >= 0 else b'-',
           abs(offs) // 60,
           abs(offs) % 60)


def create_commit_blob(tree, parent,
                       author, adate_sec, adate_tz,
                       committer, cdate_sec, cdate_tz,
                       msg):
    if adate_tz is not None:
        adate_str = _git_date_str(adate_sec, adate_tz)
    else:
        adate_str = _local_git_date_str(adate_sec)
    if cdate_tz is not None:
        cdate_str = _git_date_str(cdate_sec, cdate_tz)
    else:
        cdate_str = _local_git_date_str(cdate_sec)
    l = []
    if tree: l.append(b'tree %s' % hexlify(tree))
    if parent: l.append(b'parent %s' % hexlify(parent))
    if author: l.append(b'author %s %s' % (author, adate_str))
    if committer: l.append(b'committer %s %s' % (committer, cdate_str))
    l.append(b'')
    l.append(msg)
    return b'\n'.join(l)
