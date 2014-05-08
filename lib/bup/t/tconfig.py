from helpers import readpipe
from wvtest import *
import config


@wvtest
def test_arg_max():
    WVPASSEQ(int(readpipe(['getconf', 'ARG_MAX'])), config.arg_max)
