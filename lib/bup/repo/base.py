
from __future__ import absolute_import

_next_repo_id = 0
_repo_ids = {}

def _repo_id(key):
    global _next_repo_id, _repo_ids
    repo_id = _repo_ids.get(key)
    if repo_id:
        return repo_id
    next_id = _next_repo_id = _next_repo_id + 1
    _repo_ids[key] = next_id
    return next_id

class BaseRepo(object):
    def __init__(self, key):
        self._id = _repo_id(key)

    def id(self):
        """Return an identifier that differs from any other repository that
        doesn't share the same repository-specific information
        (e.g. refs, tags, etc.)."""
        return self._id
