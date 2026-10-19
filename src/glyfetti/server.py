"""Loopback-only editor. Assets are rendered locally; no external services."""
import base64
import binascii
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
import threading
import webbrowser
import zipfile

from .engine import build, FONTS_DIR
from .validation import DATA_DIR, validate_style

WEB_DIR = Path(__file__).parent / 'web'
MAX_BODY = 256 * 1024
MAX_REFERENCE_BODY = 6 * 1024 * 1024


class LocalHTTPServer(ThreadingHTTPServer):
    # SO_REUSEADDR on Windows allows two live servers to bind the same port,
    # leaving the older renderer answering requests after a restart.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def catalog():
    presets = []
    for path in sorted((DATA_DIR / 'presets').glob('*.json')):
        style = json.loads(path.read_text('utf-8'))
        style.pop('$schema', None)
        style['font'] = str((FONTS_DIR / Path(style['font']).name).resolve())
        presets.append(style)
    return {'presets': sorted(presets, key=lambda p: p.get('order', 999)),
            'fonts': [str(p.resolve()) for p in sorted(FONTS_DIR.glob('*.ttf'))]}


def render_style(style, preview=False, mode='atlas', with_report=False):
    if mode not in ('atlas', 'title'):
        raise ValueError('output mode must be atlas or title')
    style = copy.deepcopy(validate_style(style))
    original = copy.deepcopy(style)
    if preview:
        style['supersample'] = 1
        style['chars'] = ''.join(style.get('preview', ['Level complete!', 'Score: 2 560'])) or ' '
    with tempfile.TemporaryDirectory(prefix='glyfetti-') as folder:
        root = Path(folder)
        source = root / 'style.json'
        source.write_text(json.dumps(style, ensure_ascii=False), 'utf-8')
        if mode == 'title':
            from .title import build_title
            result = build_title(source, root / 'out' / f"{style['name']}_title.png")
            if not preview:
                data = result['out'].read_bytes()
                report = {key: result[key] for key in ('size', 'glyphs', 'kernings', 'skipped', 'lines')}
                return (data, report) if with_report else data
            image = result['preview'].read_bytes()
            return {'mode': 'title', 'image': 'data:image/png;base64,' + base64.b64encode(image).decode(),
                    **{key: result[key] for key in ('size', 'glyphs', 'kernings', 'skipped', 'lines')}}
        result = build(source, root / 'out', preview_only=preview)
        if preview:
            image = (root / 'out' / f"{result['name']}_preview.png").read_bytes()
            return {'image': 'data:image/png;base64,' + base64.b64encode(image).decode(),
                    'glyphs': result['glyphs'], 'atlas': result['atlas'], 'skipped': result['skipped'],
                    'kernings': result['kernings'], 'packing': result['packing'], 'occupancy': result['occupancy']}
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as target:
            for path in sorted((root / 'out').iterdir()):
                target.write(path, path.name)
            target.writestr(f"{style['name']}.style.json", json.dumps(original, ensure_ascii=False, indent=2) + '\n')
            target.writestr('build-report.json', json.dumps({key: result[key] for key in ('glyphs', 'atlas', 'skipped', 'kernings', 'packing', 'occupancy')}, ensure_ascii=False, indent=2) + '\n')
        data = archive.getvalue()
        report = {key: result[key] for key in ('glyphs', 'atlas', 'skipped', 'kernings', 'packing', 'occupancy')}
        return (data, report) if with_report else data


def make_server(port=8765):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data, content_type='application/json'):
            if isinstance(data, dict):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def allowed(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {'error': 'Use the loopback URL printed by glyfetti serve.'})
            if self.path == '/api/catalog':
                return self.respond(200, {**catalog(), 'token': token})
            files = {'/': ('index.html', 'text/html; charset=utf-8'),
                     '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                     '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if self.path not in files:
                return self.respond(404, {'error': 'Not found'})
            filename, mime = files[self.path]
            self.respond(200, (WEB_DIR / filename).read_bytes(), mime)

        def do_POST(self):
            if not self.allowed() or not secrets.compare_digest(self.headers.get('X-Glyfetti-Token', ''), token):
                return self.respond(403, {'error': 'Invalid editor session. Reload the page.'})
            if self.path not in ('/api/preview', '/api/export', '/api/title-preview', '/api/title-export', '/api/validate', '/api/expand', '/api/reference', '/api/inspect'):
                return self.respond(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                limit = MAX_REFERENCE_BODY if self.path == '/api/reference' else MAX_BODY
                if not 0 < length <= limit:
                    return self.respond(413, {'error': 'Request is too large.'})
                style = json.loads(self.rfile.read(length))
                if self.path == '/api/reference':
                    from .reference import MAX_REFERENCE_BYTES, analyze_reference
                    if not isinstance(style, dict):
                        raise ValueError('Expected reference image and base style JSON.')
                    encoded = style.get('image', '')
                    if not isinstance(encoded, str) or not encoded.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,')):
                        raise ValueError('Reference must be a PNG/JPEG data URL.')
                    payload = encoded.partition(',')[2]
                    if len(payload) > (MAX_REFERENCE_BYTES + 2) // 3 * 4:
                        raise ValueError('Reference image exceeds 4 MiB.')
                    try:
                        image = base64.b64decode(payload, validate=True)
                    except binascii.Error as error:
                        raise ValueError('Invalid reference image encoding.') from error
                    return self.respond(200, analyze_reference(image, style.get('style')))
                if self.path == '/api/inspect':
                    from .quality import inspect_style
                    return self.respond(200, inspect_style(style, base=Path.cwd(), include_atlas=True))
                if self.path == '/api/expand':
                    return self.respond(200, {'style': validate_style(style)})
                if self.path == '/api/validate':
                    validate_style(style)
                    return self.respond(200, {'valid': True})
                title = self.path.startswith('/api/title-')
                result = render_style(style, preview=self.path.endswith('preview'), mode='title' if title else 'atlas')
                mime = ('image/png' if title else 'application/zip') if isinstance(result, bytes) else 'application/json'
                self.respond(200, result, mime)
            except (ValueError, OSError, KeyError, TypeError) as error:
                self.respond(400, {'error': str(error)})
            except Exception:
                self.respond(500, {'error': 'Rendering failed. Check the font and style parameters.'})

    return LocalHTTPServer(('127.0.0.1', port), Handler)


def serve(port=8765, open_browser=True):
    with make_server(port) as server:
        url = f'http://127.0.0.1:{server.server_port}'
        print(f'Glyfetti editor: {url}\nPress Ctrl+C to stop.', flush=True)
        if open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print('\nEditor stopped.')
