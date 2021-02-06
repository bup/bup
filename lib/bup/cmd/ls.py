
from __future__ import absolute_import, print_function
import os.path, sys

from bup import compat, git, ls
from bup.io import byte_stream

def main(argv):
    git.check_repo_or_die()

    sys.stdout.flush()
    out = byte_stream(sys.stdout)
    # Check out lib/bup/ls.py for the opt spec
    rc = ls.via_cmdline(argv[1:], out=out)
    sys.exit(rc)
