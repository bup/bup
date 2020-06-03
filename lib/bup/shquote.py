
from __future__ import absolute_import
import re

from bup.compat import bytes_from_byte

q = b"'"
qq = b'"'


class QuoteError(Exception):
    pass


def _quotesplit(line):
    inquote = None
    inescape = None
    wordstart = 0
    word = b''
    for i in range(len(line)):
        c = bytes_from_byte(line[i])
        if inescape:
            if inquote == q and c != q:
                word += b'\\'  # single-q backslashes can only quote single-q
            word += c
            inescape = False
        elif c == b'\\':
            inescape = True
        elif c == inquote:
            inquote = None
            # this is un-sh-like, but do it for sanity when autocompleting
            yield (wordstart, word)
            word = b''
            wordstart = i+1
        elif not inquote and not word and (c == q or c == qq):
            # the 'not word' constraint on this is un-sh-like, but do it
            # for sanity when autocompleting
            inquote = c
            wordstart = i
        elif not inquote and c in [b' ', b'\n', b'\r', b'\t']:
            if word:
                yield (wordstart, word)
            word = b''
            wordstart = i+1
        else:
            word += c
    if word:
        yield (wordstart, word)
    if inquote or inescape or word:
        raise QuoteError()


def quotesplit(line):
    """Split 'line' into a list of offset,word tuples.

    The words are produced after removing doublequotes, singlequotes, and
    backslash escapes.

    Note that this implementation isn't entirely sh-compatible.  It only
    dequotes words that *start* with a quote character, that is, bytes like
       hello"world"
    will not have its quotes removed, while bytes like
       hello "world"
    will be turned into [(0, 'hello'), (6, 'world')] (ie. quotes removed).
    """
    l = []
    try:
        for i in _quotesplit(line):
            l.append(i)
    except QuoteError:
        pass
    return l


def unfinished_word(line):
    """Returns the quotechar,word of any unfinished word at the end of 'line'.

    You can use this to determine if 'line' is a completely parseable line
    (ie. one that quotesplit() will finish successfully) or if you need
    to read more bytes first.

    Args:
      line: bytes
    Returns:
      quotechar,word: the initial quote char (or None), and the partial word.
    """
    try:
        for (wordstart,word) in _quotesplit(line):
            pass
    except QuoteError:
        firstchar = bytes_from_byte(line[wordstart])
        if firstchar in [q, qq]:
            return (firstchar, word)
        else:
            return (None, word)
    else:
        return (None, b'')

def quotify(qtype, word, terminate):
    """Return a bytes corresponding to given word, quoted using qtype.

    The resulting bytes are dequotable using quotesplit() and can be
    joined with other quoted bytes by adding arbitrary whitespace
    separators.

    Args:
      qtype: one of '', shquote.qq, or shquote.q
      word: the bytes to quote.  May contain arbitrary characters.
      terminate: include the trailing quote character, if any.
    Returns:
      The quoted bytes.
    """
    if qtype == qq:
        return qq + word.replace(qq, b'\\"') + (terminate and qq or b'')
    elif qtype == q:
        return q + word.replace(q, b"\\'") + (terminate and q or b'')
    else:
        return re.sub(br'([\"\' \t\n\r])', br'\\\1', word)


def quotify_list(words):
  """Return minimally-quoted bytes produced by quoting each word.

  This calculates the qtype for each word depending on whether the word
  already includes singlequote characters, doublequote characters, both,
  or neither.

  Args:
    words: the list of words to quote.
  Returns:
    The resulting bytes, with quoted words separated by ' '.
  """
  wordout = []
  for word in words:
    qtype = q
    if word and not re.search(br'[\s\"\']', word):
      qtype = b''
    elif q in word and qq not in word:
      qtype = qq
    wordout.append(quotify(qtype, word, True))
  return b' '.join(wordout)


def what_to_add(qtype, origword, newword, terminate):
    """Return a qtype that is needed to finish a partial word.

    For example, given an origword of '\"frog' and a newword of '\"frogston',
    returns either:
       terminate=False: 'ston'
       terminate=True:  'ston\"'

    This is useful when calculating tab completions for readline.

    Args:
      qtype: the type of quoting to use (ie. the first character of origword)
      origword: the original word that needs completion.
      newword: the word we want it to be after completion.  Must start with
        origword.
      terminate: true if we should add the actual quote character at the end.
    Returns:
      The bytes to append to origword to produce (quoted) newword.
    """
    if not newword.startswith(origword):
        return b''
    else:
        qold = quotify(qtype, origword, terminate=False)
        return quotify(qtype, newword, terminate=terminate)[len(qold):]
