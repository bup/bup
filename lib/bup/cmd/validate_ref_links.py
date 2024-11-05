
from bup import git, options
from bup.gc import count_objects, find_live_objects
from bup.helpers import EXIT_FALSE, EXIT_TRUE, log, wrap_boolean_main


optspec = """
bup validate-ref-links
--
v,verbose       increase log output (can be used more than once)
"""

def validate(argv):
    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])
    verbosity = opt.verbose

    if extra:
        o.fatal(f'unexpected arguments: {extra}')

    git.check_repo_or_die()
    cat_pipe = git.cp()

    existing_count = count_objects(git.repo(b'objects/pack'), verbosity)
    if verbosity:
        log(f'found {existing_count} objects\n')

    missing = 0
    if existing_count:
        with git.PackIdxList(git.repo(b'objects/pack')) as idxl:
            live_objects, live_trees, missing = \
                find_live_objects(existing_count, cat_pipe, idxl,
                                  verbosity=verbosity, count_missing=True)
            live_objects.close()
    return EXIT_FALSE if missing else EXIT_TRUE

def main(argv):
    wrap_boolean_main(lambda: validate(argv))
