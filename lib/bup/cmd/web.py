
from binascii import hexlify
from collections import ChainMap, namedtuple
from urllib import parse
from urllib.parse import urlencode
import mimetypes, os, posixpath, signal, stat, sys, time, webbrowser

from bup import options, git, vfs, xstat
from bup.helpers \
    import (EXIT_FAILURE,
            chunkyreader,
            debug1,
            format_filesize,
            log,
            saved_errors)
from bup.io import path_msg
from bup.metadata import Metadata
from bup.path import resource_path
from bup.repo import LocalRepo

try:
    from tornado import gen
    from tornado.httpserver import HTTPServer
    from tornado.ioloop import IOLoop
    from tornado.netutil import bind_unix_socket
    import tornado.web
except ImportError:
    log('error: cannot find the python "tornado" module; please install it\n')
    sys.exit(EXIT_FAILURE)


# FIXME: right now the way hidden files are handled causes every
# directory to be traversed twice.


def http_date_from_utc_ns(utc_ns):
    return time.strftime('%a, %d %b %Y %H:%M:%S', time.gmtime(utc_ns / 10**9))


def normalize_bool(k, v):
    return 1 if v else 0


def from_req_bool(k, v):
    if v == '0': return 0
    if v == '1': return 1
    raise ValueError(f'Request {k} parameter not 0 or 1')


class ParamInfo:
    """The default indicates the value that will be assumed if the
    parameter is missing.  from_req(k, v) converts from a request
    value to the param value, e.g. perhaps from '100' to 100 for an
    integer param.  normalize(k, v) converts a proposed change to the
    canonical form, e.g. perhaps 100 to 1 for a boolean parameter.
    from_req must produce a subset of normalize's values.

    """
    __slots__ = 'default', 'from_req', 'normalize'
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def request_params(req):
    """Fully vet the incoming request arguments via the bup_param_info
    and return a dictionary of the query parameters..

    """
    param_info = req.bup_param_info
    params = {}
    for k in req.request.arguments.keys():
        info = param_info.get(k)
        if not info:
            # FIXME: eventually raise proper http error.
            raise ValueError(f'Unexpected request parameter {k!r}')
        v = req.get_argument(k, None)
        params[k] = info.from_req(k, v)
    return params


def encode_query(params, param_info):
    """Return a properly encoded query fragment (including a leading
    ?) representing the given params.

    """
    result = {}
    for k, v in params.items():
        info = param_info.get(k)
        if not info:
            # FIXME: eventually raise proper http error.
            raise ValueError(f'Unexpected request parameter {k!r}')
        v = info.normalize(k, v)
        if v == info.default:
            result.pop(k, None)
        else:
            result[k] = v
    if not result:
        return ''
    return '?' + urlencode(result)


def _compute_breadcrumbs(path, params, param_info):
    """Returns a list of breadcrumb objects for a path."""
    breadcrumbs = []
    full_path = '/'
    query = encode_query(params, param_info)
    breadcrumbs.append(('[root]', full_path + query))
    path_parts = path.split(b'/')[1:-1]
    for part in path_parts:
        full_path += parse.quote(part) + '/'
        query = encode_query(params, param_info)
        breadcrumbs.append((path_msg(part), full_path + query))
    return breadcrumbs


def _contains_hidden_files(repo, dir_item):
    """Return true if the directory contains items with names other than
    '.' and '..' that begin with '.'

    """
    for name, item in vfs.contents(repo, dir_item, want_meta=False):
        if name in (b'.', b'..'):
            continue
        if name.startswith(b'.'):
            return True
    return False


def _dir_contents(repo, resolution, params, param_info):
    """Yield the display information for the contents of dir_item."""

    def item_info(name, item, resolved_item, display_name=None,
                  include_size=False):
        link = parse.quote(name)
        # link should be based on fully resolved type to avoid extra
        # HTTP redirect.
        if stat.S_ISDIR(vfs.item_mode(resolved_item)):
            link += '/'

        if include_size:
            size = vfs.item_size(repo, item)
            if params.get('human'):
                display_size = format_filesize(size)
            else:
                display_size = size
        else:
            display_size = None

        if not display_name:
            mode = vfs.item_mode(item)
            if stat.S_ISDIR(mode):
                display_name = name + b'/'
                display_size = None
            elif stat.S_ISLNK(mode):
                display_name = name + b'@'
                display_size = None
            else:
                display_name = name

        query = encode_query(params, param_info)
        meta = resolved_item.meta
        if not isinstance(meta, Metadata):
            meta = None
        oidx = getattr(resolved_item, 'oid', None)
        if oidx: oidx = hexlify(oidx)
        return path_msg(display_name), link + query, display_size, meta, oidx

    dir_item = resolution[-1][1]
    for name, item in vfs.contents(repo, dir_item):
        if not params.get('hidden'):
            if (name not in (b'.', b'..')) and name.startswith(b'.'):
                continue
        if name == b'.':
            parent_item = resolution[-2][1] if len(resolution) > 1 else dir_item
            yield item_info(b'..', parent_item, parent_item, b'..')
            continue
        mp = params.get('meta')
        res_item = vfs.ensure_item_has_metadata(repo, item, include_size=mp)
        yield item_info(name, item, res_item, include_size=mp)


class BupRequestHandler(tornado.web.RequestHandler):

    def initialize(self, repo=None, human=None):
        self.repo = repo
        default_false_param = ParamInfo(default=0, from_req=from_req_bool,
                                        normalize=normalize_bool)
        human_param = ParamInfo(default=1 if human else 0,
                                from_req=from_req_bool,
                                normalize=normalize_bool)
        self.bup_param_info = dict(hash=default_false_param,
                                   hidden=default_false_param,
                                   human=human_param,
                                   meta=default_false_param)

    def decode_argument(self, value, name=None):
        if name == 'path':
            return value
        return super().decode_argument(value, name)

    def get(self, path):
        return self._process_request(path)

    def head(self, path):
        return self._process_request(path)

    def _process_request(self, path):
        print('Handling request for %s' % path)
        sys.stdout.flush()
        # Set want_meta because dir metadata won't be fetched, and if
        # it's not a dir, then we're going to want the metadata.
        res = vfs.resolve(self.repo, path, want_meta=True)
        leaf_name, leaf_item = res[-1]
        if not leaf_item:
            self.send_error(404)
            return
        mode = vfs.item_mode(leaf_item)
        if stat.S_ISDIR(mode):
            self._list_directory(path, res)
        else:
            self._get_file(self.repo, path, res)

    def _list_directory(self, path, resolution):
        """Helper to produce a directory listing.

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent.
        """
        param_info = self.bup_param_info
        params = request_params(self)

        if not path.endswith(b'/') and len(path) > 0:
            print('Redirecting from %s to %s' % (path_msg(path), path_msg(path + b'/')))
            query = encode_query(params, param_info)
            return self.redirect(''.join((parse.quote(path), '/', query)),
                                 permanent=True)

        def amend_query(params, **changes):
            # The changes allow us to easily avoid double curly braces in
            # templates, e.g. {**params, **{'hidden': 1}}
            return encode_query(ChainMap(changes, params), param_info)

        self.render(
            'list-directory.html',
            path=path,
            breadcrumbs=_compute_breadcrumbs(path, params, param_info),
            files_hidden=_contains_hidden_files(self.repo, resolution[-1][1]),
            local_time_str=xstat.local_time_str,
            mode_str=xstat.mode_str,
            params=params,
            amend_query=amend_query,
            dir_contents=_dir_contents(self.repo, resolution, params, param_info))
        return None

    def _set_header(self, path, file_item):
        meta = file_item.meta
        ctype = self._guess_type(path)
        assert len(file_item.oid) == 20
        if meta.mtime is not None:
            self.set_header("Last-Modified", http_date_from_utc_ns(meta.mtime))
        self.set_header("Content-Type", ctype)
        self.set_header("Etag", hexlify(file_item.oid))
        self.set_header("Content-Length", str(meta.size))

    @gen.coroutine
    def _get_file(self, repo, path, resolved):
        """Process a request on a file.

        Return value is either a file object, or None (indicating an error).
        In either case, the headers are sent.
        """
        try:
            file_item = resolved[-1][1]
            file_item = vfs.augment_item_meta(repo, file_item, include_size=True)

            # Defer the set_header() calls until after we start
            # writing so we can still generate a 500 failure if
            # something fails.
            if self.request.method == 'HEAD':
                self._set_header(path, file_item)
            else:
                set_header = False
                with vfs.fopen(self.repo, file_item) as f:
                    for blob in chunkyreader(f):
                        if not set_header:
                            self._set_header(path, file_item)
                            set_header = True
                        self.write(blob)
        except Exception as e:
            self.set_status(500)
            self.write("<h1>Server Error</h1>\n")
            self.write("%s: %s\n" % (e.__class__.__name__, str(e)))
        raise gen.Return()

    def _guess_type(self, path):
        """Guess the type of a file.

        Argument is a PATH (a filename).

        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.

        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.
        """
        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'text/plain', # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        })


io_loop = None

def handle_sigterm(signum, frame):
    global io_loop
    debug1('\nbup-web: signal %d received\n' % signum)
    log('Shutdown requested\n')
    if not io_loop:
        sys.exit(0)
    io_loop.stop()


optspec = """
bup web [[hostname]:port]
bup web unix://path
--
human-readable    display human readable file sizes (i.e. 3.9K, 4.7M)
browser           show repository in default browser (incompatible with unix://)
"""

opt = None

def main(argv):
    signal.signal(signal.SIGTERM, handle_sigterm)

    UnixAddress = namedtuple('UnixAddress', ['path'])
    InetAddress = namedtuple('InetAddress', ['host', 'port'])

    o = options.Options(optspec)
    opt, flags, extra = o.parse_bytes(argv[1:])

    if len(extra) > 1:
        o.fatal("at most one argument expected")

    if len(extra) == 0:
        address = InetAddress(host='127.0.0.1', port=8080)
    else:
        bind_url = extra[0]
        if bind_url.startswith('unix://'):
            address = UnixAddress(path=bind_url[len('unix://'):])
        else:
            addr_parts = extra[0].split(':', 1)
            if len(addr_parts) == 1:
                host = '127.0.0.1'
                port = addr_parts[0]
            else:
                host, port = addr_parts
            try:
                port = int(port)
            except (TypeError, ValueError) as ex:
                o.fatal('port must be an integer, not %r' % port)
            address = InetAddress(host=host, port=port)

    git.check_repo_or_die()

    settings = dict(
        debug = 1,
        template_path = resource_path(b'web').decode('utf-8'),
        static_path = resource_path(b'web/static').decode('utf-8'),
    )

    # Disable buffering on stdout, for debug messages
    try:
        sys.stdout._line_buffering = True
    except AttributeError:
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    with LocalRepo() as repo:
        handlers = [ (r"(?P<path>/.*)", BupRequestHandler,
                      dict(repo=repo, human=opt.human_readable))]
        application = tornado.web.Application(handlers, **settings)

        http_server = HTTPServer(application)
        io_loop_pending = IOLoop.instance()

        if isinstance(address, InetAddress):
            sockets = tornado.netutil.bind_sockets(address.port, address.host)
            http_server.add_sockets(sockets)
            print('Serving HTTP on %s:%d...' % sockets[0].getsockname()[0:2])
            if opt.browser:
                browser_addr = 'http://' + address[0] + ':' + str(address[1])
                io_loop_pending.add_callback(lambda : webbrowser.open(browser_addr))
        elif isinstance(address, UnixAddress):
            unix_socket = bind_unix_socket(address.path)
            http_server.add_socket(unix_socket)
            print('Serving HTTP on filesystem socket %r' % address.path)
        else:
            log('error: unexpected address %r', address)
            sys.exit(1)

        io_loop = io_loop_pending
        io_loop.start()

    if saved_errors:
        log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
        sys.exit(1)
