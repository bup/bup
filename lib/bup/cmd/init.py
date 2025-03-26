
from os import environb as environ
from os.path import abspath

from bup import git, options, repo
from bup.compat import argv_bytes
from bup.config import derive_repo_addr
from bup.helpers import EXIT_FAILURE, log
from bup.compat import argv_bytes


optspec = """
[BUP_DIR=directory] bup init [-r host:path] [directory]
--
r,remote=  remote repository path
"""

def main(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    if opt.remote: opt.remote = argv_bytes(opt.remote)
    if len(extra) > 1:
        o.fatal('only the directory positional argument is allowed')
    if extra:
        if opt.remote:
            o.fatal('cannot initialize both local and remote repo')
        environ[b'BUP_DIR'] = abspath(argv_bytes(extra[0]))
    addr = derive_repo_addr(remote=opt.remote, die=o.fatal)
    try:
        with repo.make_repo(addr, create=True):
            pass
    except git.GitError as ex:
        log(f'bup: error: could not init repository: {ex}')
        return EXIT_FAILURE
    return 0
