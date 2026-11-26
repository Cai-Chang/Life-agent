"""Check a running deployment; exercise auth only on disposable CI environments."""
import argparse
import http.cookiejar
import json
import secrets
import urllib.error
import urllib.request
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    parser.add_argument('--exercise-auth', action='store_true', help='Creates a fake account; use only in an isolated test stack')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(route, body=None, method=None, csrf=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if body is not None and route.startswith(('/api/v1/events', '/api/v1/tasks')):
            headers['Idempotency-Key'] = key or str(uuid4())
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = urllib.request.Request(base+route, data=None if body is None else json.dumps(body).encode(), headers=headers, method=method)
        try:
            response = opener.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw and response.headers.get_content_type() == 'application/json' else raw

    assert request('/health/ready') == (200, {'status': 'ready'}), 'Deployment database or migration not ready'
    status, html = request('/')
    assert status == 200 and b'LifeAgent' in html, 'Frontend did not respond'
    if args.exercise_auth:
        status, profile = request('/api/v1/auth/register', {'email':f'ci-{uuid4().hex}@example.com',
            'password':secrets.token_urlsafe(24), 'display_name':'CI Test', 'timezone':'UTC'})
        assert status == 201, f'Registration failed: HTTP {status}'
        workspace = profile['workspace']['id']
        assert request('/api/v1/me')[1]['workspace']['id'] == workspace
        assert request('/api/v1/workspaces/'+workspace, {'name':'CI workspace'}, method='PATCH', csrf=profile['csrf_token'])[0] == 200
        csrf = profile['csrf_token']
        event_body = {'title':'CI event', 'start_at':'2026-12-10T09:00:00Z', 'end_at':'2026-12-10T10:00:00Z'}
        operation = str(uuid4())
        code, event = request('/api/v1/events', event_body, csrf=csrf, key=operation)
        assert code == 201
        assert request('/api/v1/events', event_body, csrf=csrf, key=operation) == (201, event)
        assert request('/api/v1/events', event_body, csrf=csrf)[0] == 409
        code, task = request('/api/v1/tasks', {'title':'CI task', 'event_id':event['id']}, csrf=csrf)
        assert code == 201
        assert request('/api/v1/tasks/'+task['id'], {'version':1,'status':'done'}, method='PATCH', csrf=csrf)[0] == 200
        assert request('/api/v1/events/'+event['id'], {'version':1}, method='DELETE', csrf=csrf)[1]['status'] == 'cancelled'
        assert request('/api/v1/tasks/'+task['id'])[1]['status'] == 'done'
        assert request('/api/v1/tasks/'+task['id'], {'version':2}, method='DELETE', csrf=csrf)[0] == 200
        print('Planning smoke passed: event, replay, conflict, linked task, completion, cancellation and deletion.')
        assert request('/api/v1/auth/logout', {}, csrf=csrf)[0] == 204
        assert request('/api/v1/me')[0] == 401
        print('Container auth smoke passed: register, session, personal workspace, logout.')
    print('Deployment health and frontend smoke passed.')


if __name__ == '__main__':
    main()
