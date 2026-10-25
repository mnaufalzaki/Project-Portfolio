"""HEBAT auth: owner-bound Keychain sessions and bounded, read-only transport."""
from contextlib import contextmanager
import argparse
import fcntl
import getpass
import hashlib
from html.parser import HTMLParser
import json
import math
import os
import re
from pathlib import Path
import threading
import time
from urllib.parse import urljoin, urlparse, parse_qs, unquote
import requests
from keychain_store import KeychainStore, KeychainError

BASE = 'https://hebat.elearning.unair.ac.id/'
ORIGIN = urlparse(BASE).netloc
ROOT = Path(__file__).resolve().parents[1]
STORE = KeychainStore()
MUTEX = threading.RLock()
MEASURE = threading.local()
SESSION_VERSION = 2


class AuthError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class TokenParser(HTMLParser):
    def __init__(self, body):
        super().__init__()
        self.token = None
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input' and a.get('name') == 'logintoken':
            self.token = a.get('value')


@contextmanager
def measure(metrics):
    """Attach aggregate counters to this thread; never record URLs or payloads."""
    previous = getattr(MEASURE, 'metrics', None)
    MEASURE.metrics = metrics
    try:
        yield
    finally:
        MEASURE.metrics = previous


def metric_inc(key, amount=1):
    metrics = getattr(MEASURE, 'metrics', None)
    if metrics is not None:
        metrics.inc(key, amount)


def metric_time(key, elapsed):
    metrics = getattr(MEASURE, 'metrics', None)
    if metrics is not None:
        metrics.add_time(key, elapsed)


def account_id(credentials):
    if not isinstance(credentials, dict) or not isinstance(credentials.get('username'), str) or not credentials['username'].strip():
        raise AuthError('keychain_credentials_format_invalid')
    return hashlib.sha256(('hebat:' + credentials['username']).encode()).hexdigest()[:24]


def session_account_id(session):
    return getattr(session, '_hebat_account_id', None)


def trusted_url(path):
    p = urlparse(urljoin(BASE, path))._replace(fragment='')
    if p.scheme != 'https' or p.netloc != ORIGIN or p.username or p.password:
        raise AuthError('untrusted_origin')
    return p.geturl()


def read_url(path):
    url = trusted_url(path)
    p = urlparse(url)
    q = parse_qs(p.query, keep_blank_values=True)
    if p.path == '/my/' and not q:
        return url
    if p.path in ('/course/view.php', '/mod/assign/index.php', '/mod/assign/view.php', '/mod/resource/view.php', '/mod/url/view.php'):
        if set(q) == {'id'} and len(q['id']) == 1 and q['id'][0].isdigit():
            return url
    if p.path == '/course/overview.php' and set(q) in ({'id'}, {'id', 'expand[]'}):
        if len(q.get('id', [])) == 1 and q['id'][0].isdigit() and q.get('expand[]', ['assign']) == ['assign']:
            return url
    raise AuthError('read_route_not_allowed')


def login_url(path, method='GET'):
    """Authentication may POST only to the login form and GET only safe targets."""
    url = trusted_url(path)
    p = urlparse(url)
    if p.path == '/login/index.php' and not p.query and method in ('GET', 'POST'):
        return url
    if p.path == '/login/index.php' and method == 'GET':
        query = parse_qs(p.query, keep_blank_values=True)
        # Moodle confirms its newly established session with this GET continuation.
        if set(query) == {'testsession'} and len(query['testsession']) == 1 and re.fullmatch('[0-9]{1,20}', query['testsession'][0]):
            return url
    if method == 'GET':
        if p.path == '/' and not p.query:
            return url
        return read_url(url)
    raise AuthError('auth_route_not_allowed')


def attachment_url(path):
    url = trusted_url(path)
    p = urlparse(url)
    decoded = unquote(p.path)
    if not p.path.startswith('/pluginfile.php/') or not p.path.removeprefix('/pluginfile.php/'):
        raise AuthError('attachment_route_not_allowed')
    if any(part in ('.', '..') for part in decoded.split('/')) or any(ord(c) < 32 for c in decoded) or '\\' in decoded:
        raise AuthError('attachment_route_not_allowed')
    try:
        query = parse_qs(p.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise AuthError('attachment_query_not_allowed') from None
    if p.query and query not in ({'forcedownload': ['0']}, {'forcedownload': ['1']}):
        raise AuthError('attachment_query_not_allowed')
    return url


def material_url(path):
    """Only a Moodle Resource or its same-origin file may be resolved."""
    url = trusted_url(path)
    p = urlparse(url)
    if p.path == '/mod/resource/view.php':
        try:
            query = parse_qs(p.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise AuthError('material_route_not_allowed') from None
        if set(query) == {'id'} and len(query['id']) == 1 and re.fullmatch('[0-9]+', query['id'][0]):
            return url
        raise AuthError('material_route_not_allowed')
    return attachment_url(url)


def session_from(value=None, owner=None):
    s = requests.Session()
    s.headers['User-Agent'] = 'Mozilla/5.0 (HEBAT-MCP read-only; Keychain)'
    s._hebat_account_id = owner
    if value:
        if not isinstance(value, dict) or not isinstance(value.get('cookies'), list):
            raise AuthError('keychain_session_format_invalid')
        declared_owner = value.get('account_id') if value.get('version') == SESSION_VERSION else None
        if declared_owner is not None and (not isinstance(declared_owner, str) or not re.fullmatch('[a-f0-9]{24}', declared_owner)):
            raise AuthError('keychain_session_format_invalid')
        s._hebat_account_id = declared_owner
        for c in value['cookies']:
            if not isinstance(c, dict) or c.get('domain', '').lstrip('.') != ORIGIN:
                raise AuthError('invalid_cookie_origin')
            if not isinstance(c.get('name'), str) or not isinstance(c.get('value'), str):
                raise AuthError('keychain_session_format_invalid')
            s.cookies.set(c['name'], c['value'], domain=c['domain'], path=c.get('path', '/'),
                          secure=bool(c.get('secure', True)), expires=c.get('expires'))
    return s


def serialize(s):
    return {'version': SESSION_VERSION, 'account_id': session_account_id(s), 'saved_at': time.time(), 'cookies': [
        {'name': c.name, 'value': c.value, 'domain': c.domain, 'path': c.path, 'secure': c.secure, 'expires': c.expires}
        for c in s.cookies if c.domain.lstrip('.') == ORIGIN]}


def request(s, path, method='GET', data=None, auth_route=False, attachment_route=False, stream=False, material_route=False):
    if sum((bool(auth_route), bool(attachment_route), bool(material_route))) > 1:
        raise AuthError('invalid_request_context')
    method = method.upper()
    if not auth_route and (method != 'GET' or data is not None):
        raise AuthError('read_method_not_allowed')
    validator = login_url if auth_route else material_url if material_route else attachment_url if attachment_route else read_url
    url = validator(path, method) if auth_route else validator(path)
    testsession_seen = bool(auth_route and urlparse(url).query)
    for _ in range(6):
        started = time.perf_counter()
        metric_inc('http_attempts')
        metric_inc('http_' + method.lower())
        try:
            # Inspect redirect headers before consuming bodies: some login redirects
            # keep a chunked response open. Never wait for a body that will be discarded.
            r = s.request(method, url, data=data, timeout=25, allow_redirects=False, stream=True)
        except requests.RequestException:
            metric_inc('http_network_errors')
            raise AuthError('network_unavailable') from None
        finally:
            metric_time('network_seconds', time.perf_counter() - started)
        metric_inc('http_responses')
        metric_inc('http_status_' + str(r.status_code))
        if r.status_code in (301, 302, 303, 307, 308):
            metric_inc('http_redirects')
            try:
                dest = trusted_url(urljoin(url, r.headers.get('Location', '')))
                if r.status_code in (307, 308) and method != 'GET':
                    raise AuthError('unexpected_login_redirect')
                if urlparse(dest).path == '/login/index.php' and not auth_route:
                    login_url(dest)
                    return None
                # Validate before the next request, including authentication redirects.
                next_url = validator(dest, 'GET') if auth_route else validator(dest)
                if auth_route and urlparse(next_url).path == '/login/index.php' and urlparse(next_url).query:
                    if testsession_seen:
                        raise AuthError('unexpected_login_redirect')
                    testsession_seen = True
            finally:
                r.close()
            url, method, data = next_url, 'GET', None
            continue
        if r.status_code in (401, 403) and not auth_route:
            r.close()
            return None
        if r.status_code >= 400:
            r.close()
            raise AuthError('hebat_http_error_' + str(r.status_code))
        if not stream:
            started = time.perf_counter()
            try:
                # Final pages retain eager loading, bounded by the same read timeout.
                text = r.text
            except requests.RequestException:
                metric_inc('http_network_errors')
                r.close()
                raise AuthError('network_unavailable') from None
            finally:
                metric_time('network_seconds', time.perf_counter() - started)
            if not auth_route and re.search(r"name=['\"](?:logintoken|username)['\"]", text) and re.search(r"name=['\"]password['\"]", text):
                r.close()
                return None
        return r
    raise AuthError('redirect_limit')


def authenticated(s):
    metric_inc('session_verifications')
    started = time.perf_counter()
    try:
        r = request(s, 'my/')
        if r is None:
            return False
        try:
            return '/login/logout.php' in r.text
        finally:
            r.close()
    finally:
        metric_time('session_verification_seconds', time.perf_counter() - started)


@contextmanager
def refresh_lock():
    folder = ROOT / '.session'
    folder.mkdir(mode=0o700, exist_ok=True)
    folder.chmod(0o700)
    with MUTEX:
        fd = os.open(folder / 'auth.lock', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def persist_verified(s, interactive=False):
    bundle = serialize(s)
    if not bundle['account_id']:
        raise AuthError('session_identity_missing')
    current = STORE.read('credentials', interactive=interactive)
    if not current or account_id(current) != bundle['account_id']:
        raise AuthError('session_identity_mismatch')
    if not bundle['cookies']:
        raise AuthError('no_session_cookie')
    STORE.write('session', bundle, interactive=interactive)
    restored = STORE.read('session', interactive=interactive)
    if restored != bundle:
        raise AuthError('keychain_session_verification_failed')
    if not authenticated(session_from(restored)):
        raise AuthError('restored_session_not_authenticated')
    return bundle


def login_once(credentials, interactive=False):
    """Validate new credentials in memory; the caller commits the bound pair."""
    metric_inc('login_attempts')
    s = session_from(owner=account_id(credentials))
    r = request(s, 'login/index.php', auth_route=True)
    try:
        token = TokenParser(r.text).token
    finally:
        r.close()
    if not token:
        raise AuthError('login_form_or_sso_changed')
    r = request(s, 'login/index.php', method='POST', data={'anchor': '', 'logintoken': token,
                'username': credentials['username'], 'password': credentials['password']}, auth_route=True)
    try:
        if '/login/' in r.url or 'loginerrormessage' in r.text.lower():
            raise AuthError('credentials_rejected')
    finally:
        r.close()
    if not authenticated(s):
        raise AuthError('login_not_authenticated')
    return s


def remove_legacy():
    # Called only after independent Keychain round-trip and authenticated restore.
    removed = []
    for name in ['cookies.env', 'cookies.txt']:
        path = ROOT / '.session' / name
        if path.exists():
            path.unlink()
            removed.append(name)
    return removed


def _credentials(expected_account_id=None):
    credentials = STORE.read('credentials')
    if not credentials:
        raise AuthError('keychain_setup_required')
    owner = account_id(credentials)
    if expected_account_id is not None and owner != expected_account_id:
        raise AuthError('account_identity_changed')
    return credentials, owner


def _cached_session(cached, owner):
    if not cached:
        return None
    s = session_from(cached)
    bound = session_account_id(s)
    if bound is None:
        return None  # Legacy sessions are renewed, never rebound by assumption.
    if bound != owner:
        raise AuthError('session_identity_mismatch')
    return s


def ensure_client(force=False, expected_account_id=None):
    credentials, owner = _credentials(expected_account_id)
    first_cached = STORE.read('session') if not force else None
    if not force:
        s = _cached_session(first_cached, owner)
        if s is not None and authenticated(s):
            return s, False
    with refresh_lock():
        credentials, current_owner = _credentials(expected_account_id)
        if current_owner != owner:
            raise AuthError('account_identity_changed')
        if not force:
            cached = STORE.read('session')
            s = _cached_session(cached, owner)
            # Another process may have renewed while this caller waited for the lock.
            if cached != first_cached and s is not None and authenticated(s):
                return s, False
        control = STORE.read('control') or {}
        if not isinstance(control, dict):
            raise AuthError('keychain_control_format_invalid')
        if control.get('requires_setup'):
            raise AuthError('credentials_update_required')
        last_attempt = control.get('last_attempt', 0)
        if isinstance(last_attempt, bool) or not isinstance(last_attempt, (int, float)) or not math.isfinite(last_attempt):
            raise AuthError('keychain_control_format_invalid')
        if time.time() - last_attempt < 60:
            raise AuthError('auto_login_cooldown')
        STORE.write('control', {'last_attempt': time.time(), 'requires_setup': False})
        try:
            s = login_once(credentials)
            if session_account_id(s) != owner:
                raise AuthError('session_identity_mismatch')
            persist_verified(s)
        except AuthError as e:
            if e.code in ('credentials_rejected', 'login_form_or_sso_changed', 'login_not_authenticated'):
                STORE.write('control', {'last_attempt': time.time(), 'requires_setup': True, 'reason': e.code})
            raise
        STORE.write('control', {'last_success': time.time(), 'requires_setup': False})
        remove_legacy()
        return s, True


def read_page(path):
    url = read_url(path)
    s, renewed = ensure_client()
    r = request(s, url)
    if r is None:
        if renewed:
            raise AuthError('session_rejected_after_login')
        s, _ = ensure_client(force=True, expected_account_id=session_account_id(s))
        r = request(s, url)
        if r is None:
            raise AuthError('session_rejected_after_login')
    return r


def status(force=False):
    _, renewed = ensure_client(force=force)
    return {'authenticated': True, 'storage': 'macos-keychain', 'auto_login_used': renewed, 'url': BASE + 'my/'}


def setup():
    if not __import__('sys').stdin.isatty():
        raise AuthError('interactive_terminal_required')
    os.umask(0o077)
    print('Pengaturan HEBAT Keychain — akun disimpan lokal di Keychain macOS.')
    print('NIM dan password tidak masuk ke chat, argumen proses, atau file biasa.')
    username = input('NIM/username HEBAT: ').strip()
    password = getpass.getpass('Password HEBAT (tidak ditampilkan): ')
    if not username or not password:
        raise AuthError('empty_credentials')
    credentials = {'username': username, 'password': password}
    with refresh_lock():
        session = login_once(credentials, interactive=True)
        if session_account_id(session) != account_id(credentials):
            raise AuthError('session_identity_mismatch')
        STORE.write('credentials', credentials, interactive=True)
        if STORE.read('credentials', interactive=True) != credentials:
            raise AuthError('keychain_credentials_verification_failed')
        persist_verified(session, interactive=True)
        STORE.write('control', {'last_success': time.time(), 'requires_setup': False}, interactive=True)
        removed = remove_legacy()
    print('Berhasil. Kredensial dan sesi tersimpan di Keychain; login ulang otomatis aktif.')
    print('Salinan cookie teks lama telah dihapus setelah penyimpanan dan akses terverifikasi.')
    return {'setup_complete': True, 'storage': 'macos-keychain', 'legacy_cookie_files_removed': len(removed)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['setup', 'status', 'refresh'])
    a = p.parse_args()
    try:
        result = setup() if a.action == 'setup' else status(force=a.action == 'refresh')
        print(json.dumps(result))
        return 0
    except (AuthError, KeychainError) as e:
        print(json.dumps({'authenticated': False, 'storage': 'macos-keychain', 'error': e.code}))
        return 1
    except Exception:
        print(json.dumps({'authenticated': False, 'storage': 'macos-keychain', 'error': 'unexpected_auth_error'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
