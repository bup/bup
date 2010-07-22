#!/usr/bin/env python
import sys, stat, cgi, shutil, urllib, mimetypes, posixpath, time
import tornado.httpserver
import tornado.ioloop
import tornado.web
from bup import options, git, vfs
from bup.helpers import *

handle_ctrl_c()

class BupRequestHandler(tornado.web.RequestHandler):
    def get(self, path):
        return self._process_request(path)

    def head(self, path):
        return self._process_request(path)

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

        self.set_header("Content-Type", "text/html")

        displaypath = cgi.escape(path)
        self.write("""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">
<html>
  <head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <title>Directory listing for %(displaypath)s</title>
    <style type="text/css">
      body, table { font-family: sans-serif }
      #breadcrumb { margin: 10px 0; }
      .dir-name { text-align: left }
      .dir-size { text-align: right }
    </style>
  </head>
  <body>
    <div id="breadcrumb">
""" % { 'displaypath': displaypath })
        if path == "/":
            self.write("""<strong>[root]</strong>""")
        else:
            self.write("""<a href="/">[root]</a> """)
            path_parts = path.split("/")
            path_parts_cleaned = path_parts[1:-1]
            for index, value in enumerate(path_parts_cleaned[0:-1]):
                self.write("""/ <a href="/%(path)s/">%(element)s</a> """ % { 'path' : "/".join(path_parts_cleaned[0:(index + 1)]) , 'element' : value})
            self.write("""/ <strong>%s</strong>""" % path_parts_cleaned[-1])
        self.write("""
    </div>
    <table>
      <tr>
        <th class="dir-name">Name</th>
        <th class="dir-size">Size</th>
      </tr>
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
            self.write("""      <tr>
        <td class="dir-name"><a href="%s">%s</a></td>
        <td class="dir-size">%s</td>
      </tr>""" % (urllib.quote(linkname), cgi.escape(displayname), size))
        self.write("""
    </table>
  </body>
</html>""")

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

        if self.request.method != 'HEAD':
            f = n.open()
            for blob in chunkyreader(f):
                self.write(blob)
            f.close()

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

(pwd,junk) = os.path.split(sys.argv[0])

settings = dict(
    debug = 1,
)

# Disable buffering on stdout, for debug messages
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

application = tornado.web.Application([
    (r"(/.*)", BupRequestHandler),
], **settings)

if __name__ == "__main__":
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(address[1], address=address[0])

    print "Serving HTTP on %s:%d..." % http_server._socket.getsockname()
    loop = tornado.ioloop.IOLoop.instance()
    loop.start()

