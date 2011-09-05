from bup import shquote
from wvtest import *

def qst(line):
    return [word for offset,word in shquote.quotesplit(line)]

@wvtest
def test_shquote():
    WVPASSEQ(qst("""  this is    basic \t\n\r text  """),
             ['this', 'is', 'basic', 'text'])
    WVPASSEQ(qst(r""" \"x\" "help" 'yelp' """), ['"x"', 'help', 'yelp'])
    WVPASSEQ(qst(r""" "'\"\"'" '\"\'' """), ["'\"\"'", '\\"\''])

    WVPASSEQ(shquote.quotesplit('  this is "unfinished'),
             [(2,'this'), (7,'is'), (10,'unfinished')])

    WVPASSEQ(shquote.quotesplit('"silly"\'will'),
             [(0,'silly'), (7,'will')])

    WVPASSEQ(shquote.unfinished_word('this is a "billy" "goat'),
             ('"', 'goat'))
    WVPASSEQ(shquote.unfinished_word("'x"),
             ("'", 'x'))
    WVPASSEQ(shquote.unfinished_word("abra cadabra "),
             (None, ''))
    WVPASSEQ(shquote.unfinished_word("abra cadabra"),
             (None, 'cadabra'))

    (qtype, word) = shquote.unfinished_word("this is /usr/loc")
    WVPASSEQ(shquote.what_to_add(qtype, word, "/usr/local", True),
             "al")
    (qtype, word) = shquote.unfinished_word("this is '/usr/loc")
    WVPASSEQ(shquote.what_to_add(qtype, word, "/usr/local", True),
             "al'")
    (qtype, word) = shquote.unfinished_word("this is \"/usr/loc")
    WVPASSEQ(shquote.what_to_add(qtype, word, "/usr/local", True),
             "al\"")
    (qtype, word) = shquote.unfinished_word("this is \"/usr/loc")
    WVPASSEQ(shquote.what_to_add(qtype, word, "/usr/local", False),
             "al")
    (qtype, word) = shquote.unfinished_word("this is \\ hammer\\ \"")
    WVPASSEQ(word, ' hammer "')
    WVPASSEQ(shquote.what_to_add(qtype, word, " hammer \"time\"", True),
             "time\\\"")

    WVPASSEQ(shquote.quotify_list(['a', '', '"word"', "'third'", "'", "x y"]),
             "a '' '\"word\"' \"'third'\" \"'\" 'x y'")
