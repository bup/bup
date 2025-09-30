
import math, os, re

from bup import _helpers
from bup.config import ConfigError
from bup.helpers import dict_subset


BUP_BLOBBITS = 13
BUP_TREE_BLOBBITS = 13
MAX_PER_TREE = 256
fanout = 16

GIT_MODE_FILE = 0o100644
GIT_MODE_EXEC = 0o100755
GIT_MODE_TREE = 0o40000
GIT_MODE_SYMLINK = 0o120000

HashSplitter = _helpers.HashSplitter

def _fanbits():
    return int(math.log(fanout or 128, 2))

fanbits = _fanbits

_splitter_args = ('progress', 'keep_boundaries', 'blobbits', 'fanbits')

def splitter(files, *, progress=None, keep_boundaries=False, blobbits=None,
             fanbits=None):
    return HashSplitter(files,
                        keep_boundaries=keep_boundaries,
                        progress=progress,
                        bits=blobbits or BUP_BLOBBITS,
                        fanbits=fanbits or _fanbits())


_method_rx = br'legacy:(13|14|15|16|17|18|19|20|21)'

def configuration(config_get):
    """Return a splitting configuration map based on information
    provided by config_get. The valid entries include the splitter()
    keyword arguments, and the configuration must include every option
    that affects the way data will be split. (See also, rewriting via
    get --rewrite.)

    """
    cfg = {'trees': config_get(b'bup.split.trees', opttype='bool')}
    method = config_get(b'bup.split.files')
    if method is None:
        return cfg
    m = re.fullmatch(_method_rx, method)
    if not m:
        raise ConfigError(f'invalid bup.split.files setting {method}')
    cfg['blobbits'] = int(m.group(1))
    return cfg

def from_config(files, split_config):
    """Return a hashsplitter for the given split_config."""
    return splitter(files, **dict_subset(split_config, _splitter_args))


total_split = 0
def split_to_blobs(makeblob, splitter):
    global total_split
    for blob, level in splitter:
        sha = makeblob(blob)
        total_split += len(blob)
        yield (sha, len(blob), level)


def _make_shalist(l):
    ofs = 0
    l = list(l)
    total = sum(size for mode,sha,size, in l)
    vlen = len(b'%x' % total)
    shalist = []
    for (mode, sha, size) in l:
        shalist.append((mode, b'%0*x' % (vlen,ofs), sha))
        ofs += size
    assert(ofs == total)
    return (shalist, total)


def _squish(maketree, stacks, n):
    i = 0
    while i < n or len(stacks[i]) >= MAX_PER_TREE:
        while len(stacks) <= i+1:
            stacks.append([])
        if len(stacks[i]) == 1:
            stacks[i+1] += stacks[i]
        elif stacks[i]:
            (shalist, size) = _make_shalist(stacks[i])
            tree = maketree(shalist)
            stacks[i+1].append((GIT_MODE_TREE, tree, size))
        stacks[i] = []
        i += 1


def split_to_shalist(makeblob, maketree, splitter):
    sl = split_to_blobs(makeblob, splitter)
    assert(fanout != 0)
    if not fanout:
        shal = []
        for (sha,size,level) in sl:
            shal.append((GIT_MODE_FILE, sha, size))
        return _make_shalist(shal)[0]
    else:
        stacks = [[]]
        for (sha,size,level) in sl:
            stacks[0].append((GIT_MODE_FILE, sha, size))
            _squish(maketree, stacks, level)
        #log('stacks: %r\n' % [len(i) for i in stacks])
        _squish(maketree, stacks, len(stacks)-1)
        #log('stacks: %r\n' % [len(i) for i in stacks])
        return _make_shalist(stacks[-1])[0]


def split_to_blob_or_tree(makeblob, maketree, splitter):
    shalist = list(split_to_shalist(makeblob, maketree, splitter))
    if len(shalist) == 1:
        return (shalist[0][0], shalist[0][2])
    elif len(shalist) == 0:
        return (GIT_MODE_FILE, makeblob(b''))
    else:
        return (GIT_MODE_TREE, maketree(shalist))


def open_noatime(name):
    fd = _helpers.open_noatime(name)
    try:
        return os.fdopen(fd, 'rb', 1024*1024)
    except:
        try:
            os.close(fd)
        except:
            pass
        raise
