import re

q = "'"
qq = '"'


class QuoteError(Exception):
    pass


def _quotesplit(line):
    inquote = None
    inescape = None
    wordstart = 0
    word = ''
    for i in range(len(line)):
        c = line[i]
        if inescape:
            if inquote == q and c != q:
                word += '\\'  # single-q backslashes can only quote single-q
            word += c
            inescape = False
        elif c == '\\':
            inescape = True
        elif c == inquote:
            inquote = None
            # this is un-sh-like, but do it for sanity when autocompleting
            yield (wordstart, word)
            word = ''
            wordstart = i+1
        elif not inquote and not word and (c == q or c == qq):
            # the 'not word' constraint on this is un-sh-like, but do it
            # for sanity when autocompleting
            inquote = c
            wordstart = i
        elif not inquote and c in [' ', '\n', '\r', '\t']:
            if word:
                yield (wordstart, word)
            word = ''
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
    dequotes words that *start* with a quote character, that is, a string like
       hello"world"
    will not have its quotes removed, while a string like
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
      line: an input string
    Returns:
      quotechar,word: the initial quote char (or None), and the partial word.
    """
    try:
        for (wordstart,word) in _quotesplit(line):
            pass
    except QuoteError:
        firstchar = line[wordstart]
        if firstchar in [q, qq]:
            return (firstchar, word)
        else:
            return (None, word)
    else:
        return (None, '')


def quotify(qtype, word, terminate):
    """Return a string corresponding to given word, quoted using qtype.

    The resulting string is dequotable using quotesplit() and can be
    joined with other quoted strings by adding arbitrary whitespace
    separators.

    Args:
      qtype: one of '', shquote.qq, or shquote.q
      word: the string to quote.  May contain arbitrary characters.
      terminate: include the trailing quote character, if any.
    Returns:
      The quoted string.
    """
    if qtype == qq:
        return qq + word.replace(qq, '\\"') + (terminate and qq or '')
    elif qtype == q:
        return q + word.replace(q, "\\'") + (terminate and q or '')
    else:
        return re.sub(r'([\"\' \t\n\r])', r'\\\1', word)


def quotify_list(words):
  """Return a minimally-quoted string produced by quoting each word.

  This calculates the qtype for each word depending on whether the word
  already includes singlequote characters, doublequote characters, both,
  or neither.

  Args:
    words: the list of words to quote.
  Returns:
    The resulting string, with quoted words separated by ' '.
  """
  wordout = []
  for word in words:
    qtype = q
    if word and not re.search(r'[\s\"\']', word):
      qtype = ''
    elif q in word and qq not in word:
      qtype = qq
    wordout.append(quotify(qtype, word, True))
  return ' '.join(wordout)


def what_to_add(qtype, origword, newword, terminate):
    """Return a qtype that is needed to finish a partial word.

    For example, given an origword of '\"frog' and a newword of '\"frogston',
    returns either:
       terminate=False: 'ston'
       terminate=True:  'ston\"'

    This is useful when calculating tab completion strings for readline.

    Args:
      qtype: the type of quoting to use (ie. the first character of origword)
      origword: the original word that needs completion.
      newword: the word we want it to be after completion.  Must start with
        origword.
      terminate: true if we should add the actual quote character at the end.
    Returns:
      The string to append to origword to produce (quoted) newword.
    """
    if not newword.startswith(origword):
        return ''
    else:
        qold = quotify(qtype, origword, terminate=False)
        return quotify(qtype, newword, terminate=terminate)[len(qold):]
