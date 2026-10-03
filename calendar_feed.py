"""Builds the calendar column (today, tomorrow and the day after) from the household's calendars.

Sources, set from the phone remote's settings:
  - iCal links ("Secret address in iCal format" in Google Calendar, or any other .ics feed)
  - optionally a Google Apps Script web app (google_calendar_data.gs), the original setup

Results are cached for a few minutes, since every open screen asks for them.
"""
import datetime as dt
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

try:
    import icalendar
    import recurring_ical_events
except ImportError:  # deploy/install.sh installs these into .venv
    icalendar = recurring_ical_events = None

CACHE_SECONDS = 5 * 60
DAY_KEYS = ('today', 'tomorrow', 'dayAfterTomorrow')

_cache = {'key': None, 'at': 0.0, 'result': None}
_cache_lock = threading.Lock()


class CalendarError(Exception):
    """A calendar link that can't be read, with a message fit to show the user."""


def normalize_url(url):
    url = url.strip()
    if url.lower().startswith('webcal://'):
        url = 'https://' + url[len('webcal://'):]
    return url


def fetch(url, timeout=20):
    request = urllib.request.Request(url, headers={'User-Agent': 'Home-Dashboard'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as e:
        raise CalendarError(f'the link returned an error ({e.code})') from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise CalendarError('the link could not be reached') from e


def parse_ical(data):
    if icalendar is None:
        raise CalendarError('calendar support is not installed (run deploy/install.sh)')
    try:
        return icalendar.Calendar.from_ical(data)
    except ValueError as e:
        raise CalendarError("that link doesn't lead to a calendar file") from e


def check_ical_url(url):
    """Raises CalendarError with a helpful message unless url serves a readable iCal feed."""
    parsed = urllib.parse.urlparse(normalize_url(url))
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise CalendarError('that is not a web link')
    if parsed.netloc == 'calendar.google.com' and '/ical/' not in parsed.path:
        raise CalendarError('that is the calendar\'s web page; use its "Secret address in iCal format" '
                            'from the calendar\'s settings')
    parse_ical(fetch(normalize_url(url)))


def clock(t):
    return f'{t.hour % 12 or 12}:{t.minute:02d} {"AM" if t.hour < 12 else "PM"}'


def time_label(start, end, day_start, day_end):
    """'9:00 AM'; 'All Day' for all-day events; 'Until 7:00 AM' for one carried over from the night before."""
    if not isinstance(start, dt.datetime):
        return 'All Day'
    if start < day_start:
        return f'Until {clock(end)}' if end < day_end else 'All Day'
    return clock(start)


def local(value):
    """Event times as aware local times (floating times are taken as local); all-day dates unchanged."""
    return value.astimezone() if isinstance(value, dt.datetime) else value


def span_of(start, end):
    """(first day, number of days) an event covers. All-day DTEND is the day after the last day."""
    if isinstance(start, dt.datetime):
        last = (end - dt.timedelta(microseconds=1)).date() if end > start else start.date()
        first = start.date()
    else:
        first = start
        last = end - dt.timedelta(days=1) if end > start else start
    return first, (last - first).days + 1


def place(found, title, start, end, days):
    """Adds an event to each of the days it falls on, in found: {day index: [event, ...]}."""
    first, length = span_of(start, end)
    for i, (day_start, day_end) in enumerate(days):
        if isinstance(start, dt.datetime):
            overlaps = start < day_end and (end > day_start or start >= day_start)
        else:
            overlaps = first <= day_start.date() < first + dt.timedelta(days=length)
        if not overlaps:
            continue
        label = time_label(start, end, day_start, day_end)
        found[i].append({
            # All-day and carried-over events first, then by start time
            'sort': (1, start.strftime('%H:%M')) if label[0].isdigit() else (0, ''),
            'title': title,
            'time': label,
            # When a timed event ends, so the wall can take it off Today afterwards
            'end': end.isoformat() if isinstance(end, dt.datetime) else None,
            'span': {'day': (day_start.date() - first).days + 1, 'of': length} if length > 1 else None,
        })


def ical_events(url, days):
    """{day index: [event, ...]} for one iCal feed."""
    calendar = parse_ical(fetch(normalize_url(url)))
    found = {i: [] for i in range(len(days))}
    for event in recurring_ical_events.of(calendar).between(days[0][0], days[-1][1]):
        if str(event.get('STATUS', '')).upper() == 'CANCELLED':
            continue
        title = str(event.get('SUMMARY', '')).strip() or '(No title)'
        start = local(event.decoded('DTSTART'))
        end = local(event.decoded('DTEND')) if event.get('DTEND') else start
        place(found, title, start, end, days)
    return found


def apps_script_events(url, days):
    """Same shape as ical_events, from the Google Apps Script web app (google_calendar_data.gs)."""
    text = fetch(url).decode('utf-8', 'replace')
    try:
        data = json.loads(text[text.index('(') + 1:text.rindex(')')])  # it answers "callback({...})"
    except ValueError as e:
        raise CalendarError('the Apps Script link did not return calendar data') from e
    found = {i: [] for i in range(len(days))}
    unique = {}
    for i, key in enumerate(DAY_KEYS[:len(days)]):
        for event in data.get(key, []):
            title = (event.get('title') or '').strip() or '(No title)'
            if 'start' in event:  # current script: real start and end times, placed like iCal events
                start, end = (dt.datetime.fromisoformat(event[k]).astimezone() for k in ('start', 'end'))
                if event.get('allDay'):
                    start, end = start.date(), end.date()
                unique[(title, start, end)] = (title, start, end)
            else:  # older script: only a time label per day; no end times or spans
                label = event.get('time', 'All Day')
                sort_time = dt.datetime.strptime(label, '%I:%M %p').strftime('%H:%M') if label != 'All Day' else ''
                found[i].append({'sort': (0, '') if label == 'All Day' else (1, sort_time), 'title': title,
                                 'time': label, 'end': None, 'span': None})
    for title, start, end in unique.values():
        place(found, title, start, end, days)
    return found


def three_days(now=None):
    """(start, end) local datetimes for today, tomorrow and the day after."""
    today = (now or dt.datetime.now()).date()
    days = []
    for offset in range(3):
        d = today + dt.timedelta(days=offset)
        start = dt.datetime(d.year, d.month, d.day).astimezone()  # local midnight, DST-correct
        nxt = d + dt.timedelta(days=1)
        days.append((start, dt.datetime(nxt.year, nxt.month, nxt.day).astimezone()))
    return days


def build(settings):
    """The calendar column for these settings: {'configured', 'today', 'tomorrow', ..., 'dates', 'errors'}."""
    calendars = settings.get('calendars') or []
    apps_script = settings.get('appsScriptUrl')
    days = three_days()
    result = {
        'configured': bool(calendars or apps_script),
        'dates': {
            'today': days[0][0].day,
            'tomorrow': days[1][0].day,
            'dayAfterTomorrow': days[2][0].day,
            'dayAfterTomorrowName': days[2][0].strftime('%A'),
        },
        'errors': [],
    }
    sources = [(c.get('label') or 'Calendar', ical_events, c['url']) for c in calendars]
    if apps_script:
        sources.append(('Apps Script', apps_script_events, apps_script))

    merged = {i: [] for i in range(3)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [(name, pool.submit(func, url, days)) for name, func, url in sources]
    for name, future in futures:
        try:
            for i, events in future.result().items():
                merged[i].extend(events)
        except CalendarError as e:
            result['errors'].append(f'{name}: {e}')
        except Exception as e:  # a malformed feed shouldn't take down the whole column
            result['errors'].append(f'{name}: could not be read ({type(e).__name__})')

    for i, key in enumerate(DAY_KEYS):
        seen, events = set(), []
        # The same event often appears in several shared calendars; show it once
        for event in sorted(merged[i], key=lambda e: (e['sort'], e['title'])):
            if (event['title'], event['time']) not in seen:
                seen.add((event['title'], event['time']))
                events.append({k: event[k] for k in ('title', 'time', 'end', 'span')})
        result[key] = events
    return result


def get(settings):
    """build(), cached per settings and day."""
    key = json.dumps([settings.get('calendars'), settings.get('appsScriptUrl'), dt.date.today().isoformat()])
    with _cache_lock:
        if _cache['key'] == key and time.time() - _cache['at'] < CACHE_SECONDS:
            return _cache['result']
        result = build(settings)
        source_count = len(settings.get('calendars') or []) + bool(settings.get('appsScriptUrl'))
        if len(result['errors']) < source_count:  # don't cache a total failure; retry next time
            _cache.update(key=key, at=time.time(), result=result)
        return result
