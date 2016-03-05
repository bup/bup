#!/bin/sh
"""": # -*-python-*-
bup_python="$(dirname "$0")/bup-python" || exit $?
exec "$bup_python" "$0" ${1+"$@"}
"""
# end of bup preamble

from collections import namedtuple
import mimetypes, os, posixpath, signal, stat, sys, time, urllib, webbrowser

from bup import options, git, vfs
from bup.helpers import (chunkyreader, debug1, handle_ctrl_c, log,
                         resource_path, saved_errors)

try:
    from tornado.httpserver import HTTPServer
    from tornado.ioloop import IOLoop
    from tornado.netutil import bind_unix_socket
    import tornado.web
except ImportError:
    log('error: cannot find the python "tornado" module; please install it\n')
    sys.exit(1)


handle_ctrl_c()


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


def _contains_hidden_files(n):
    """Return True if n contains files starting with a '.', False otherwise."""
    for sub in n:
        name = sub.name
        if len(name)>1 and name.startswith('.'):
            return True

    return False


def _compute_dir_contents(n, path, show_hidden=False):
    """Given a vfs node, returns an iterator for display info of all subs."""
    url_append = ""
    if show_hidden:
        url_append = "?hidden=1"

    if path != "/":
        yield('..', '../' + url_append, '')
    for sub in n:
        display = sub.name
        link = urllib.quote(sub.name)

        # link should be based on fully resolved type to avoid extra
        # HTTP redirect.
        if stat.S_ISDIR(sub.try_resolve().mode):
            link += "/"

        if not show_hidden and len(display)>1 and display.startswith('.'):
            continue

        size = None
        if stat.S_ISDIR(sub.mode):
            display += '/'
        elif stat.S_ISLNK(sub.mode):
            display += '@'
        else:
            size = sub.size()
            size = (opt.human_readable and format_filesize(size)) or size

        yield (display, link + url_append, size)


class BupRequestHandler(tornado.web.RequestHandler):
    def get(self, path):
        return self._process_request(path)

    def head(self, path):
        return self._process_request(path)
    
    @tornado.web.asynchronous
    def _process_request(self, path):
        path = urllib.unquote(path)
        print 'Handling request for %s' % path
        try:
            n = top.resolve(path)
        except vfs.NoSuchFile:
            self.send_error(404)
            return
        f = None
        if stat.S_ISDIR(n.mode):
            self._list_directory(path, n)
        else:
            self._get_file(path, n)

    def _list_directory(self, path, n):
        """Helper to produce a directory listing.

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent.
        """
        if not path.endswith('/') and len(path) > 0:
            print 'Redirecting from %s to %s' % (path, path + '/')
            return self.redirect(path + '/', permanent=True)

        try:
            show_hidden = int(self.request.arguments.get('hidden', [0])[-1])
        except ValueError as e:
            show_hidden = False

        self.render(
            'list-directory.html',
            path=path,
            breadcrumbs=_compute_breadcrumbs(path, show_hidden),
            files_hidden=_contains_hidden_files(n),
            hidden_shown=show_hidden,
            dir_contents=_compute_dir_contents(n, path, show_hidden))

    def _get_file(self, path, n):
        """Process a request on a file.

        Return value is either a file object, or None (indicating an error).
        In either case, the headers are sent.
        """
        ctype = self._guess_type(path)

        self.set_header("Last-Modified", self.date_time_string(n.mtime))
        self.set_header("Content-Type", ctype)
        size = n.size()
        self.set_header("Content-Length", str(size))
        assert(len(n.hash) == 20)
        self.set_header("Etag", n.hash.encode('hex'))

        if self.request.method != 'HEAD':
            self.flush()
            f = n.open()
            it = chunkyreader(f)
            def write_more(me):
                try:
                    blob = it.next()
                except StopIteration:
                    f.close()
                    self.finish()
                    return
                self.request.connection.stream.write(blob,
                                                     callback=lambda: me(me))
            write_more(write_more)
        else:
            self.finish()

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

    def date_time_string(self, t):
        return time.strftime('%a, %d %b %Y %H:%M:%S', time.gmtime(t))


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
            o.fatal('port must be an integer, not %r', port)
        address = InetAddress(host=host, port=port)

git.check_repo_or_die()
top = vfs.RefList(None)

settings = dict(
    debug = 1,
    template_path = resource_path('web'),
    static_path = resource_path('web/static')
)

# Disable buffering on stdout, for debug messages
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

application = tornado.web.Application([
    (r"(/.*)", BupRequestHandler),
], **settings)

http_server = HTTPServer(application)
io_loop_pending = IOLoop.instance()

if isinstance(address, InetAddress):
    http_server.listen(address.port, address.host)
    try:
        sock = http_server._socket # tornado < 2.0
    except AttributeError as e:
        sock = http_server._sockets.values()[0]
    print "Serving HTTP on %s:%d..." % sock.getsockname()
    if opt.browser:
        browser_addr = 'http://' + address[0] + ':' + str(address[1])
        io_loop_pending.add_callback(lambda : webbrowser.open(browser_addr))
elif isinstance(address, UnixAddress):
    unix_socket = bind_unix_socket(address.path)
    http_server.add_socket(unix_socket)
    print "Serving HTTP on filesystem socket %r" % address.path
else:
    log('error: unexpected address %r', address)
    sys.exit(1)

io_loop = io_loop_pending
io_loop.start()

if saved_errors:
    log('WARNING: %d errors encountered while saving.\n' % len(saved_errors))
    sys.exit(1)
