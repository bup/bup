from bup.helpers import *
from wvtest import *

@wvtest
def test_parse_num():
    pn = parse_num
    WVPASSEQ(pn('1'), 1)
    WVPASSEQ(pn('0'), 0)
    WVPASSEQ(pn('1.5k'), 1536)
    WVPASSEQ(pn('2 gb'), 2*1024*1024*1024)
    WVPASSEQ(pn('1e+9 k'), 1000000000 * 1024)
    WVPASSEQ(pn('-3e-3mb'), int(-0.003 * 1024 * 1024))

@wvtest
def test_strip_path():
    prefix = "/var/backup/daily.0/localhost"
    empty_prefix = ""
    non_matching_prefix = "/home"
    path = "/var/backup/daily.0/localhost/etc/"

    WVPASSEQ(strip_path(prefix, path), '/etc')
    WVPASSEQ(strip_path(empty_prefix, path), path)
    WVPASSEQ(strip_path(non_matching_prefix, path), path)
    WVEXCEPT(Exception, strip_path, None, path)

@wvtest
def test_strip_base_path():
    path = "/var/backup/daily.0/localhost/etc/"
    base_paths = ["/var", "/var/backup", "/var/backup/daily.0/localhost"]
    WVPASSEQ(strip_base_path(path, base_paths), '/etc')

@wvtest
def test_graft_path():
    middle_matching_old_path = "/user"
    non_matching_old_path = "/usr"
    matching_old_path = "/home"
    matching_full_path = "/home/user"
    new_path = "/opt"

    all_graft_points = [(middle_matching_old_path, new_path),
                        (non_matching_old_path, new_path),
                        (matching_old_path, new_path)]

    path = "/home/user/"

    WVPASSEQ(graft_path([(middle_matching_old_path, new_path)], path),
                        "/home/user")
    WVPASSEQ(graft_path([(non_matching_old_path, new_path)], path),
                        "/home/user")
    WVPASSEQ(graft_path([(matching_old_path, new_path)], path), "/opt/user")
    WVPASSEQ(graft_path(all_graft_points, path), "/opt/user")
    WVPASSEQ(graft_path([(matching_full_path, new_path)], path),
                        "/opt")
