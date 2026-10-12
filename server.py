import calendar
import datetime as dt
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

import calendar_feed

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
CALENDAR_PATH_RE = re.compile(r'^/api/settings/calendars/(\d+)$')
TASK_PATH_RE = re.compile(r'^/api/tasks/(\d+)$')
TASK_DONE_PATH_RE = re.compile(r'^/api/tasks/(\d+)/done$')
PERSON_PATH_RE = re.compile(r'^/api/settings/people/(\d+)$')
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
REPEAT_UNITS = {'day', 'week', 'month', 'year'}
# A routine's next due date counts from the day it was done ("every month after the filter was
# changed") or follows a fixed schedule ("trash night every Tuesday", "registration every October").
REPEAT_FROM = {'done', 'schedule'}
HISTORY_LIMIT = 20       # completion dates kept per routine ("when did we last change the filter?")
DONE_KEEP_DAYS = 30      # checked-off one-off to-dos stay in "Done lately" this long
MAX_PEOPLE = 12
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
        return {'events': [], 'tasks': [], 'background': None, 'settings': default_settings()}


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


def new_id(items):
    # Millisecond timestamps, like the ids the page used to create, but never reused.
    return max([int(time.time() * 1000)] + [item['id'] + 1 for item in items])


def find_event(state, event_id):
    for event in state['events']:
        if event['id'] == event_id:
            return event
    raise LookupError('no such countdown')


def add_event(state, body):
    state['events'].append({'id': new_id(state['events']), **clean_event(body)})


def edit_event(state, body, event_id):
    find_event(state, event_id).update(clean_event(body))


def delete_event(state, event_id):
    state['events'].remove(find_event(state, event_id))


def set_background(state, body):
    state['background'] = clean_background(body)


def is_over(event, today):
    """A countdown whose day has passed. One added with a date before the day before it was added
    ("We met", counting the days since) is a count-up and stays. Ids are creation times in ms."""
    date = dt.date.fromisoformat(event['date'])
    added = dt.date.fromtimestamp(event['id'] / 1000)
    is_count_up = date < added - dt.timedelta(days=1)
    return date < today and not is_count_up


def done_long_ago(task, today):
    return bool(task.get('done')) and dt.date.fromisoformat(task['done']) < today - dt.timedelta(days=DONE_KEEP_DAYS)


def remove_finished():
    """Runs every few minutes: deletes countdowns the day after their date, and one-off to-dos a
    month after they were checked off."""
    global state_version
    while True:
        with state_changed:
            state = load_state()
            today = dt.date.today()
            gone = [e['title'] for e in state['events'] if is_over(e, today)]
            old = [t['title'] for t in state.get('tasks', []) if done_long_ago(t, today)]
            if gone or old:
                state['events'] = [e for e in state['events'] if not is_over(e, today)]
                state['tasks'] = [t for t in state.get('tasks', []) if not done_long_ago(t, today)]
                save_state(state)
                state_version += 1
                state_changed.notify_all()
                if gone:
                    print('Removed finished countdowns:', ', '.join(gone), flush=True)
                if old:
                    print('Removed to-dos done over a month ago:', ', '.join(old), flush=True)
        time.sleep(5 * 60)


# --- To-dos: one-offs (with a due date or "anytime") and routines that repeat ---

def clean_date(value, name):
    """None, or a real YYYY-MM-DD date."""
    if value is None:
        return None
    if not isinstance(value, str) or not DATE_RE.match(value):
        raise ValueError(f'{name} must be YYYY-MM-DD')
    dt.date.fromisoformat(value)  # rejects 2026-02-30
    return value


def is_id(value):
    return isinstance(value, int) and not isinstance(value, bool)


def clean_repeat(raw):
    if raw is None:
        return None
    every = raw.get('every') if isinstance(raw, dict) else None
    if not is_id(every) or not 1 <= every <= 365 or raw.get('unit') not in REPEAT_UNITS \
            or raw.get('from') not in REPEAT_FROM:
        raise ValueError('repeat must be {"every": 1-365, "unit": "day|week|month|year", "from": "done|schedule"}')
    return {'every': every, 'unit': raw['unit'], 'from': raw['from']}


def clean_task(raw, state):
    """Validates a client-sent to-do and keeps only the fields worth persisting."""
    if not isinstance(raw, dict):
        raise ValueError('expected {"title": ..., "due": "YYYY-MM-DD" or null, ...}')
    title, notes, who = raw.get('title'), raw.get('notes') or '', raw.get('who') or []
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('to-do title must be 1-200 characters')
    if not isinstance(notes, str) or len(notes) > 2000:
        raise ValueError('notes must be at most 2000 characters')
    if not isinstance(who, list) or not all(is_id(p) for p in who):
        raise ValueError('who must be a list of person ids')
    people = {p['id'] for p in settings_of(state).get('people', [])}
    repeat = clean_repeat(raw.get('repeat'))
    due = clean_date(raw.get('due'), 'due')
    if repeat and not due:
        raise ValueError('a repeating to-do needs a due date')
    history = raw.get('history') or []
    if not isinstance(history, list):
        raise ValueError('history must be a list of dates')
    return {
        'title': title.strip(),
        'notes': notes.strip(),
        'who': [p for p in dict.fromkeys(who) if p in people],  # anyone removed meanwhile is dropped
        'due': due,
        'repeat': repeat,
        'snoozedUntil': clean_date(raw.get('snoozedUntil'), 'snoozedUntil'),
        # A routine is never "done": checking it off moves it to its next due date instead
        'done': None if repeat else clean_date(raw.get('done'), 'done'),
        'history': [clean_date(d, 'history') for d in history][:HISTORY_LIMIT] if repeat else [],
    }


def find_task(state, task_id):
    for task in state.setdefault('tasks', []):
        if task['id'] == task_id:
            return task
    raise LookupError('no such to-do')


def add_task(state, body):
    tasks = state.setdefault('tasks', [])
    tasks.append({'id': new_id(tasks), **clean_task(body, state)})


def edit_task(state, body, task_id):
    find_task(state, task_id).update(clean_task(body, state))


def delete_task(state, task_id):
    state['tasks'].remove(find_task(state, task_id))


def add_interval(date, every, unit):
    """date plus every days/weeks/months/years; Jan 31 plus a month is Feb 28 (or 29)."""
    if unit in ('day', 'week'):
        return date + dt.timedelta(days=every * (7 if unit == 'week' else 1))
    months = date.month - 1 + every * (12 if unit == 'year' else 1)
    year, month = date.year + months // 12, months % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


def next_due(task, today):
    repeat = task['repeat']
    if repeat['from'] == 'done':
        return add_interval(today, repeat['every'], repeat['unit'])
    # On a schedule: the first date in the series after today, so a late or early check-off
    # doesn't shift it, and missed ones are skipped rather than piling up
    due, steps = dt.date.fromisoformat(task['due']), 1
    while (following := add_interval(due, repeat['every'] * steps, repeat['unit'])) <= today:
        steps += 1
    return following


def complete_task(state, task_id):
    """Checks a to-do off. A one-off is marked done; a routine gets its next due date."""
    task, today = find_task(state, task_id), dt.date.today()
    task['snoozedUntil'] = None
    if not task.get('repeat'):
        task['done'] = today.isoformat()
        return
    task['history'] = [today.isoformat(), *task.get('history', [])][:HISTORY_LIMIT]
    task['due'] = next_due(task, today).isoformat()


# --- People: who a to-do is for, each with a color on the wall ---

def clean_person(raw, state, person_id=None):
    name, color = (raw or {}).get('name'), (raw or {}).get('color')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 30:
        raise ValueError('Enter a name of up to 30 characters.')
    if not isinstance(color, str) or not COLOR_RE.match(color):
        raise ValueError('color must be #RRGGBB')
    for other in settings_of(state).get('people', []):
        if other['id'] != person_id and other['name'].lower() == name.strip().lower():
            raise ValueError(f"{other['name']} is already on the list.")
    return {'name': name.strip(), 'color': color}


def find_person(state, person_id):
    for person in settings_of(state).get('people', []):
        if person['id'] == person_id:
            return person
    raise LookupError('no such person')


def add_person(state, body):
    people = settings_of(state).setdefault('people', [])
    if len(people) >= MAX_PEOPLE:
        raise ValueError(f'Up to {MAX_PEOPLE} people.')
    people.append({'id': max([0] + [p['id'] for p in people]) + 1, **clean_person(body, state)})


def edit_person(state, body, person_id):
    find_person(state, person_id).update(clean_person(body, state, person_id))


def remove_person(state, person_id):
    settings_of(state)['people'].remove(find_person(state, person_id))
    for task in state.get('tasks', []):  # their to-dos stay, for anyone
        task['who'] = [p for p in task.get('who', []) if p != person_id]


def set_show_todos(state, body):
    show = (body or {}).get('show')
    if not isinstance(show, bool):
        raise ValueError('expected {"show": true or false}')
    settings_of(state)['showTodos'] = show


# --- Household settings: where the weather is for, and which calendars to show ---

def default_settings():
    return {'location': None, 'calendars': [], 'appsScriptUrl': None, 'showTodos': False, 'people': []}


def settings_of(state):
    return state.setdefault('settings', default_settings())


def geocode_zip(zip_code):
    """{'zip', 'name', 'lat', 'lon'} for a US ZIP code. The weather comes from the US National
    Weather Service, so the location is US-only too."""
    zip_code = str(zip_code or '').strip()
    if not re.fullmatch(r'\d{5}', zip_code):
        raise ValueError('Enter a 5-digit US ZIP code.')
    try:
        data = json.loads(calendar_feed.fetch(f'https://api.zippopotam.us/us/{zip_code}', timeout=10))
    except calendar_feed.CalendarError:
        raise ValueError(f"Couldn't find ZIP code {zip_code}.")
    place = data['places'][0]
    return {'zip': zip_code, 'name': f"{place['place name']}, {place['state abbreviation']}",
            'lat': round(float(place['latitude']), 4), 'lon': round(float(place['longitude']), 4)}


def checked_calendar(body):
    """A calendar entry from a client request, once its link is confirmed to be readable."""
    url = calendar_feed.normalize_url(str((body or {}).get('url') or ''))
    label = str((body or {}).get('label') or '').strip()[:40]
    try:
        calendar_feed.check_ical_url(url)
    except calendar_feed.CalendarError as e:
        raise ValueError(f"Couldn't use that link: {e}.")
    return {'url': url, 'label': label}


def checked_apps_script(body):
    url = str((body or {}).get('url') or '').strip()
    if url:
        try:
            calendar_feed.apps_script_events(url, calendar_feed.three_days())
        except calendar_feed.CalendarError as e:
            raise ValueError(f"Couldn't use that link: {e}.")
    return url or None


def add_calendar(state, calendar):
    calendars = settings_of(state)['calendars']
    if any(c['url'] == calendar['url'] for c in calendars):
        raise ValueError('That calendar is already added.')
    calendars.append({'id': max([0] + [c['id'] for c in calendars]) + 1, **calendar})


def remove_calendar(state, calendar_id):
    calendars = settings_of(state)['calendars']
    match = [c for c in calendars if c['id'] == calendar_id]
    if not match:
        raise LookupError('no such calendar')
    calendars.remove(match[0])


def lan_addresses():
    """How phones on the network can reach this Pi, for the setup screen."""
    host = socket.gethostname().lower()
    urls = [f'http://{host}.local:{PORT}']
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1', 9))  # picks the outgoing interface; nothing is sent
            urls.append(f'http://{s.getsockname()[0]}:{PORT}')
    except OSError:
        pass
    return urls


class DashboardRequestHandler(http.server.SimpleHTTPRequestHandler):
    # Python 3.11 (the Pi's) doesn't map these on its own
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      '.woff2': 'font/woff2', '.svg': 'image/svg+xml'}

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
        if path == '/api/calendar':
            return self.get_calendar()
        if path == '/api/info':
            return self.send_json(200, {'urls': lan_addresses()})
        super().do_GET()

    def get_calendar(self):
        with state_lock:
            settings = settings_of(load_state())
        result = calendar_feed.get(settings)
        # 502 only if every calendar failed; with some working, the page shows what it has plus a note
        source_count = len(settings['calendars']) + bool(settings.get('appsScriptUrl'))
        self.send_json(502 if source_count and len(result['errors']) >= source_count else 200, result)

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
        done = TASK_DONE_PATH_RE.match(self.path)
        if done:
            self.change_state(lambda state, body: complete_task(state, int(done[1])))
        elif self.path == '/update':
            self.update()
        elif self.path == '/kiosk/exit':
            self.exit_kiosk()
        elif self.path == '/kiosk/start':
            self.start_kiosk()
        elif self.path == '/system/reboot':
            self.reboot()
        elif self.path == '/api/events':
            self.change_state(add_event)
        elif self.path == '/api/settings/calendars':
            self.change_state(add_calendar, prepare=checked_calendar)
        elif self.path == '/api/tasks':
            self.change_state(add_task)
        elif self.path == '/api/settings/people':
            self.change_state(add_person)
        else:
            self.send_error(404)

    def do_PUT(self):
        match = EVENT_PATH_RE.match(self.path)
        task = TASK_PATH_RE.match(self.path)
        person = PERSON_PATH_RE.match(self.path)
        if match:
            self.change_state(lambda state, body: edit_event(state, body, int(match[1])))
        elif task:
            self.change_state(lambda state, body: edit_task(state, body, int(task[1])))
        elif person:
            self.change_state(lambda state, body: edit_person(state, body, int(person[1])))
        elif self.path == '/api/settings/todos':
            self.change_state(set_show_todos)
        elif self.path == '/api/background':
            self.change_state(set_background)
        elif self.path == '/api/settings/location':
            self.change_state(lambda state, location: settings_of(state).update(location=location),
                              prepare=lambda body: geocode_zip((body or {}).get('zip')))
        elif self.path == '/api/settings/apps-script':
            self.change_state(lambda state, url: settings_of(state).update(appsScriptUrl=url),
                              prepare=checked_apps_script)
        else:
            self.send_error(404)

    def do_DELETE(self):
        event = EVENT_PATH_RE.match(self.path)
        calendar = CALENDAR_PATH_RE.match(self.path)
        task = TASK_PATH_RE.match(self.path)
        person = PERSON_PATH_RE.match(self.path)
        if event:
            self.change_state(lambda state, body: delete_event(state, int(event[1])))
        elif calendar:
            self.change_state(lambda state, body: remove_calendar(state, int(calendar[1])))
        elif task:
            self.change_state(lambda state, body: delete_task(state, int(task[1])))
        elif person:
            self.change_state(lambda state, body: remove_person(state, int(person[1])))
        else:
            self.send_error(404)

    def change_state(self, change, prepare=None):
        """Applies one change to the saved state and replies with the result.

        Changes are applied to the current file rather than replacing it wholesale, so the wall
        and a phone editing at the same time can't overwrite each other's countdowns.
        prepare(body), if given, runs first and outside the lock: it validates the request
        (looking up a ZIP code, test-reading a calendar link) and returns what change() receives.
        """
        global state_version
        try:
            body = self.read_json()
            if prepare:
                body = prepare(body)
            with state_changed:
                state = load_state()
                change(state, body)
                save_state(state)
                state_version += 1
                state_changed.notify_all()
                state = {**state, 'version': state_version}
        except LookupError as e:
            return self.send_json(404, {'error': str(e.args[0])})
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
    threading.Thread(target=remove_finished, daemon=True).start()
    with DualStackServer(('::', PORT), DashboardRequestHandler) as httpd:
        print(f'Serving dashboard at http://localhost:{PORT}')
        httpd.serve_forever()
