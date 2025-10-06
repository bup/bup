
from binascii import hexlify

from bup.io import enc_sh, log


def valid_repair_id(s):
    assert isinstance(s, bytes), s
    for b in s:
        if b < 32 or b > 126:
            return False
    return True


class Repairs:
    # Used, for example, to track all repairs in a bup get process
    __slots__ = ('id', 'destructive', 'command', '_others', '_replacements')
    def __init__(self, id, destructive, command):
        assert valid_repair_id(id)
        self.id = id
        self.destructive = destructive
        self.command = command
        self._others = 0
        self._replacements = []
    def repair_count(self): return len(self._replacements) + self._others
    def note_incidental_repair(self):
        # "Safe" repairs that don't involve the repair id.
        self._others += 1
    def path_replaced(self, path, oid, new_oid):
        if self.repair_count() == 0:
            log(b'repairs needed, repair-id: %s\n' % self.id)
        self._replacements.append((path, oid, new_oid))
    def repair_trailers(self, repair_id):
        assert valid_repair_id(repair_id)
        if not self.repair_count():
            return []
        trailers = [b'Bup-Repair-ID: ' + repair_id]
        for path, oid, new_oid in self._replacements:
            trailers.append(b'Bup-Replaced: %s %s'
                            % (hexlify(new_oid), enc_sh(path)))
        return trailers
