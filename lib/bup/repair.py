
from binascii import hexlify
from typing import Optional, Union

from bup.compat import dataclass
from bup.io import enc_sh


def valid_repair_id(s):
    assert isinstance(s, bytes), s
    for b in s:
        if b < 32 or b > 126:
            return False
    return True


class RepairInfo:
    # Used, for example, to track all repairs in a bup get process
    __slots__ = 'command', '_others', '_replacements'
    def __init__(self, *, command=None):
        self.command = command
        self._others = 0
        self._replacements = []
    def note_repair(self): self._others += 1
    def path_replaced(self, path, oid, new_oid):
        self._replacements.append((path, oid, new_oid))
    def repair_count(self): return len(self._replacements) + self._others
    def repair_trailers(self, repair_id):
        assert valid_repair_id(repair_id)
        if not self.repair_count():
            return []
        trailers = [b'Bup-Repair-ID: ' + repair_id]
        for path, oid, new_oid in self._replacements:
            trailers.append(b'Bup-Replaced: %s %s'
                            % (hexlify(new_oid), enc_sh(path)))
        return trailers


@dataclass(slots=True, frozen=True)
class MissingConfig:
    id: bytes
    mode: Union['fail', 'ignore', 'replace']
    repair_info: Optional[RepairInfo] = None
    def __post_init__(self):
        assert valid_repair_id(self.id)
        assert self.mode in ('fail', 'ignore', 'replace')
        if self.mode == 'replace':
            assert isinstance(self.repair_info, RepairInfo), self.repair_info
