"""Google Tasks on the to-do list, through the Apps Script web app in google_tasks_data.gs.

The dashboard posts an action ("read", "done", "add", ...) and its key to the script's link, and the
script answers with every list and to-do in the Google account. The script remembers the first key
it's sent, so once this dashboard is connected the link alone is no use to anyone else.
"""
import datetime as dt
import json
import secrets
import urllib.error
import urllib.request


class GoogleTasksError(Exception):
    """The script couldn't be reached or refused, with a message fit to show the user."""


def new_key():
    return secrets.token_urlsafe(24)


def done_date(completed):
    """The local day a to-do was checked off, from Google's UTC time."""
    if not completed:
        return None
    return dt.datetime.fromisoformat(completed.replace('Z', '+00:00')).astimezone().date().isoformat()


def call(url, key, action, **params):
    """Sends one action; returns {'lists': [{id, title}], 'tasks': [...], 'created': new to-do's id}."""
    body = json.dumps({'key': key, 'action': action, **params}).encode()
    # Apps Script answers a POST with a redirect to the result, which urllib follows with a GET
    request = urllib.request.Request(url, data=body, method='POST', headers={
        'Content-Type': 'application/json', 'User-Agent': 'Home-Dashboard'})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            text = response.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        raise GoogleTasksError(f'the link returned an error ({e.code})') from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GoogleTasksError('the link could not be reached') from e
    try:
        data = json.loads(text)
    except ValueError as e:
        # Google's sign-in or error page: usually the deployment isn't set to "Anyone"
        raise GoogleTasksError("the link didn't answer like the Google Tasks script; check that the "
                               "deployment's access is set to Anyone") from e
    error = data.get('error') if isinstance(data, dict) else 'unexpected answer'
    if error:
        if 'Tasks is not defined' in error:
            error = 'add the Google Tasks API under Services in the script, then deploy a new version'
        raise GoogleTasksError(error)
    try:
        return {
            'lists': [{'id': l['id'], 'title': l['title']} for l in data['lists']],
            'tasks': [{'id': t['id'], 'list': t['list'], 'title': t['title'], 'notes': t.get('notes') or '',
                       'due': t.get('due'), 'done': done_date(t.get('completed'))} for t in data['tasks']],
            'created': data.get('created'),
        }
    except (KeyError, TypeError, ValueError) as e:
        raise GoogleTasksError('the script sent something unexpected; paste in its latest version') from e
