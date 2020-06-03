
from __future__ import absolute_import

from wvtest import *

from bup import shquote
from buptest import no_lingering_errors


def qst(line):
    return [word for offset,word in shquote.quotesplit(line)]

@wvtest
def test_shquote():
    with no_lingering_errors():
        WVPASSEQ(qst(b"""  this is    basic \t\n\r text  """),
                 [b'this', b'is', b'basic', b'text'])
        WVPASSEQ(qst(br""" \"x\" "help" 'yelp' """), [b'"x"', b'help', b'yelp'])
        WVPASSEQ(qst(br""" "'\"\"'" '\"\'' """), [b"'\"\"'", b'\\"\''])

        WVPASSEQ(shquote.quotesplit(b'  this is "unfinished'),
                 [(2, b'this'), (7, b'is'), (10, b'unfinished')])

        WVPASSEQ(shquote.quotesplit(b'"silly"\'will'),
                 [(0, b'silly'), (7, b'will')])

        WVPASSEQ(shquote.unfinished_word(b'this is a "billy" "goat'),
                 (b'"', b'goat'))
        WVPASSEQ(shquote.unfinished_word(b"'x"),
                 (b"'", b'x'))
        WVPASSEQ(shquote.unfinished_word(b"abra cadabra "),
                 (None, b''))
        WVPASSEQ(shquote.unfinished_word(b"abra cadabra"),
                 (None, b'cadabra'))

        qtype, word = shquote.unfinished_word(b"this is /usr/loc")
        WVPASSEQ(shquote.what_to_add(qtype, word, b"/usr/local", True),
                 b"al")
        qtype, word = shquote.unfinished_word(b"this is '/usr/loc")
        WVPASSEQ(shquote.what_to_add(qtype, word, b"/usr/local", True),
                 b"al'")
        qtype, word = shquote.unfinished_word(b"this is \"/usr/loc")
        WVPASSEQ(shquote.what_to_add(qtype, word, b"/usr/local", True),
                 b"al\"")
        qtype, word = shquote.unfinished_word(b"this is \"/usr/loc")
        WVPASSEQ(shquote.what_to_add(qtype, word, b"/usr/local", False),
                 b"al")
        qtype, word = shquote.unfinished_word(b"this is \\ hammer\\ \"")
        WVPASSEQ(word, b' hammer "')
        WVPASSEQ(shquote.what_to_add(qtype, word, b" hammer \"time\"", True),
                 b"time\\\"")

        WVPASSEQ(shquote.quotify_list([b'a', b'', b'"word"', b"'third'", b"'",
                                       b"x y"]),
                 b"a '' '\"word\"' \"'third'\" \"'\" 'x y'")
