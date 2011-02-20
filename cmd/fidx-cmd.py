#!/usr/bin/env python
import sys, struct
from bup import options, hashsplit, git
from bup.helpers import *

FIDX_VERSION=1

optspec = """
bup fidx <filenames...>
--
d,outdir=  directory to write output (.fidx) files
o,outfile= filename to write fidx data (only works with a single input file)
A,ascii    write the index in human-readable ascii format to stdout
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if not extra:
    o.fatal("at least one filename expected")
if opt.outfile and len(extra) > 1:
    o.fatal('--outfile only works with a single input filename')
if opt.outfile and opt.outdir:
    o.fatal('--outfile is incompatible with --outdir')


def makeblob(content):
    return git.calc_hash('blob', content)


_total = [0]
def prog(filenum, ofs):
    _total[0] += ofs
    qprogress('Hashing: %dk, %d/%d files\r'
              % (_total[0]/1024, filenum, len(extra)))


for count,name in enumerate(extra):
    progress('%s\n' % name)
    try:
        inf = open(name)
    except IOError, e:
        add_error('%s: %s' % (name, e))
        continue
    if opt.ascii:
        outf = None
    else:
        if opt.outdir:
            outname = os.path.join(opt.outdir,
                                   os.path.basename(name) + '.fidx')
        else:
            outname = name + '.fidx'
        outf = open(outname + '.tmp', 'w+')
        filesha = Sha1()
        def w(s):
            filesha.update(s)
            outf.write(s)
        w('FIDX%s' % struct.pack('!I', FIDX_VERSION))
        
    it = hashsplit.split_to_blobs(makeblob, [inf],
                                  keep_boundaries=False,
                                  progress=lambda n,sz: prog(count+1,sz))
    for sha,size,level in it:
        assert(size <= 65535)
        assert(size <= hashsplit.BLOB_MAX)
        if opt.ascii:
            print sha.encode('hex'), level, size
        else:
            w(sha)
            w(struct.pack('!HH', size, level))

    if outf:
        filesum = filesha.digest()
        assert(len(filesum) == 20)
        outf.write(filesum)
        outf.close()
        os.rename(outname + '.tmp', outname)


if saved_errors:
    log('WARNING: %d errors encountered while hashing.\n' % len(saved_errors))
    sys.exit(1)
