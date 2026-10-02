import hashlib
import http.server
import json
import os
import posixpath
import re
import subprocess
import threading
import urllib.parse

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, 'data', 'state.json')

# Shared with start_dashboard.sh: the launcher stops relaunching Chromium while
# this file exists, and the kiosk Chromium is the one using this profile dir.
KIOSK_PAUSE_FILE = os.path.expanduser('~/.cache/home-dashboard/kiosk-paused')
KIOSK_PROFILE_DIR = os.path.expanduser('~/.local/share/home-dashboard/chromium')

# Only these are served; everything else in the repo (.git, data/, server.py) stays private.
STATIC_FILES = {'/dashboard.html'}
STATIC_PREFIXES = ('/assets/',)

BACKGROUND_TYPES = {'color', 'gradient', 'pattern', 'image'}
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MAX_BODY = 256 * 1024

state_lock = threading.Lock()


def file_hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_state():
    try:
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'events': [], 'background': None}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def clean_state(raw):
    """Validates a client-sent state and keeps only the fields worth persisting."""
    if not isinstance(raw, dict) or not isinstance(raw.get('events'), list):
        raise ValueError('expected {"events": [...], "background": ...}')
    events = []
    for e in raw['events']:
        if not isinstance(e, dict):
            raise ValueError('each event must be an object')
        title, date, event_id = e.get('title'), e.get('date'), e.get('id')
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError('event title must be 1-200 characters')
        if not isinstance(date, str) or not DATE_RE.match(date):
            raise ValueError('event date must be YYYY-MM-DD')
        if not isinstance(event_id, (int, float)):
            raise ValueError('event id must be a number')
        events.append({'id': event_id, 'title': title, 'date': date})
    background = raw.get('background')
    if background is not None:
        if not isinstance(background, dict) or background.get('type') not in BACKGROUND_TYPES:
            raise ValueError('invalid background')
        background = {'type': background['type'], 'value': background.get('value')}
    return {'events': events, 'background': background}


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        # Always revalidate, so a reload after "Update Dashboard" picks up new files.
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get('Content-Length') or 0)
        if length > MAX_BODY:
            raise ValueError('request too large')
        return json.loads(self.rfile.read(length) or b'null')

    def do_GET(self):
        if self.path.split('?', 1)[0] == '/api/state':
            with state_lock:
                return self.send_json(200, load_state())
        super().do_GET()

    def send_head(self):
        # Shared by GET and HEAD for static files. Normalize first so
        # "/assets/../.git/config" can't slip past the allowlist.
        path = posixpath.normpath(urllib.parse.unquote(self.path.split('?', 1)[0].split('#', 1)[0]))
        if path == '/':
            path = '/dashboard.html'
        elif path not in STATIC_FILES and not path.startswith(STATIC_PREFIXES):
            self.send_error(404)
            return None
        self.path = path
        return super().send_head()

    def do_PUT(self):
        if self.path != '/api/state':
            return self.send_error(404)
        try:
            state = clean_state(self.read_json())
        except ValueError as e:  # includes json.JSONDecodeError
            return self.send_json(400, {'success': False, 'error': str(e)})
        with state_lock:
            save_state(state)
        self.send_json(200, {'success': True})

    def do_POST(self):
        if self.path == '/update':
            self.update()
        elif self.path == '/kiosk/exit':
            self.exit_kiosk()
        else:
            self.send_error(404)

    def update(self):
        server_file = os.path.abspath(__file__)
        before = file_hash(server_file)
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND='ssh -o BatchMode=yes')
        try:
            result = subprocess.run(['git', 'pull', '--ff-only'], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return self.send_json(200, {'success': False, 'error': 'git pull timed out after 60s'})
        except Exception as e:
            return self.send_json(500, {'success': False, 'error': str(e)})

        # If server.py itself changed, exit after replying; systemd restarts us on the new code.
        restart = result.returncode == 0 and file_hash(server_file) != before
        self.send_json(200, {
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr,
            'restart': restart,
        })
        if restart:
            threading.Timer(0.5, os._exit, args=(0,)).start()

    def exit_kiosk(self):
        os.makedirs(os.path.dirname(KIOSK_PAUSE_FILE), exist_ok=True)
        open(KIOSK_PAUSE_FILE, 'w').close()
        self.send_json(200, {'success': True})
        subprocess.run(['pkill', '-TERM', '-f', '--', '--user-data-dir=' + KIOSK_PROFILE_DIR])


if __name__ == '__main__':
    with http.server.ThreadingHTTPServer(('', PORT), DashboardRequestHandler) as httpd:
        print(f'Serving dashboard at http://localhost:{PORT}')
        httpd.serve_forever()
