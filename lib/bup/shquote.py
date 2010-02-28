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
    l = []
    try:
        for i in _quotesplit(line):
            l.append(i)
    except QuoteError:
        pass
    return l


def unfinished_word(line):
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
    if qtype == qq:
        return qq + word.replace(qq, '\\"') + (terminate and qq or '')
    elif qtype == q:
        return q + word.replace(q, "\\'") + (terminate and q or '')
    else:
        return re.sub(r'([\"\' \t\n\r])', r'\\\1', word)


def what_to_add(qtype, origword, newword, terminate):
    if not newword.startswith(origword):
        return ''
    else:
        qold = quotify(qtype, origword, terminate=False)
        return quotify(qtype, newword, terminate=terminate)[len(qold):]
