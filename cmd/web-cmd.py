#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from __future__ import absolute_import, print_function
from collections import namedtuple
import mimetypes, os, posixpath, signal, stat, sys, time, urllib, webbrowser

from bup import options, git, vfs
from bup.helpers import (chunkyreader, debug1, format_filesize, handle_ctrl_c,
                         log, saved_errors)
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
    sys.exit(1)


# FIXME: right now the way hidden files are handled causes every
# directory to be traversed twice.

handle_ctrl_c()


def http_date_from_utc_ns(utc_ns):
    return time.strftime('%a, %d %b %Y %H:%M:%S', time.gmtime(utc_ns / 10**9))


def _compute_breadcrumbs(path, show_hidden=False):
    """Returns a list of breadcrumb objects for a path."""
    breadcrumbs = []
    breadcrumbs.append(('[root]', '/'))
    path_parts = path.split('/')[1:-1]
    full_path = '/'
    for part in path_parts:
        full_path += part + "/"
        url_append = ""
        if show_hidden:
            url_append = '?hidden=1'
        breadcrumbs.append((part, full_path+url_append))
    return breadcrumbs


def _contains_hidden_files(repo, dir_item):
    """Return true if the directory contains items with names other than
    '.' and '..' that begin with '.'

    """
    for name, item in vfs.contents(repo, dir_item, want_meta=False):
        if name in ('.', '..'):
            continue
        if name.startswith('.'):
            return True
    return False


def _dir_contents(repo, resolution, show_hidden=False):
    """Yield the display information for the contents of dir_item."""

    url_query = '?hidden=1' if show_hidden else ''

    def display_info(name, item, resolved_item, display_name=None):
        # link should be based on fully resolved type to avoid extra
        # HTTP redirect.
        if stat.S_ISDIR(vfs.item_mode(resolved_item)):
            link = urllib.quote(name) + '/'
        else:
            link = urllib.quote(name)

        size = vfs.item_size(repo, item)
        if opt.human_readable:
            display_size = format_filesize(size)
        else:
            display_size = size

        if not display_name:
            mode = vfs.item_mode(item)
            if stat.S_ISDIR(mode):
                display_name = name + '/'
            elif stat.S_ISLNK(mode):
                display_name = name + '@'
            else:
                display_name = name

        return display_name, link + url_query, display_size

    dir_item = resolution[-1][1]    
    for name, item in vfs.contents(repo, dir_item):
        if not show_hidden:
            if (name not in ('.', '..')) and name.startswith('.'):
                continue
        if name == '.':
            yield display_info(name, item, item, '.')
            parent_item = resolution[-2][1] if len(resolution) > 1 else dir_item
            yield display_info('..', parent_item, parent_item, '..')
            continue
        res = vfs.try_resolve(repo, name, parent=resolution, want_meta=False)
        res_name, res_item = res[-1]
        yield display_info(name, item, res_item)


class BupRequestHandler(tornado.web.RequestHandler):

    def initialize(self, repo=None):
        self.repo = repo

    def decode_argument(self, value, name=None):
        if name == 'path':
            return value
        return super(BupRequestHandler, self).decode_argument(value, name)

    def get(self, path):
        return self._process_request(path)

    def head(self, path):
        return self._process_request(path)
    
    def _process_request(self, path):
        path = urllib.unquote(path)
        print('Handling request for %s' % path)
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
        if not path.endswith('/') and len(path) > 0:
            print('Redirecting from %s to %s' % (path, path + '/'))
            return self.redirect(path + '/', permanent=True)

        hidden_arg = self.request.arguments.get('hidden', [0])[-1]
        try:
            show_hidden = int(hidden_arg)
        except ValueError as e:
            show_hidden = False

        self.render(
            'list-directory.html',
            path=path,
            breadcrumbs=_compute_breadcrumbs(path, show_hidden),
            files_hidden=_contains_hidden_files(self.repo, resolution[-1][1]),
            hidden_shown=show_hidden,
            dir_contents=_dir_contents(self.repo, resolution,
                                       show_hidden=show_hidden))

    @gen.coroutine
    def _get_file(self, repo, path, resolved):
        """Process a request on a file.

        Return value is either a file object, or None (indicating an error).
        In either case, the headers are sent.
        """
        file_item = resolved[-1][1]
        file_item = vfs.augment_item_meta(repo, file_item, include_size=True)
        meta = file_item.meta
        ctype = self._guess_type(path)
        self.set_header("Last-Modified", http_date_from_utc_ns(meta.mtime))
        self.set_header("Content-Type", ctype)
        
        self.set_header("Content-Length", str(meta.size))
        assert len(file_item.oid) == 20
        self.set_header("Etag", file_item.oid.encode('hex'))
        if self.request.method != 'HEAD':
            with vfs.fopen(self.repo, file_item) as f:
                it = chunkyreader(f)
                for blob in chunkyreader(f):
                    self.write(blob)
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


signal.signal(signal.SIGTERM, handle_sigterm)

UnixAddress = namedtuple('UnixAddress', ['path'])
InetAddress = namedtuple('InetAddress', ['host', 'port'])

optspec = """
bup web [[hostname]:port]
bup web unix://path
--
human-readable    display human readable file sizes (i.e. 3.9K, 4.7M)
browser           show repository in default browser (incompatible with unix://)
"""
o = options.Options(optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

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
    template_path = resource_path('web'),
    static_path = resource_path('web/static')
)

# Disable buffering on stdout, for debug messages
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

application = tornado.web.Application([
    (r"(?P<path>/.*)", BupRequestHandler, dict(repo=LocalRepo())),
], **settings)

http_server = HTTPServer(application)
io_loop_pending = IOLoop.instance()

if isinstance(address, InetAddress):
    http_server.listen(address.port, address.host)
    try:
        sock = http_server._socket # tornado < 2.0
    except AttributeError as e:
        sock = http_server._sockets.values()[0]
    print('Serving HTTP on %s:%d...' % sock.getsockname())
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
