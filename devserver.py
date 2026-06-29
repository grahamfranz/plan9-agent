#!/usr/bin/env python3
# Dev bridge between the Mac and the 9front VM.
#   GET  /<file>   -> serve a script from this directory (VM pulls scripts)
#   POST /up       -> save the request body to _up.txt (VM sends output back)
#   POST /claude   -> proxy an OpenAI-style chat request to the Anthropic API.
#                     The VM speaks plain HTTP to us; we do the HTTPS + auth +
#                     translation, and return an OpenAI-shaped reply so the
#                     agent's parser is unchanged.
import http.server, os, json, urllib.request, urllib.error

DIR = os.path.dirname(os.path.abspath(__file__))
KEYFILE = os.path.expanduser('~/.anthropic_key')

def claude(req):
    key = open(KEYFILE).read().strip()
    system = ''
    conv = []
    for m in req.get('messages', []):
        if m.get('role') == 'system':
            system = m.get('content', '')
        else:
            conv.append({'role': m['role'], 'content': m.get('content', '')})
    body = {
        'model': req.get('model', 'claude-haiku-4-5-20251001'),
        'max_tokens': 1024,
        'system': system,
        'messages': conv,
    }
    r = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=json.dumps(body).encode(),
        headers={
            'content-type': 'application/json',
            'x-api-key': key,
            'anthropic-version': '2023-06-01',
        },
    )
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        out = json.loads(resp.read())
        text = ''.join(b.get('text', '') for b in out.get('content', []) if b.get('type') == 'text')
    except urllib.error.HTTPError as e:
        text = 'PROXY ERROR: ' + e.read().decode(errors='replace')
    except Exception as e:
        text = 'PROXY ERROR: ' + str(e)
    # OpenAI-shaped reply, so agent.rc's existing parser works unchanged
    return {'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def do_POST(self):
        n = int(self.headers.get('Content-Length', '0'))
        data = self.rfile.read(n)
        if self.path.startswith('/claude'):
            try:
                out = claude(json.loads(data))
            except Exception as e:
                out = {'choices': [{'message': {'content': 'PROXY ERROR: ' + str(e)}, 'finish_reason': 'stop'}]}
            payload = json.dumps(out, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(payload)
        else:  # /up
            with open(os.path.join(DIR, '_up.txt'), 'wb') as f:
                f.write(data)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok\n')

    def log_message(self, *a):
        pass

H.protocol_version = 'HTTP/1.0'
http.server.HTTPServer(('0.0.0.0', 8000), H).serve_forever()
