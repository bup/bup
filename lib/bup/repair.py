
from binascii import hexlify

from bup.io import enc_sh, log
from bup.vfs import Commit, RevList, render_path


def valid_repair_id(s):
    assert isinstance(s, bytes), s
    for b in s:
        if b < 32 or b > 126:
            return False
    return True

class Repairs:
    # Used, for example, to track all repairs in a bup get process
    __slots__ = ('id', 'destructive', 'command', '_others', '_repaired_save',
                 '_replaced_files', '_replaced_meta', '_restored_symlink_blobs',
                 '_fixed_symlink_blobs')
    def __init__(self, id, destructive, command):
        assert valid_repair_id(id)
        self.id = id
        self.destructive = destructive
        self.command = command
        self._others = 0
        self._repaired_save = {} # requires 3.7+ dict ordering
        self._replaced_files = []
        self._replaced_meta = []
        self._restored_symlink_blobs = []
        self._fixed_symlink_blobs = []
    def repair_count(self):
        return len(self._replaced_files) \
            + len(self._replaced_meta) \
            + len(self._restored_symlink_blobs) \
            + len(self._fixed_symlink_blobs) \
            + self._others
    def note_incidental_repair(self):
        # "Safe" repairs that don't involve the repair id.
        self._others += 1
    def _remember_save(self, path):
        revlist, commit = path[1:3]
        assert isinstance(revlist[1], RevList), path
        assert isinstance(commit[1], Commit), path
        path = b'%s/%s' % (revlist[0], commit[0])
        existing = self._repaired_save.setdefault(path, commit[1].coid)
        if existing:
            assert existing == commit[1].coid, (existing, revlist, commit)
    def meta_replaced(self, path):
        if self.repair_count() == 0:
            log(b'repairs needed, repair-id: %s\n' % self.id)
        self._remember_save(path)
        self._replaced_meta.append(render_path(path[3:]))
    def path_replaced(self, path, oid, new_oid):
        if self.repair_count() == 0:
            log(b'repairs needed, repair-id: %s\n' % self.id)
        self._remember_save(path)
        self._replaced_files.append((render_path(path[3:]), oid, new_oid))
    def link_blob_restored(self, path, oid):
        if self.repair_count() == 0:
            log(b'repairs needed, repair-id: %s\n' % self.id)
        self._remember_save(path)
        self._restored_symlink_blobs.append((render_path(path[3:]), oid))
    def link_blob_fixed(self, path, prev_blob):
        if self.repair_count() == 0:
            log(b'repairs needed, repair-id: %s\n' % self.id)
        self._remember_save(path)
        self._fixed_symlink_blobs.append((render_path(path[3:]), prev_blob))
    def repair_trailers(self, repair_id):
        assert valid_repair_id(repair_id)
        if not self.repair_count():
            return []
        trailers = [b'Bup-Repair-ID: ' + repair_id]
        for save_path, coid in self._repaired_save.items():
            trailers.append(b'Bup-Repaired-Save: %s %s'
                            % (hexlify(coid), enc_sh(save_path)))
        for path, oid, new_oid in self._replaced_files:
            trailers.append(b'Bup-Replaced: %s %s'
                            % (hexlify(new_oid), enc_sh(path)))
        for path, oid in self._restored_symlink_blobs:
            trailers.append(b'Bup-Restored-Link-Blob: %s %s'
                            % (hexlify(oid), enc_sh(path)))
        for path, prev_blob in self._fixed_symlink_blobs:
            trailers.append(b'Bup-Fixed-Link-Blob: was %s for %s'
                            % (enc_sh(prev_blob), enc_sh(path)))
        for path in self._replaced_meta:
            trailers.append(b'Bup-Lost-Meta: %s' % enc_sh(path))
        return trailers
