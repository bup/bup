
from os import environb as environ
from pathlib import Path
from subprocess import CalledProcessError
import os, pytest, subprocess, sys

from bup.compat import fsdecode
from bup.helpers import temp_dir
from bup.io import byte_stream

# Handle all test-* files as wvtest protocol subprocesses
# cf. https://docs.pytest.org/en/latest/example/nonpython.html

# version_tuple was added in 7.0
pytest_ver = getattr(pytest, 'version_tuple', None)

class BupSubprocFailure(Exception):
    def __init__(self, msg, cmd, status, failures):
        super().__init__(msg)
        self.cmd = cmd
        self.status = status
        self.failures = failures

class BupSubprocTestRunner(pytest.Item):

    def __init__(self, name, parent):
        super().__init__(name, parent)

    def runtest(self):
        cmd = str(self.fspath)
        with temp_dir(dir=os.path.abspath(b'test/tmp'), prefix=b'bup-test-home-') as home:
            env = environ.copy()
            env[b'HOME'] = home
            p = subprocess.Popen(cmd,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT,
                                 env=env)
            out = p.communicate()[0]
        sys.stdout.flush()
        byte_stream(sys.stdout).write(out)
        lines = out.splitlines()
        for line in lines:
            if line.startswith(b'!') and line.lower().endswith(b' skip ok'):
                pytest.skip(line.decode('ascii'))
                return
        failures = [line for line in lines
                    if (line.startswith(b'!')
                        and line.lower().endswith(b' failed'))]
        if b'AssertionError' in out:
            raise BupSubprocFailure('AssertionError detected')
        if failures or p.returncode != 0:
            raise BupSubprocFailure('%s failed (exit %d, %d failures)'
                                    % (cmd, p.returncode, len(failures)),
                                    cmd, p.returncode, failures)

    def repr_failure(self, excinfo):
        ex = excinfo.value
        if isinstance(ex, BupSubprocFailure):
            msg = ['Exit status: %d' % ex.status,
                   'Failures:']
            msg.extend(fsdecode(s) for s in ex.failures)
            return '\n'.join(msg)

    def reportinfo(self):
        # This does not appear to be documented, but is in the
        # example, and sets the final report header line (at least)
        # for failures.
        test_name = str(self.fspath)
        linenum = None
        return self.fspath, linenum, test_name

class BupSubprocTestFile(pytest.File):
    def collect(self):
        name = self.fspath.basename
        # name='' because there's only one test: running the command.
        # i.e there are no sub-tests.  Otherwise the status messages
        # duplicate the test name like this:
        #   test/ext/test-cat-file.sh::test-cat-file.sh PASSED ...
        try:
            yield BupSubprocTestRunner.from_parent(self, name='')
        except AttributeError:
            yield BupSubprocTestRunner('', self)

def _collect_item(item):
    name = os.path.basename(item.name)
    if name.startswith('test-') and not name.endswith('~'):
        if name == 'test-versioning-and-archive':
            item.add_marker(pytest.mark.release)
        return item

if pytest_ver: # 7+
    def pytest_collect_file(parent, file_path):
        item = BupSubprocTestFile.from_parent(parent, path=file_path)
        return _collect_item(item)
else:
    def pytest_collect_file(parent, path):
        try:
            item = BupSubprocTestFile.from_parent(parent, fspath=path)
        except AttributeError:
            item = BupSubprocTestFile(path, parent)
        return _collect_item(item)
