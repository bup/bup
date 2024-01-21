#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

import os, socket, stat, sys, threading, time

from bup import options, git, vfs, xstat
from bup.helpers import log

allow_delete = False
local_ip = socket.gethostbyname(socket.gethostname())
local_port = 8888
currdir = '/'

class Stat():
    def __init__(self):
        self.st_mode = 0
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 0
        self.st_uid = 0
        self.st_gid = 0
        self.st_size = 0
        self.st_atime = 0
        self.st_mtime = 0
        self.st_ctime = 0
        self.st_blocks = 0
        self.st_blksize = 0
        self.st_rdev = 0

class FTPserverThread(threading.Thread):
    def __init__(self, top, (conn, addr)):
        self.conn = conn
        self.addr = addr
        self.basewd = currdir
        self.cwd = self.basewd
        self.rest = False
        self.pasv_mode = False
        self.top = top
        self.meta = True
        threading.Thread.__init__(self)

    def run(self):
        self.conn.send('220 Welcome!\r\n')
        while True:
            cmd = self.conn.recv(256)
            if not cmd: break
            else:
                try:
                    func = getattr(self, cmd[:4].strip().upper())
                    func(cmd)
                except Exception, e:
                    print 'ERROR: ', e
                    self.conn.send('500 Sorry.\r\n')

    def SYST(self, cmd):
        self.conn.send('215 UNIX Type: L8\r\n')

    def OPTS(self, cmd):
        if cmd[5:-2].upper() == 'UTF8 ON':
            self.conn.send('200 OK.\r\n')
        else:
            self.conn.send('451 Sorry.\r\n')

    def USER(self, cmd):
        self.conn.send('331 OK.\r\n')

    def PASS(self, cmd):
        self.conn.send('230 OK.\r\n')

    def QUIT(self, cmd):
        self.conn.send('221 Goodbye.\r\n')

    def NOOP(self, cmd):
        self.conn.send('200 OK.\r\n')

    def TYPE(self, cmd):
        self.mode = cmd[5]
        self.conn.send('200 Binary mode.\r\n')

    def CDUP(self, cmd):
        if self.cwd != self.basewd:
            self.cwd = os.path.abspath(os.path.join(self.cwd, '..'))
        self.conn.send('200 OK.\r\n')

    def PWD(self, cmd):
        cwd = self.cwd
        if cwd == '.':
            cwd = '/'
        self.conn.send('257 \"%s\"\r\n' % cwd)

    def CWD(self, cmd):
        chwd = cmd[4:-2]
        if chwd == '/':
            self.cwd = self.basewd
        else:
            self.cwd = os.path.abspath(os.path.join(self.cwd, chwd))
        self.conn.send('250 OK.\r\n')

    def PORT(self, cmd):
        if self.pasv_mode:
            self.servsock.close()
            self.pasv_mode = False
        l = cmd[5:].split(',')
        self.dataAddr = '.'.join(l[:4])
        self.dataPort = (int(l[4]) << 8) + int(l[5])
        self.conn.send('200 Get port.\r\n')

    def PASV(self, cmd): # from http://goo.gl/3if2U
        self.pasv_mode = True
        self.servsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servsock.bind((local_ip, 0))
        self.servsock.listen(1)
        ip, port = self.servsock.getsockname()
        self.conn.send('227 Entering Passive Mode (%s,%u,%u).\r\n' %
                (','.join(ip.split('.')), port >> 8 & 0xFF, port & 0xFF))

    def start_datasock(self):
        if self.pasv_mode:
            self.datasock, addr = self.servsock.accept()
        else:
            self.datasock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.datasock.connect((self.dataAddr, self.dataPort))

    def stop_datasock(self):
        self.datasock.close()
        if self.pasv_mode:
            self.servsock.close()

    def LIST(self, cmd):
        self.conn.send('150 Here comes the directory listing.\r\n')
        self.start_datasock()
        node = self.top.resolve(self.cwd)
        for sub in node.subs():
            k = self.toListItem(os.path.join(self.cwd, sub.name))
            self.datasock.send(k + '\r\n')
        self.stop_datasock()
        self.conn.send('226 Directory send OK.\r\n')

    def getattr(self, path):
        try:
            node = self.top.resolve(path)
            st = Stat()
            st.st_mode = node.mode
            st.st_nlink = node.nlinks()
            st.st_size = node.size()  # Until/unless we store the size in m.
            if self.meta:
                m = node.metadata()
                if m:
                    st.st_mode = m.mode
                    st.st_uid = m.uid
                    st.st_gid = m.gid
                    st.st_atime = max(0, xstat.fstime_floor_secs(m.atime))
                    st.st_mtime = max(0, xstat.fstime_floor_secs(m.mtime))
                    st.st_ctime = max(0, xstat.fstime_floor_secs(m.ctime))
            return st
        except vfs.NoSuchFile:
            return -errno.ENOENT

    def toListItem(self, fn):
        st = self.getattr(fn)
        fullmode = 'rwxrwxrwx'
        mode = ''
        for i in range(9):
            mode += ((st.st_mode >> (8 - i)) & 1) and fullmode[i] or '-'
        d = (stat.S_ISDIR(st.st_mode)) and 'd' or '-'
        ftime = time.strftime(' %b %d %H:%M ', time.gmtime(st.st_mtime))
        return d + mode + ' 1 user group ' + str(st.st_size) + ftime + os.path.basename(fn)

    def MKD(self, cmd):
        self.conn.send('502 Command not implemented.\r\n')

    def RMD(self, cmd):
        self.conn.send('502 Command not implemented.\r\n')

    def DELE(self, cmd):
        self.conn.send('502 Command not implemented.\r\n')

    def RNFR(self, cmd):
        self.rnfn = os.path.join(self.cwd, cmd[5:-2])
        self.conn.send('350 Ready.\r\n')

    def RNTO(self, cmd):
        self.conn.send('502 Command not implemented.\r\n')

    def REST(self, cmd):
        self.pos = int(cmd[5:-2])
        self.rest = True
        self.conn.send('250 File position reseted.\r\n')

    def RETR(self, cmd):
        fn = os.path.join(self.cwd, cmd[5:-2])
        node = self.top.resolve(fn)
        fi = node.open()
        self.conn.send('150 Opening data connection.\r\n')
        if self.rest:
            fi.seek(self.pos)
            self.rest = False
        data = fi.read(1024)
        self.start_datasock()
        while data:
            self.datasock.send(data)
            data = fi.read(1024)
        fi.close()
        self.stop_datasock()
        self.conn.send('226 Transfer complete.\r\n')

    def STOR(self,cmd):
        self.conn.send('502 Command not implemented.\r\n')

class FTPserver(threading.Thread):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((local_ip, local_port))
        threading.Thread.__init__(self)

    def run(self):
        self.sock.listen(5)
        while True:
            git.check_repo_or_die()
            top = vfs.RefList(None)
            th = FTPserverThread(top, self.sock.accept())
            th.daemon = True
            th.start()

    def stop(self):
        self.sock.close()

optspec = """
bup ftp-server
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

ftp = FTPserver()
ftp.daemon = True
ftp.start()
log('On %r' % local_ip)
log(' port %r\n' % local_port)
log('Enter to end...\n')
raw_input('\n')
ftp.stop()
