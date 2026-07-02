#!/usr/bin/env python3
# Dev bridge between the Mac (or any trusted host) and the 9front VM.
#   GET  /<file>   -> serve a script from this directory (VM pulls scripts)
#   POST /up       -> save the request body to _up.txt (VM sends output back)
#   POST /claude   -> proxy an OpenAI-style chat request to an LLM provider,
#                     adding TLS + auth, and return an OpenAI-shaped reply so
#                     agent.rc's parser is unchanged. (Route name is historical.)
#
# Provider-agnostic via env vars; the defaults reproduce the original Anthropic
# setup, so existing use is unchanged:
#   PROVIDER  anthropic | openai   ('openai' = ANY OpenAI-compatible endpoint:
#                                    OpenAI, OpenRouter, Together, Groq, Ollama, ...)
#   UPSTREAM  full endpoint URL     (default depends on PROVIDER)
#   KEYFILE   file holding the API key (default depends on PROVIDER; may be empty
#             or /dev/null for keyless local servers like Ollama)
#   BIND      interface to listen on (default 127.0.0.1 -- loopback only, so the
#             proxy is not an open relay on your LAN. Set 0.0.0.0 only if the VM
#             cannot otherwise reach it.)
#   PORT      port (default 8000)
# e.g. a local Ollama, no crypto at all:
#   PROVIDER=openai UPSTREAM=http://localhost:11434/v1/chat/completions \
#     KEYFILE=/dev/null python3 devserver.py
import http.server, os, json, urllib.request, urllib.error

DIR = os.path.dirname(os.path.abspath(__file__))
PROVIDER = os.environ.get('PROVIDER', 'anthropic')
BIND = os.environ.get('BIND', '127.0.0.1')
PORT = int(os.environ.get('PORT', '8000'))
_DEFAULTS = {
    'anthropic': ('https://api.anthropic.com/v1/messages', '~/.anthropic_key'),
    'openai':    ('https://api.openai.com/v1/chat/completions', '~/.openai_key'),
}
_url, _key = _DEFAULTS.get(PROVIDER, _DEFAULTS['openai'])
UPSTREAM = os.environ.get('UPSTREAM', _url)
KEYFILE = os.path.expanduser(os.environ.get('KEYFILE', _key))


def readkey():
    try:
        return open(KEYFILE).read().strip()
    except OSError:
        return ''


def complete(req):
    key = readkey()
    if PROVIDER == 'anthropic':
        # translate OpenAI-shaped request -> Anthropic, then reply -> text
        system, conv = '', []
        for m in req.get('messages', []):
            if m.get('role') == 'system':
                system = m.get('content', '')
            else:
                conv.append({'role': m['role'], 'content': m.get('content', '')})
        body = {
            'model': req.get('model', 'claude-haiku-4-5-20251001'),
            'max_tokens': req.get('max_tokens', 4096),
            'system': system,
            'messages': conv,
        }
        headers = {'content-type': 'application/json', 'x-api-key': key,
                   'anthropic-version': '2023-06-01'}
        r = urllib.request.Request(UPSTREAM, data=json.dumps(body).encode(), headers=headers)
        out = json.loads(urllib.request.urlopen(r, timeout=60).read())
        return ''.join(b.get('text', '') for b in out.get('content', []) if b.get('type') == 'text')
    # OpenAI-compatible: pass the request straight through, just add auth + TLS
    headers = {'content-type': 'application/json'}
    if key:
        headers['authorization'] = 'Bearer ' + key
    r = urllib.request.Request(UPSTREAM, data=json.dumps(req).encode(), headers=headers)
    out = json.loads(urllib.request.urlopen(r, timeout=60).read())
    return out['choices'][0]['message']['content']


def claude(req):
    try:
        text = complete(req)
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
print('devserver: %s -> %s  (listening on %s:%d)' % (PROVIDER, UPSTREAM, BIND, PORT))
http.server.HTTPServer((BIND, PORT), H).serve_forever()
