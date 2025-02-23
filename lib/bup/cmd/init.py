
from os import environb as environ
from os.path import abspath

from bup import git, options, repo
from bup.compat import argv_bytes
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

    if len(extra) > 1:
        o.fatal('only the directory positional argument is allowed')
    if extra:
        environ[b'BUP_DIR'] = abspath(argv_bytes(extra[0]))

    try:
        repo.LocalRepo.create()
    except git.GitError as ex:
        log(f'bup: error: could not init repository: {ex}')
        return EXIT_FAILURE

    if opt.remote:
        git.check_repo_or_die()
        with repo.make_repo(argv_bytes(opt.remote), create=True):
            pass
    return 0
