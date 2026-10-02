import hashlib
import http.server
import json
import os
import posixpath
import re
import socket
import subprocess
import threading
import time
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
EVENT_PATH_RE = re.compile(r'^/api/events/(\d+)$')
MAX_BODY = 256 * 1024

state_lock = threading.Lock()
# Bumped on every change. Pages wait on /api/state?since=<version>, so a change made on a
# phone shows on the wall right away instead of at the next poll.
state_changed = threading.Condition(state_lock)
state_version = 0
LONG_POLL_SECONDS = 25


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


def clean_event(raw):
    """Validates a client-sent countdown and keeps only the fields worth persisting."""
    if not isinstance(raw, dict):
        raise ValueError('expected {"title": ..., "date": "YYYY-MM-DD"}')
    title, date = raw.get('title'), raw.get('date')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('event title must be 1-200 characters')
    if not isinstance(date, str) or not DATE_RE.match(date):
        raise ValueError('event date must be YYYY-MM-DD')
    return {'title': title.strip(), 'date': date}


def clean_background(raw):
    if not isinstance(raw, dict) or raw.get('type') not in BACKGROUND_TYPES:
        raise ValueError('invalid background')
    return {'type': raw['type'], 'value': raw.get('value')}


def new_event_id(events):
    # Millisecond timestamps, like the ids the page used to create, but never reused.
    return max([int(time.time() * 1000)] + [e['id'] + 1 for e in events])


def find_event(state, event_id):
    for event in state['events']:
        if event['id'] == event_id:
            return event
    raise LookupError(event_id)


def add_event(state, body):
    state['events'].append({'id': new_event_id(state['events']), **clean_event(body)})


def edit_event(state, body, event_id):
    find_event(state, event_id).update(clean_event(body))


def delete_event(state, event_id):
    state['events'].remove(find_event(state, event_id))


def set_background(state, body):
    state['background'] = clean_background(body)


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
        path, _, query = self.path.partition('?')
        if path == '/api/state':
            return self.get_state(urllib.parse.parse_qs(query).get('since', [None])[0])
        super().do_GET()

    def get_state(self, since):
        """Replies with the saved state. With ?since=<version>, first waits (up to
        LONG_POLL_SECONDS) until the state is newer than that version."""
        with state_changed:
            if since is not None and since.lstrip('-').isdigit():
                state_changed.wait_for(lambda: state_version != int(since), timeout=LONG_POLL_SECONDS)
            state = {**load_state(), 'version': state_version}
        self.send_json(200, state)

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

    def log_request(self, code='-', size='-'):
        # Every open page keeps a request to /api/state waiting; keep those out of the journal.
        if self.path.split('?', 1)[0] == '/api/state' and str(code) == '200':
            return
        super().log_request(code, size)

    def do_POST(self):
        if self.path == '/update':
            self.update()
        elif self.path == '/kiosk/exit':
            self.exit_kiosk()
        elif self.path == '/kiosk/start':
            self.start_kiosk()
        elif self.path == '/system/reboot':
            self.reboot()
        elif self.path == '/api/events':
            self.change_state(add_event)
        else:
            self.send_error(404)

    def do_PUT(self):
        match = EVENT_PATH_RE.match(self.path)
        if match:
            self.change_state(lambda state, body: edit_event(state, body, int(match[1])))
        elif self.path == '/api/background':
            self.change_state(set_background)
        else:
            self.send_error(404)

    def do_DELETE(self):
        match = EVENT_PATH_RE.match(self.path)
        if not match:
            return self.send_error(404)
        self.change_state(lambda state, body: delete_event(state, int(match[1])))

    def change_state(self, change):
        """Applies one change to the saved state and replies with the result.

        Changes are applied to the current file rather than replacing it wholesale, so the wall
        and a phone editing at the same time can't overwrite each other's countdowns.
        """
        global state_version
        try:
            body = self.read_json()
            with state_changed:
                state = load_state()
                change(state, body)
                save_state(state)
                state_version += 1
                state_changed.notify_all()
                state = {**state, 'version': state_version}
        except LookupError:
            return self.send_json(404, {'error': 'no such countdown'})
        except ValueError as e:  # includes invalid JSON
            return self.send_json(400, {'error': str(e)})
        self.send_json(200, state)

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

    def start_kiosk(self):
        """Brings the kiosk back after "Exit to Desktop", e.g. from a phone."""
        # This service doesn't inherit the desktop session's environment; find its Wayland socket.
        runtime_dir = os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')
        sockets = sorted(f for f in os.listdir(runtime_dir) if re.fullmatch(r'wayland-\d+', f))
        if not sockets:
            return self.send_json(503, {'success': False, 'error': 'the desktop is not running'})
        env = dict(os.environ, XDG_RUNTIME_DIR=runtime_dir, WAYLAND_DISPLAY=sockets[0])
        # The launcher clears the pause file and exits early if the kiosk is already running.
        subprocess.Popen([os.path.join(ROOT, 'start_dashboard.sh')], env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.send_json(200, {'success': True})

    def reboot(self):
        # logind lets the logged-in desktop user reboot without sudo. systemctl returns once the
        # reboot is queued, so there's still time to reply with whether it was accepted.
        try:
            result = subprocess.run(['systemctl', 'reboot', '--no-ask-password'],
                                    capture_output=True, text=True, timeout=15)
        except Exception as e:
            return self.send_json(500, {'success': False, 'error': str(e)})
        self.send_json(200, {'success': result.returncode == 0, 'error': result.stderr.strip()})


class DualStackServer(http.server.ThreadingHTTPServer):
    # raspberrypi.local resolves to IPv6 as well; listening on both avoids a stall
    # on clients that try IPv6 first.
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


if __name__ == '__main__':
    with DualStackServer(('::', PORT), DashboardRequestHandler) as httpd:
        print(f'Serving dashboard at http://localhost:{PORT}')
        httpd.serve_forever()
