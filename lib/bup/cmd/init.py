
from os.path import abspath

from bup import git, options
from bup.compat import argv_bytes
from bup.helpers import EXIT_FAILURE, log
from bup.url import URL
from bup.repo import main_repo_location, repo_for_location


optspec = """
[BUP_DIR=directory] bup init [-r host:path] [directory]
--
r,remote=  remote repository path
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags_, extra = o.parse_bytes(argv[1:])
    if len(extra) > 1:
        o.fatal('only the directory positional argument is allowed')
    if extra:
        if opt.remote:
            o.fatal('cannot initialize both local and remote repo')
        loc = URL(scheme=b'file', path=abspath(argv_bytes(extra[0])))
    else:
        loc = main_repo_location(opt.remote, o.fatal)
    try:
        with repo_for_location(loc, create=True): pass
    except git.GitError as ex:
        log(f'bup: error: could not init repository: {ex}')
        return EXIT_FAILURE
    return 0
