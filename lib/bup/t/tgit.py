
from __future__ import absolute_import
from os import environ
from subprocess import check_call
import struct, os, time

from wvtest import *

from bup import git
from bup.compat import range
from bup.helpers import localtime, log, mkdirp, readpipe
from buptest import no_lingering_errors, test_tempdir


top_dir = os.path.realpath('../../..')
bup_exe = top_dir + '/bup'


def exc(*cmd):
    cmd_str = ' '.join(cmd)
    print >> sys.stderr, cmd_str
    check_call(cmd)


def exo(*cmd):
    cmd_str = ' '.join(cmd)
    print >> sys.stderr, cmd_str
    return readpipe(cmd)


@wvtest
def test_git_version_detection():
    with no_lingering_errors():
        # Test version types from git's tag history
        for expected, ver in \
            (('insufficient', b'git version 0.99'),
             ('insufficient', b'git version 0.99.1'),
             ('insufficient', b'git version 0.99.7a'),
             ('insufficient', b'git version 1.0rc1'),
             ('insufficient', b'git version 1.0.1'),
             ('insufficient', b'git version 1.4.2.1'),
             ('insufficient', b'git version 1.5.5'),
             ('insufficient', b'git version 1.5.6-rc0'),
             ('suitable', b'git version 1.5.6'),
             ('suitable', b'git version 1.5.6.1'),
             ('suitable', b'git version 2.14.0-rc0'),
             ('suitable', b'git version 2.14.0 (something ...)'),
             ('suitable', b'git version 111.222.333.444-rc555'),
             ('unrecognized', b'huh?')):
            WVMSG('Checking version validation: %r' % ver)
            WVPASSEQ(expected, git.is_suitable_git(ver_str=ver))
            try:
                if expected == 'insufficient':
                    WVEXCEPT(SystemExit, git.require_suitable_git, ver)
                elif expected == 'suitable':
                    git.require_suitable_git(ver_str=ver)
                elif expected == 'unrecognized':
                    WVEXCEPT(git.GitError, git.require_suitable_git, ver)
                else:
                    WVPASS(False)
            finally:
                git._git_great = None
            try:
                environ[b'BUP_GIT_VERSION_IS_FINE'] = b'true'
                git.require_suitable_git(ver_str=ver)
            finally:
                del environ[b'BUP_GIT_VERSION_IS_FINE']
                git._git_great = None


@wvtest
def testmangle():
    with no_lingering_errors():
        afile  = 0o100644
        afile2 = 0o100770
        alink  = 0o120000
        adir   = 0o040000
        adir2  = 0o040777
        WVPASSEQ(git.mangle_name("a", adir2, adir), "a")
        WVPASSEQ(git.mangle_name(".bup", adir2, adir), ".bup.bupl")
        WVPASSEQ(git.mangle_name("a.bupa", adir2, adir), "a.bupa.bupl")
        WVPASSEQ(git.mangle_name("b.bup", alink, alink), "b.bup.bupl")
        WVPASSEQ(git.mangle_name("b.bu", alink, alink), "b.bu")
        WVPASSEQ(git.mangle_name("f", afile, afile2), "f")
        WVPASSEQ(git.mangle_name("f.bup", afile, afile2), "f.bup.bupl")
        WVPASSEQ(git.mangle_name("f.bup", afile, adir), "f.bup.bup")
        WVPASSEQ(git.mangle_name("f", afile, adir), "f.bup")

        WVPASSEQ(git.demangle_name("f.bup", afile), ("f", git.BUP_CHUNKED))
        WVPASSEQ(git.demangle_name("f.bupl", afile), ("f", git.BUP_NORMAL))
        WVPASSEQ(git.demangle_name("f.bup.bupl", afile), ("f.bup", git.BUP_NORMAL))

        WVPASSEQ(git.demangle_name(".bupm", afile), ('', git.BUP_NORMAL))
        WVPASSEQ(git.demangle_name(".bupm", adir), ('', git.BUP_CHUNKED))

        # for safety, we ignore .bup? suffixes we don't recognize.  Future
        # versions might implement a .bup[a-z] extension as something other
        # than BUP_NORMAL.
        WVPASSEQ(git.demangle_name("f.bupa", afile), ("f.bupa", git.BUP_NORMAL))


@wvtest
def testencode():
    with no_lingering_errors():
        s = 'hello world'
        looseb = ''.join(git._encode_looseobj('blob', s))
        looset = ''.join(git._encode_looseobj('tree', s))
        loosec = ''.join(git._encode_looseobj('commit', s))
        packb = ''.join(git._encode_packobj('blob', s))
        packt = ''.join(git._encode_packobj('tree', s))
        packc = ''.join(git._encode_packobj('commit', s))
        WVPASSEQ(git._decode_looseobj(looseb), ('blob', s))
        WVPASSEQ(git._decode_looseobj(looset), ('tree', s))
        WVPASSEQ(git._decode_looseobj(loosec), ('commit', s))
        WVPASSEQ(git._decode_packobj(packb), ('blob', s))
        WVPASSEQ(git._decode_packobj(packt), ('tree', s))
        WVPASSEQ(git._decode_packobj(packc), ('commit', s))
        for i in range(10):
            WVPASS(git._encode_looseobj('blob', s, compression_level=i))
        def encode_pobj(n):
            return ''.join(git._encode_packobj('blob', s, compression_level=n))
        WVEXCEPT(ValueError, encode_pobj, -1)
        WVEXCEPT(ValueError, encode_pobj, 10)
        WVEXCEPT(ValueError, encode_pobj, 'x')


@wvtest
def testpacks():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            git.init_repo(bupdir)
            git.verbose = 1

            w = git.PackWriter()
            w.new_blob(os.urandom(100))
            w.new_blob(os.urandom(100))
            w.abort()

            w = git.PackWriter()
            hashes = []
            nobj = 1000
            for i in range(nobj):
                hashes.append(w.new_blob(str(i)))
            log('\n')
            nameprefix = w.close()
            print repr(nameprefix)
            WVPASS(os.path.exists(nameprefix + '.pack'))
            WVPASS(os.path.exists(nameprefix + '.idx'))

            r = git.open_idx(nameprefix + '.idx')
            print repr(r.fanout)

            for i in range(nobj):
                WVPASS(r.find_offset(hashes[i]) > 0)
            WVPASS(r.exists(hashes[99]))
            WVFAIL(r.exists('\0'*20))

            pi = iter(r)
            for h in sorted(hashes):
                WVPASSEQ(str(next(pi)).encode('hex'), h.encode('hex'))

            WVFAIL(r.find_offset('\0'*20))

            r = git.PackIdxList(bupdir + '/objects/pack')
            WVPASS(r.exists(hashes[5]))
            WVPASS(r.exists(hashes[6]))
            WVFAIL(r.exists('\0'*20))


@wvtest
def test_pack_name_lookup():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            git.init_repo(bupdir)
            git.verbose = 1
            packdir = git.repo('objects/pack')

            idxnames = []
            hashes = []

            for start in range(0,28,2):
                w = git.PackWriter()
                for i in range(start, start+2):
                    hashes.append(w.new_blob(str(i)))
                log('\n')
                idxnames.append(os.path.basename(w.close() + '.idx'))

            r = git.PackIdxList(packdir)
            WVPASSEQ(len(r.packs), 2)
            for e,idxname in enumerate(idxnames):
                for i in range(e*2, (e+1)*2):
                    WVPASSEQ(r.exists(hashes[i], want_source=True), idxname)


@wvtest
def test_long_index():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            git.init_repo(bupdir)
            idx = git.PackIdxV2Writer()
            obj_bin = struct.pack('!IIIII',
                    0x00112233, 0x44556677, 0x88990011, 0x22334455, 0x66778899)
            obj2_bin = struct.pack('!IIIII',
                    0x11223344, 0x55667788, 0x99001122, 0x33445566, 0x77889900)
            obj3_bin = struct.pack('!IIIII',
                    0x22334455, 0x66778899, 0x00112233, 0x44556677, 0x88990011)
            pack_bin = struct.pack('!IIIII',
                    0x99887766, 0x55443322, 0x11009988, 0x77665544, 0x33221100)
            idx.add(obj_bin, 1, 0xfffffffff)
            idx.add(obj2_bin, 2, 0xffffffffff)
            idx.add(obj3_bin, 3, 0xff)
            name = tmpdir + b'/tmp.idx'
            r = idx.write(name, pack_bin)
            i = git.PackIdxV2(name, open(name, 'rb'))
            WVPASSEQ(i.find_offset(obj_bin), 0xfffffffff)
            WVPASSEQ(i.find_offset(obj2_bin), 0xffffffffff)
            WVPASSEQ(i.find_offset(obj3_bin), 0xff)


@wvtest
def test_check_repo_or_die():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            orig_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                git.init_repo(bupdir)
                git.check_repo_or_die()
                # if we reach this point the call above passed
                WVPASS('check_repo_or_die')

                os.rename(bupdir + '/objects/pack',
                          bupdir + '/objects/pack.tmp')
                open(bupdir + '/objects/pack', 'w').close()
                try:
                    git.check_repo_or_die()
                except SystemExit as e:
                    WVPASSEQ(e.code, 14)
                else:
                    WVFAIL()
                os.unlink(bupdir + '/objects/pack')
                os.rename(bupdir + '/objects/pack.tmp',
                          bupdir + '/objects/pack')

                try:
                    git.check_repo_or_die('nonexistantbup.tmp')
                except SystemExit as e:
                    WVPASSEQ(e.code, 15)
                else:
                    WVFAIL()
            finally:
                os.chdir(orig_cwd)


@wvtest
def test_commit_parsing():

    def restore_env_var(name, val):
        if val is None:
            del os.environ[name]
        else:
            os.environ[name] = val

    def showval(commit, val):
        return readpipe(['git', 'show', '-s',
                         '--pretty=format:%s' % val, commit]).strip()

    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            orig_cwd = os.getcwd()
            workdir = tmpdir + "/work"
            repodir = workdir + '/.git'
            orig_author_name = os.environ.get('GIT_AUTHOR_NAME')
            orig_author_email = os.environ.get('GIT_AUTHOR_EMAIL')
            orig_committer_name = os.environ.get('GIT_COMMITTER_NAME')
            orig_committer_email = os.environ.get('GIT_COMMITTER_EMAIL')
            os.environ['GIT_AUTHOR_NAME'] = 'bup test'
            os.environ['GIT_COMMITTER_NAME'] = os.environ['GIT_AUTHOR_NAME']
            os.environ['GIT_AUTHOR_EMAIL'] = 'bup@a425bc70a02811e49bdf73ee56450e6f'
            os.environ['GIT_COMMITTER_EMAIL'] = os.environ['GIT_AUTHOR_EMAIL']
            try:
                readpipe(['git', 'init', workdir])
                os.environ['GIT_DIR'] = os.environ['BUP_DIR'] = repodir
                git.check_repo_or_die(repodir)
                os.chdir(workdir)
                with open('foo', 'w') as f:
                    print >> f, 'bar'
                readpipe(['git', 'add', '.'])
                readpipe(['git', 'commit', '-am', 'Do something',
                          '--author', 'Someone <someone@somewhere>',
                          '--date', 'Sat Oct 3 19:48:49 2009 -0400'])
                commit = readpipe(['git', 'show-ref', '-s', 'master']).strip()
                parents = showval(commit, '%P')
                tree = showval(commit, '%T')
                cname = showval(commit, '%cn')
                cmail = showval(commit, '%ce')
                cdate = showval(commit, '%ct')
                coffs = showval(commit, '%ci')
                coffs = coffs[-5:]
                coff = (int(coffs[-4:-2]) * 60 * 60) + (int(coffs[-2:]) * 60)
                if coffs[-5] == '-':
                    coff = - coff
                commit_items = git.get_commit_items(commit, git.cp())
                WVPASSEQ(commit_items.parents, [])
                WVPASSEQ(commit_items.tree, tree)
                WVPASSEQ(commit_items.author_name, 'Someone')
                WVPASSEQ(commit_items.author_mail, 'someone@somewhere')
                WVPASSEQ(commit_items.author_sec, 1254613729)
                WVPASSEQ(commit_items.author_offset, -(4 * 60 * 60))
                WVPASSEQ(commit_items.committer_name, cname)
                WVPASSEQ(commit_items.committer_mail, cmail)
                WVPASSEQ(commit_items.committer_sec, int(cdate))
                WVPASSEQ(commit_items.committer_offset, coff)
                WVPASSEQ(commit_items.message, 'Do something\n')
                with open('bar', 'w') as f:
                    print >> f, 'baz'
                readpipe(['git', 'add', '.'])
                readpipe(['git', 'commit', '-am', 'Do something else'])
                child = readpipe(['git', 'show-ref', '-s', 'master']).strip()
                parents = showval(child, '%P')
                commit_items = git.get_commit_items(child, git.cp())
                WVPASSEQ(commit_items.parents, [commit])
            finally:
                os.chdir(orig_cwd)
                restore_env_var('GIT_AUTHOR_NAME', orig_author_name)
                restore_env_var('GIT_AUTHOR_EMAIL', orig_author_email)
                restore_env_var('GIT_COMMITTER_NAME', orig_committer_name)
                restore_env_var('GIT_COMMITTER_EMAIL', orig_committer_email)


@wvtest
def test_new_commit():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            git.init_repo(bupdir)
            git.verbose = 1

            w = git.PackWriter()
            tree = os.urandom(20)
            parent = os.urandom(20)
            author_name = 'Author'
            author_mail = 'author@somewhere'
            adate_sec = 1439657836
            cdate_sec = adate_sec + 1
            committer_name = 'Committer'
            committer_mail = 'committer@somewhere'
            adate_tz_sec = cdate_tz_sec = None
            commit = w.new_commit(tree, parent,
                                  '%s <%s>' % (author_name, author_mail),
                                  adate_sec, adate_tz_sec,
                                  '%s <%s>' % (committer_name, committer_mail),
                                  cdate_sec, cdate_tz_sec,
                                  'There is a small mailbox here')
            adate_tz_sec = -60 * 60
            cdate_tz_sec = 120 * 60
            commit_off = w.new_commit(tree, parent,
                                      '%s <%s>' % (author_name, author_mail),
                                      adate_sec, adate_tz_sec,
                                      '%s <%s>' % (committer_name, committer_mail),
                                      cdate_sec, cdate_tz_sec,
                                      'There is a small mailbox here')
            w.close()

            commit_items = git.get_commit_items(commit.encode('hex'), git.cp())
            local_author_offset = localtime(adate_sec).tm_gmtoff
            local_committer_offset = localtime(cdate_sec).tm_gmtoff
            WVPASSEQ(tree, commit_items.tree.decode('hex'))
            WVPASSEQ(1, len(commit_items.parents))
            WVPASSEQ(parent, commit_items.parents[0].decode('hex'))
            WVPASSEQ(author_name, commit_items.author_name)
            WVPASSEQ(author_mail, commit_items.author_mail)
            WVPASSEQ(adate_sec, commit_items.author_sec)
            WVPASSEQ(local_author_offset, commit_items.author_offset)
            WVPASSEQ(committer_name, commit_items.committer_name)
            WVPASSEQ(committer_mail, commit_items.committer_mail)
            WVPASSEQ(cdate_sec, commit_items.committer_sec)
            WVPASSEQ(local_committer_offset, commit_items.committer_offset)

            commit_items = git.get_commit_items(commit_off.encode('hex'), git.cp())
            WVPASSEQ(tree, commit_items.tree.decode('hex'))
            WVPASSEQ(1, len(commit_items.parents))
            WVPASSEQ(parent, commit_items.parents[0].decode('hex'))
            WVPASSEQ(author_name, commit_items.author_name)
            WVPASSEQ(author_mail, commit_items.author_mail)
            WVPASSEQ(adate_sec, commit_items.author_sec)
            WVPASSEQ(adate_tz_sec, commit_items.author_offset)
            WVPASSEQ(committer_name, commit_items.committer_name)
            WVPASSEQ(committer_mail, commit_items.committer_mail)
            WVPASSEQ(cdate_sec, commit_items.committer_sec)
            WVPASSEQ(cdate_tz_sec, commit_items.committer_offset)


@wvtest
def test_list_refs():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            src = tmpdir + '/src'
            mkdirp(src)
            with open(src + '/1', 'w+') as f:
                print f, 'something'
            with open(src + '/2', 'w+') as f:
                print f, 'something else'
            git.init_repo(bupdir)
            emptyset = frozenset()
            WVPASSEQ(frozenset(git.list_refs()), emptyset)
            WVPASSEQ(frozenset(git.list_refs(limit_to_tags=True)), emptyset)
            WVPASSEQ(frozenset(git.list_refs(limit_to_heads=True)), emptyset)
            exc(bup_exe, 'index', src)
            exc(bup_exe, 'save', '-n', 'src', '--strip', src)
            src_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src').strip().split('\n')
            assert(len(src_hash) == 1)
            src_hash = src_hash[0].decode('hex')
            tree_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src:').strip().split('\n')[0].decode('hex')
            blob_hash = exo('git', '--git-dir', bupdir,
                           'rev-parse', 'src:1').strip().split('\n')[0].decode('hex')
            WVPASSEQ(frozenset(git.list_refs()),
                     frozenset([('refs/heads/src', src_hash)]))
            WVPASSEQ(frozenset(git.list_refs(limit_to_tags=True)), emptyset)
            WVPASSEQ(frozenset(git.list_refs(limit_to_heads=True)),
                     frozenset([('refs/heads/src', src_hash)]))
            exc('git', '--git-dir', bupdir, 'tag', 'commit-tag', 'src')
            WVPASSEQ(frozenset(git.list_refs()),
                     frozenset([('refs/heads/src', src_hash),
                                ('refs/tags/commit-tag', src_hash)]))
            WVPASSEQ(frozenset(git.list_refs(limit_to_tags=True)),
                     frozenset([('refs/tags/commit-tag', src_hash)]))
            WVPASSEQ(frozenset(git.list_refs(limit_to_heads=True)),
                     frozenset([('refs/heads/src', src_hash)]))
            exc('git', '--git-dir', bupdir, 'tag', 'tree-tag', 'src:')
            exc('git', '--git-dir', bupdir, 'tag', 'blob-tag', 'src:1')
            os.unlink(bupdir + '/refs/heads/src')
            expected_tags = frozenset([('refs/tags/commit-tag', src_hash),
                                       ('refs/tags/tree-tag', tree_hash),
                                       ('refs/tags/blob-tag', blob_hash)])
            WVPASSEQ(frozenset(git.list_refs()), expected_tags)
            WVPASSEQ(frozenset(git.list_refs(limit_to_heads=True)), frozenset([]))
            WVPASSEQ(frozenset(git.list_refs(limit_to_tags=True)), expected_tags)


@wvtest
def test__git_date_str():
    with no_lingering_errors():
        WVPASSEQ('0 +0000', git._git_date_str(0, 0))
        WVPASSEQ('0 -0130', git._git_date_str(0, -90 * 60))
        WVPASSEQ('0 +0130', git._git_date_str(0, 90 * 60))


@wvtest
def test_cat_pipe():
    with no_lingering_errors():
        with test_tempdir('bup-tgit-') as tmpdir:
            os.environ['BUP_MAIN_EXE'] = bup_exe
            os.environ['BUP_DIR'] = bupdir = tmpdir + "/bup"
            src = tmpdir + '/src'
            mkdirp(src)
            with open(src + '/1', 'w+') as f:
                print f, 'something'
            with open(src + '/2', 'w+') as f:
                print f, 'something else'
            git.init_repo(bupdir)
            exc(bup_exe, 'index', src)
            oidx = exo(bup_exe, 'save', '-cn', 'src', '--strip', src).strip()
            typ = exo('git', '--git-dir', bupdir,
                      'cat-file', '-t', 'src').strip()
            size = int(exo('git', '--git-dir', bupdir,
                               'cat-file', '-s', 'src'))
            it = git.cp().get('src')
            get_info = it.next()
            for buf in it.next():
                pass
            WVPASSEQ((oidx, typ, size), get_info)

def _create_idx(d, i):
    idx = git.PackIdxV2Writer()
    # add 255 vaguely reasonable entries
    for s in range(255):
        idx.add(struct.pack('18xBB', i, s), s, 100 * s)
    packbin = struct.pack('B19x', i)
    packname = os.path.join(d, b'pack-%s.idx' % packbin.encode('hex'))
    idx.write(packname, packbin)

@wvtest
def test_midx_close():
    fddir = b'/proc/self/fd'
    try:
        os.listdir(fddir)
    except Exception:
        # not supported, not Linux, I guess
        return

    def openfiles():
        for fd in os.listdir(fddir):
            try:
                yield os.readlink(os.path.join(fddir, fd))
            except OSError:
                pass

    def force_midx(objdir):
        args = [path.exe(), b'midx', b'--auto', b'--dir', objdir]
        check_call(args)

    with no_lingering_errors(), \
         test_tempdir(b'bup-tgit-') as tmpdir:
        environ[b'BUP_DIR'] = bupdir = tmpdir + b'/bup'
        git.init_repo(bupdir)
        # create a few dummy idxes
        for i in range(10):
            _create_idx(tmpdir, i)
        git.auto_midx(tmpdir)
        l = git.PackIdxList(tmpdir)
        # this doesn't exist (yet)
        WVPASSEQ(None, l.exists(struct.pack('18xBB', 10, 0)))
        for i in range(10, 15):
            _create_idx(tmpdir, i)
        # delete the midx ...
        # TODO: why do we need to? git.auto_midx() below doesn't?!
        for fn in os.listdir(tmpdir):
            if fn.endswith(b'.midx'):
                os.unlink(os.path.join(tmpdir, fn))
        # and make a new one
        git.auto_midx(tmpdir)
        # check it still doesn't exist - we haven't refreshed
        WVPASSEQ(None, l.exists(struct.pack('18xBB', 10, 0)))
        # check that we still have the midx open, this really
        # just checks more for the kernel API ('deleted' string)
        for fn in openfiles():
            if not b'midx-' in fn:
                continue
            WVPASSEQ(True, b'deleted' in fn)
        # refresh the PackIdxList
        l.refresh()
        # and check that an object in pack 10 exists now
        WVPASSEQ(True, l.exists(struct.pack('18xBB', 10, 0)))
        for fn in openfiles():
            if not b'midx-' in fn:
                continue
            # check that we don't have it open anymore
            WVPASSEQ(False, b'deleted' in fn)
