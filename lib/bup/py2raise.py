
import sys

# This file exists because the raise syntax is completely incompatible
# with Python 3.

def reraise(ex):
    raise ex, None, sys.exc_info()[2]
