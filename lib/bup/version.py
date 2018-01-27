
from __future__ import absolute_import

from bup import _release

if _release.COMMIT != '$Format:%H$':
    from bup._release import COMMIT, DATE, NAMES
else:
    from bup._checkout import COMMIT, DATE, NAMES
