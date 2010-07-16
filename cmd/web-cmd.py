#!/usr/bin/env python
import sys, stat, cgi, shutil, urllib, mimetypes, posixpath
import BaseHTTPServer
from bup import options, git, vfs
from bup.helpers import *
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

handle_ctrl_c()

class BupHTTPServer(BaseHTTPServer.HTTPServer):
    def handle_error(self, request, client_address):
        # If we get a KeyboardInterrupt error than just reraise it
        # so that we cause the server to exit.
        if sys.exc_info()[0] == KeyboardInterrupt:
            raise

class BupRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    server_version = 'BupHTTP/%s' % version_tag()
    protocol_version = 'HTTP/1.1'
    def do_GET(self):
        self._process_request()

    def do_HEAD(self):
        self._process_request()

    def _process_request(self):
        """Common code for GET and HEAD commands.

        This sends the response code and MIME headers along with the content
        of the response.
        """
        path = urllib.unquote(self.path)
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
        if not path.endswith('/'):
            # redirect browser - doing basically what apache does
            self.send_response(301)
            self.send_header("Location", path + "/")
            self.send_header("Content-Length", 0)
            self.end_headers()
            return

        # Note that it is necessary to buffer the output into a StringIO here
        # so that we can compute the content length before we send the
        # content.  The only other option would be to do chunked encoding, or
        # not support content length.
        f = StringIO()
        displaypath = cgi.escape(path)
        f.write("""
<HTML>
  <HEAD>
    <TITLE>Directory listing for %(displaypath)s</TITLE>
    <STYLE>
      BODY, TABLE { font-family: sans-serif }
      #breadcrumb { margin: 10px 0; }
      .dir-name { text-align: left }
      .dir-size { text-align: right }
    </STYLE>
  </HEAD>
  <BODY>
    <DIV id="breadcrumb">
""" % { 'displaypath': displaypath })
        if self.path == "/":
            f.write("""<STRONG>[root]</STRONG>""")
        else:
            f.write("""<A href="/">[root]</A> """)
            path_parts = self.path.split("/")
            path_parts_cleaned = path_parts[1:len(path_parts)-1]
            for index, value in enumerate(path_parts_cleaned[0:len(path_parts_cleaned)-1]):
                f.write("""/ <A href="/%(path)s/">%(element)s</A> """ % { 'path' : "/".join(path_parts_cleaned[0:(index + 1)]) , 'element' : value})
            f.write("""/ <STRONG>%s</STRONG>""" % path_parts_cleaned[len(path_parts_cleaned)-1])
        f.write("""
    </DIV>
    <TABLE>
      <TR>
        <TH class="dir-name">Name</TH>
        <TH class="dir-size">Size<TH>
      </TR>
""")
        for sub in n:
            displayname = linkname = sub.name
            # Append / for directories or @ for symbolic links
            size = str(sub.size())
            if stat.S_ISDIR(sub.mode):
                displayname = sub.name + "/"
                linkname = sub.name + "/"
                size = '&nbsp;'
            if stat.S_ISLNK(sub.mode):
                displayname = sub.name + "@"
                # Note: a link to a directory displays with @ and links with /
                size = '&nbsp;'
            f.write("""      <TR>
        <TD class="dir-name"><A href="%s">%s</A></TD>
        <TD class="dir-size">%s</TD>
      </TR>""" % (urllib.quote(linkname), cgi.escape(displayname), size))
        f.write("""
    </TABLE>
  </BODY>
</HTML>""")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        self._send_content(f)
        f.close()

    def _get_file(self, path, n):
        """Process a request on a file.

        Return value is either a file object, or None (indicating an error).
        In either case, the headers are sent.
        """
        ctype = self._guess_type(path)
        f = n.open()
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(n.size()))
        self.send_header("Last-Modified", self.date_time_string(n.mtime))
        self.end_headers()
        self._send_content(f)
        f.close()

    def _send_content(self, f):
        """Send the content file as the response if necessary."""
        if self.command != 'HEAD':
            for blob in chunkyreader(f):
                self.wfile.write(blob)

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


optspec = """
bup web [[hostname]:port]
--
"""
o = options.Options('bup web', optspec)
(opt, flags, extra) = o.parse(sys.argv[1:])

if len(extra) > 1:
    o.fatal("at most one argument expected")

address = ('127.0.0.1', 8080)
if len(extra) > 0:
    addressl = extra[0].split(':', 1)
    addressl[1] = int(addressl[1])
    address = tuple(addressl)

git.check_repo_or_die()
top = vfs.RefList(None)

try:
    httpd = BupHTTPServer(address, BupRequestHandler)
except socket.error, e:
    log('socket%r: %s\n' % (address, e.args[1]))
    sys.exit(1)

sa = httpd.socket.getsockname()
log("Serving HTTP on %s:%d...\n" % sa)
httpd.serve_forever()
