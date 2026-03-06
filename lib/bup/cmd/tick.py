
import time

from bup import options


optspec = """
bup tick
"""

def main(argv):
    o = options.Options(optspec)
    extra = o.parse_bytes(argv[1:])[2]
    if extra:
        o.fatal("no arguments expected")
    t = time.time()
    tleft = 1 - (t - int(t))
    time.sleep(tleft)
