#!/usr/bin/env python3
# Dev bridge between the Mac and the 9front VM.
#   GET  /<file>  -> serve a script from this directory (VM pulls scripts)
#   POST /up      -> save the request body to _up.txt (VM sends output back)
import http.server, os

DIR = os.path.dirname(os.path.abspath(__file__))

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        data = self.rfile.read(n)
        with open(os.path.join(DIR, '_up.txt'), 'wb') as f:
            f.write(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok\n')

    def log_message(self, *a):
        pass

H.protocol_version = 'HTTP/1.0'
http.server.HTTPServer(('0.0.0.0', 8000), H).serve_forever()
