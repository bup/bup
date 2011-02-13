#!/usr/bin/env python
import sys, os, subprocess, select, tempfile, signal, traceback, time
from bup import git, options, path
from bup.helpers import *
from bup.wvbuf import WvBuf


optspec = """
bup mplayer [options...]
--
mplayer=         path to the mplayer program [mplayer]
X,mplayer-flags= extra flags to pass to the mplayer binary
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

git.check_repo_or_die()
handle_ctrl_c()

if extra:
    o.fatal('no arguments expected')

if opt.mplayer_flags:
    flags = opt.mplayer_flags.split(' ')
else:
    flags = []
args = [opt.mplayer] + flags + ['-idle', '-slave', '-quiet',
                                '-cache', '1024']

def kill(p):
    if p:
        if p.poll() != None:
            return p.poll()
        os.kill(p.pid, signal.SIGTERM)
        for i in xrange(20):
            if p.poll() != None:
                return p.poll()
            time.sleep(0.1)
        os.kill(p.pid, signal.SIGINT)
        for i in xrange(20):
            if p.poll() != None:
                return p.poll()
            time.sleep(0.1)
        os.kill(p.pid, signal.SIGKILL)
        return p.wait()


count = 0
class QItem:
    def __init__(self, hash):
        global count
        self.hash = hash
        self.p = None
        self.dead = False
        count += 1
        self.name = os.path.join(tfd, str(count))
        os.mkfifo(self.name)
        
    def check(self):
        if self.dead:
            return True
        if not self.p:
            debug2('QItem.starting(%r)\n' % self)
            self.p = subprocess.Popen([path.exe(), 'join',
                                       '-o', self.name,
                                       '--', self.hash])
        return self.p.poll() != None

    def kill(self):
        debug2('QItem.kill(%r) p=%r\n' % (self, self.p))
        self.dead = True
        p = self.p
        self.p = None
        if p:
            kill(p)
        unlink(self.name)

    def __del__(self):
        try:
            debug2('QItem.__del__(%r)\n' % self)
            self.kill()
        except Exception, e:
            traceback.print_exc()


def start_mplayer():
    global paused, p
    if p and p.poll() != None:
        p = None
    if not p:
        fd = os.dup(sys.stderr.fileno())
        try:
            p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=fd)
        finally:
            os.close(fd)
        paused = False


try:
    tfd = tempfile.mkdtemp(prefix='bup-mplayer-')

    inbuf = WvBuf()
    eof = False
    queue = []
    paused = False
    p = None

    while not eof or 1:
        qi = None
        for qi in queue[0:2]:
            if qi.check():
                queue.remove(qi)
        if len(queue) > 0: queue[0].check()
        if len(queue) > 1: queue[1].check()

        r,w,x = select.select([0], [], [], 1)
        if 0 in r:
            b = os.read(0, 4096)
            if not b: eof = True
            inbuf.put(b)
        for line in inbuf.iterlines():
            debug2('got line: %r\n' % line)
            line = line.strip()
            start_mplayer()
            if not line:
                pass
            elif line == 'clear':
                while queue:
                    queue[0].kill()
                    del queue[0]
                kill(p)
                p = None
            elif line == 'pause':
                if not paused:
                    p.stdin.write('pause\n')
                    paused = True
            elif line == 'go':
                if paused:
                    p.stdin.write('pause\n')
                    paused = False
            else:
                assert(len(line) == 40)
                qi = QItem(line.strip())
                queue.append(qi)
                debug1('enqueued=%r qlen=%d\n' % (qi.name, len(queue)))
                qf = qi.name.replace('"', '_')
                p.stdin.write('loadfile "%s" 1\n' % qf)
                paused = False
finally:
    qi = None
    if p:
        p.stdin.close()
        kill(p)
    for qi in queue:
        qi.kill()
    queue = []
    for f in os.listdir(tfd):
        os.unlink(os.path.join(tfd, f))
    os.rmdir(tfd)
    log('exiting.\n')
