"""Offline auth regressions. No real Keychain item or campus request is used."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
import auth


class MemoryStore:
    def __init__(self):
        self.items = {}
        self.writes = []

    def read(self, key, interactive=False):
        return self.items.get(key)

    def write(self, key, value, interactive=False):
        self.items[key] = value
        self.writes.append(key)


class Response:
    def __init__(self, status=200, text='', location=None, url=auth.BASE + 'my/'):
        self.status_code = status
        self.text = text
        self.headers = {'Location': location} if location else {}
        self.url = url
        self.closed = False

    def close(self):
        self.closed = True


class Transport:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = MemoryStore()
        self.credentials = {'username': 'fixture', 'password': 'not-a-real-password'}
        self.store.items['credentials'] = self.credentials.copy()
        for p in [patch.object(auth, 'STORE', self.store), patch.object(auth, 'ROOT', Path(self.tmp.name))]:
            p.start()
            self.addCleanup(p.stop)

    def session(self, credentials=None):
        s = auth.session_from(owner=auth.account_id(credentials or self.credentials))
        s.cookies.set('MoodleSession', 'fixture-cookie', domain=auth.ORIGIN, path='/', secure=True)
        return s

    def legacy(self):
        d = Path(self.tmp.name) / '.session'
        d.mkdir(exist_ok=True)
        for n in ['cookies.env', 'cookies.txt']:
            (d / n).write_text('fixture-only')
        return d

    def cache_session(self):
        self.store.items['session'] = auth.serialize(self.session())

    def test_cookie_roundtrip_no_plaintext(self):
        bundle = auth.serialize(self.session())
        restored = auth.session_from(bundle)
        self.assertEqual(restored.cookies.get('MoodleSession'), 'fixture-cookie')
        self.assertEqual(auth.session_account_id(restored), auth.account_id(self.credentials))
        self.assertEqual(bundle['version'], 2)
        self.assertFalse(list(Path(self.tmp.name).rglob('cookies.*')))

    def test_cached_valid_session_never_logs_in(self):
        self.cache_session()
        with patch.object(auth, 'authenticated', return_value=True) as verify, patch.object(auth, 'login_once') as login:
            _, used = auth.ensure_client()
        self.assertFalse(used)
        login.assert_not_called()
        self.assertEqual(verify.call_count, 1)

    def test_expired_session_one_login(self):
        self.cache_session()
        with patch.object(auth, 'authenticated', return_value=False) as verify, patch.object(auth, 'login_once', return_value=self.session()) as login, patch.object(auth, 'persist_verified'):
            _, used = auth.ensure_client()
        self.assertTrue(used)
        self.assertEqual(login.call_count, 1)
        self.assertEqual(verify.call_count, 1)

    def test_bad_password_blocks_repeated_attempts(self):
        with patch.object(auth, 'login_once', side_effect=auth.AuthError('credentials_rejected')) as login:
            with self.assertRaisesRegex(auth.AuthError, 'credentials_rejected'):
                auth.ensure_client()
            with self.assertRaisesRegex(auth.AuthError, 'credentials_update_required'):
                auth.ensure_client()
        self.assertEqual(login.call_count, 1)

    def test_network_error_does_not_relogin(self):
        self.cache_session()
        with patch.object(auth, 'authenticated', side_effect=auth.AuthError('network_unavailable')), patch.object(auth, 'login_once') as login:
            with self.assertRaisesRegex(auth.AuthError, 'network_unavailable'):
                auth.ensure_client()
        login.assert_not_called()
        self.assertNotIn('control', self.store.writes)

    def test_keychain_locked_has_no_file_fallback(self):
        self.legacy()
        with patch.object(self.store, 'read', side_effect=auth.KeychainError(-25308)), patch.object(auth, 'login_once') as login:
            with self.assertRaises(auth.KeychainError):
                auth.ensure_client()
        login.assert_not_called()
        self.assertTrue((Path(self.tmp.name) / '.session/cookies.env').exists())

    def test_migration_only_after_authenticated_restore(self):
        d = self.legacy()
        with patch.object(auth, 'authenticated', return_value=False):
            with self.assertRaisesRegex(auth.AuthError, 'restored_session_not_authenticated'):
                auth.persist_verified(self.session())
        self.assertTrue((d / 'cookies.env').exists())

    def test_successful_setup_commits_credentials_before_session(self):
        d = self.legacy()
        stream = io.StringIO()
        new = {'username': 'fixture-new', 'password': 'fixture-new-password'}
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=new['username']), patch('getpass.getpass', return_value=new['password']), patch.object(auth, 'login_once', return_value=self.session(new)), patch.object(auth, 'authenticated', return_value=True), contextlib.redirect_stdout(stream):
            result = auth.setup()
        self.assertTrue(result['setup_complete'])
        self.assertFalse((d / 'cookies.env').exists())
        self.assertNotIn(new['password'], stream.getvalue())
        self.assertEqual(self.store.writes[:2], ['credentials', 'session'])
        self.assertEqual(self.store.items['session']['account_id'], auth.account_id(new))

    def test_interrupted_setup_keeps_old_session_if_credential_write_fails(self):
        self.cache_session()
        old = self.store.items['session']
        original = self.store.write
        new = {'username': 'fixture-new', 'password': 'fixture-new-password'}
        def fail_credentials(key, value, **kwargs):
            if key == 'credentials':
                raise auth.KeychainError(-25308)
            original(key, value, **kwargs)
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=new['username']), patch('getpass.getpass', return_value=new['password']), patch.object(auth, 'login_once', return_value=self.session(new)), patch.object(self.store, 'write', side_effect=fail_credentials), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(auth.KeychainError):
                auth.setup()
        self.assertEqual(self.store.items['session'], old)
        self.assertEqual(self.store.items['credentials'], self.credentials)

    def test_failed_session_commit_leaves_mismatch_closed(self):
        self.cache_session()
        old = self.store.items['session']
        original = self.store.write
        new = {'username': 'fixture-new', 'password': 'fixture-new-password'}
        def fail_session(key, value, **kwargs):
            if key == 'session':
                raise auth.KeychainError(-25308)
            original(key, value, **kwargs)
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value=new['username']), patch('getpass.getpass', return_value=new['password']), patch.object(auth, 'login_once', return_value=self.session(new)), patch.object(self.store, 'write', side_effect=fail_session), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(auth.KeychainError):
                auth.setup()
        self.assertEqual(self.store.items['session'], old)
        with patch.object(auth, 'authenticated') as verify, patch.object(auth, 'login_once') as login:
            with self.assertRaisesRegex(auth.AuthError, 'session_identity_mismatch'):
                auth.ensure_client()
        verify.assert_not_called()
        login.assert_not_called()

    def test_expected_account_change_rejected_before_network(self):
        self.cache_session()
        with patch.object(auth, 'authenticated') as verify, patch.object(auth, 'login_once') as login:
            with self.assertRaisesRegex(auth.AuthError, 'account_identity_changed'):
                auth.ensure_client(expected_account_id='a' * 24)
        verify.assert_not_called()
        login.assert_not_called()

    def test_session_owner_mismatch_rejected_before_network(self):
        self.store.items['session'] = auth.serialize(self.session({'username': 'other', 'password': 'fixture-only'}))
        with patch.object(auth, 'authenticated') as verify, patch.object(auth, 'login_once') as login:
            with self.assertRaisesRegex(auth.AuthError, 'session_identity_mismatch'):
                auth.ensure_client()
        verify.assert_not_called()
        login.assert_not_called()

    def test_legacy_session_renews_once_without_rebinding(self):
        self.store.items['session'] = {'version': 1, 'cookies': []}
        with patch.object(auth, 'login_once', return_value=self.session()) as login, patch.object(auth, 'persist_verified'):
            _, used = auth.ensure_client()
        self.assertTrue(used)
        self.assertEqual(login.call_count, 1)

    def test_unbound_session_cannot_be_persisted(self):
        s = auth.session_from()
        with self.assertRaisesRegex(auth.AuthError, 'session_identity_missing'):
            auth.persist_verified(s)
        self.assertNotIn('session', self.store.writes)

    def test_missing_credential_needs_setup(self):
        self.store.items.clear()
        with self.assertRaisesRegex(auth.AuthError, 'keychain_setup_required'):
            auth.ensure_client()

    def test_cooldown(self):
        self.store.items['control'] = {'last_attempt': auth.time.time()}
        with patch.object(auth, 'login_once') as login:
            with self.assertRaisesRegex(auth.AuthError, 'auto_login_cooldown'):
                auth.ensure_client()
        login.assert_not_called()

    def test_force_renew_skips_existing_session(self):
        self.cache_session()
        with patch.object(auth, 'login_once', return_value=self.session()) as login, patch.object(auth, 'persist_verified'):
            _, used = auth.ensure_client(force=True)
        self.assertTrue(used)
        self.assertEqual(login.call_count, 1)

    def test_read_routes_and_external_urls(self):
        for value in ['/login/logout.php?sesskey=x', '/mod/assign/view.php?id=1&action=submit', '/mod/assign/view.php?id=1&action=', 'https://example.com/', 'http://hebat.elearning.unair.ac.id/my/']:
            with self.subTest(value=value), self.assertRaises(auth.AuthError):
                auth.read_url(value)
        self.assertNotIn('#', auth.read_url('/course/overview.php?id=1&expand%5B%5D=assign#x'))

    def test_off_origin_cookie_rejected(self):
        with self.assertRaises(auth.AuthError):
            auth.session_from({'cookies': [{'name': 'x', 'value': 'fixture', 'domain': 'example.com'}]})

    def test_auth_redirect_logout_and_write_rejected_before_destination(self):
        for location in ['/login/logout.php?sesskey=fixture', '/mod/assign/view.php?id=1&action=submit', 'https://other.example/my/', '/user/edit.php', '/login/index.php?arbitrary=1']:
            transport = Transport([Response(302, location=location)])
            with self.subTest(location=location), self.assertRaises(auth.AuthError):
                auth.request(transport, 'login/index.php', auth_route=True)
            self.assertEqual(len(transport.calls), 1)

    def test_auth_post_can_redirect_to_dashboard(self):
        transport = Transport([Response(303, location='/my/'), Response(text='fixture')])
        auth.request(transport, 'login/index.php', method='POST', data={'fixture': 'only'}, auth_route=True)
        self.assertEqual([x[0] for x in transport.calls], ['POST', 'GET'])
        self.assertIsNone(transport.calls[1][2]['data'])

    def test_moodle_session_test_continuation_gets_only_numeric_query(self):
        transport = Transport([Response(303, location='/login/index.php?testsession=12345'), Response(303, location='/my/'), Response(text='fixture')])
        auth.request(transport, 'login/index.php', method='POST', data={'fixture': 'only'}, auth_route=True)
        self.assertEqual([x[0] for x in transport.calls], ['POST', 'GET', 'GET'])
        self.assertIsNone(transport.calls[1][2]['data'])
        for path in ['/login/index.php?testsession=', '/login/index.php?testsession=x', '/login/index.php?testsession=1&testsession=2', '/login/index.php?testsession=1&resendconfirmemail=1']:
            with self.subTest(path=path), self.assertRaises(auth.AuthError):
                auth.login_url(path)
        with self.assertRaises(auth.AuthError):
            auth.login_url('/login/index.php?testsession=1', 'POST')

    def test_repeated_moodle_session_test_continuation_is_bounded(self):
        transport = Transport([Response(303, location='/login/index.php?testsession=12345'), Response(303, location='/login/index.php?testsession=12345')])
        with self.assertRaisesRegex(auth.AuthError, 'unexpected_login_redirect'):
            auth.request(transport, 'login/index.php', auth_route=True)
        self.assertEqual(len(transport.calls), 2)

    def test_auth_post_target_restricted_before_request(self):
        transport = Transport([])
        with self.assertRaises(auth.AuthError):
            auth.request(transport, '/my/', method='POST', data={}, auth_route=True)
        self.assertEqual(transport.calls, [])

    def test_non_auth_post_restricted_before_request(self):
        transport = Transport([])
        with self.assertRaisesRegex(auth.AuthError, 'read_method_not_allowed'):
            auth.request(transport, '/my/', method='POST', data={})
        self.assertEqual(transport.calls, [])

    def test_post_307_rejected_without_replaying_credentials(self):
        transport = Transport([Response(307, location='/login/index.php')])
        with self.assertRaisesRegex(auth.AuthError, 'unexpected_login_redirect'):
            auth.request(transport, '/login/index.php', method='POST', data={'fixture': 'only'}, auth_route=True)
        self.assertEqual(len(transport.calls), 1)

    def test_attachment_queries_and_traversal(self):
        path = '/pluginfile.php/123/mod_assign/introattachment/0/task.pdf'
        for suffix in ['', '?forcedownload=0', '?forcedownload=1']:
            self.assertTrue(auth.attachment_url(path + suffix).endswith(suffix or 'task.pdf'))
        for value in [path + '?forcedownload=', path + '?forcedownload=1&token=fixture', path + '?forcedownload=1&forcedownload=1', path + '?broken', '/pluginfile.php/', '/pluginfile.php/%2e%2e/logout.php', 'https://other.example' + path]:
            with self.subTest(value=value), self.assertRaises(auth.AuthError):
                auth.attachment_url(value)

    def test_attachment_external_redirect_rejected_before_destination(self):
        redirect = Response(302, location='https://other.example/task.pdf')
        transport = Transport([redirect])
        with self.assertRaises(auth.AuthError):
            auth.request(transport, '/pluginfile.php/1/task.pdf?forcedownload=1', attachment_route=True, stream=True)
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(redirect.closed)

    def test_attachment_expired_session_returns_none_without_login_get(self):
        transport = Transport([Response(302, location='/login/index.php')])
        result = auth.request(transport, '/pluginfile.php/1/task.pdf', attachment_route=True, stream=True)
        self.assertIsNone(result)
        self.assertEqual(len(transport.calls), 1)

    def test_stream_response_is_not_read_as_text_by_transport(self):
        class StreamResponse:
            status_code = 200
            headers = {'Content-Type': 'text/html'}
            @property
            def text(self):
                raise AssertionError('stream transport must leave bounded body inspection to downloader')
        response = StreamResponse()
        transport = Transport([response])
        returned = auth.request(transport, '/pluginfile.php/1/task.pdf', attachment_route=True, stream=True)
        self.assertIs(returned, response)
        self.assertTrue(transport.calls[0][2]['stream'])

    def test_metrics_count_attempt_redirect_and_no_sensitive_values(self):
        class Metrics:
            def __init__(self):
                self.counts = {}
                self.times = {}
            def inc(self, key, amount=1):
                self.counts[key] = self.counts.get(key, 0) + amount
            def add_time(self, key, value):
                self.times[key] = self.times.get(key, 0) + value
        metrics = Metrics()
        transport = Transport([Response(302, location='/my/'), Response(text='fixture')])
        with auth.measure(metrics):
            auth.request(transport, '/login/index.php', auth_route=True)
        self.assertEqual(metrics.counts['http_get'], 2)
        self.assertEqual(metrics.counts['http_redirects'], 1)
        self.assertEqual(metrics.counts['http_attempts'], 2)
        self.assertEqual(metrics.counts['http_status_302'], 1)
        self.assertEqual(metrics.counts['http_status_200'], 1)
        self.assertIn('network_seconds', metrics.times)
        self.assertTrue(all('fixture' not in key and '/' not in key for key in metrics.counts))

    def test_request_network_exception_has_safe_code(self):
        transport = Transport([auth.requests.RequestException('fixture-secret-url')])
        with self.assertRaisesRegex(auth.AuthError, '^network_unavailable$'):
            auth.request(transport, '/my/')

    def test_login_redirect_body_need_not_finish_before_following_headers(self):
        class SlowRedirect(Response):
            @property
            def text(self):
                raise auth.requests.ReadTimeout('fixture unfinished redirect body')
            @text.setter
            def text(self, value):
                pass
        redirect = SlowRedirect(303, location='/login/index.php?testsession=123')
        transport = Transport([redirect, Response(303, location='/my/'), Response(text='logged in')])
        result = auth.request(transport, '/login/index.php', method='POST', data={'fixture':'only'}, auth_route=True)
        self.assertEqual(result.text, 'logged in')
        self.assertTrue(redirect.closed)
        self.assertEqual([c[0] for c in transport.calls], ['POST','GET','GET'])
        self.assertTrue(all(c[2]['stream'] is True for c in transport.calls))
        self.assertTrue(all(c[2]['data'] is None for c in transport.calls[1:]))

    def test_final_page_body_timeout_remains_safe_error(self):
        class SlowPage(Response):
            @property
            def text(self):
                raise auth.requests.ReadTimeout('fixture secret body')
            @text.setter
            def text(self, value):
                pass
        response = SlowPage()
        with self.assertRaisesRegex(auth.AuthError, '^network_unavailable$'):
            auth.request(Transport([response]), '/my/')
        self.assertTrue(response.closed)

    def test_material_redirect_to_file_keeps_guard_and_streaming(self):
        target=auth.BASE+'pluginfile.php/1/material.pdf?forcedownload=1'
        redirect=Response(303,location=target);binary=Response(url=target)
        transport=Transport([redirect,binary])
        self.assertIs(auth.request(transport,'/mod/resource/view.php?id=10',material_route=True,stream=True),binary)
        self.assertEqual([x[1] for x in transport.calls],[auth.BASE+'mod/resource/view.php?id=10',target])
        self.assertTrue(redirect.closed)
        self.assertTrue(all(call[2]['stream'] for call in transport.calls))

    def test_material_unsafe_redirect_rejected_before_destination(self):
        for dest in ['https://outside.invalid/file.pdf','/login/logout.php?sesskey=x','/user/edit.php',
                     '/mod/assign/view.php?id=10','/mod/resource/view.php?id=10&action=',
                     '/pluginfile.php/1/task.pdf?token=x']:
            transport=Transport([Response(303,location=dest)])
            with self.subTest(dest=dest),self.assertRaises(auth.AuthError):
                auth.request(transport,'/mod/resource/view.php?id=10',material_route=True,stream=True)
            self.assertEqual(len(transport.calls),1)

    def test_material_invalid_input_rejected_before_request(self):
        for url in ['/mod/resource/view.php?id=','/mod/resource/view.php?id=1&id=2',
                    '/mod/resource/view.php?id=1&broken','/mod/url/view.php?id=1',
                    'http://hebat.elearning.unair.ac.id/mod/resource/view.php?id=1','/pluginfile.php/%2e%2e/task.pdf']:
            transport=Transport([])
            with self.subTest(url=url),self.assertRaises(auth.AuthError):
                auth.request(transport,url,material_route=True,stream=True)
            self.assertEqual(transport.calls,[])

    def test_material_login_redirect_returns_none(self):
        redirect=Response(303,location='/login/index.php');transport=Transport([redirect])
        self.assertIsNone(auth.request(transport,'/mod/resource/view.php?id=10',material_route=True,stream=True))
        self.assertEqual(len(transport.calls),1);self.assertTrue(redirect.closed)

    def test_material_post_and_mixed_context_rejected(self):
        for kwargs in [{'method':'POST','data':{}},{'auth_route':True},{'attachment_route':True}]:
            transport=Transport([])
            with self.subTest(kwargs=kwargs),self.assertRaises(auth.AuthError):
                auth.request(transport,'/mod/resource/view.php?id=10',material_route=True,**kwargs)
            self.assertEqual(transport.calls,[])

    def test_material_redirect_loop_bounded(self):
        transport=Transport([Response(303,location='/mod/resource/view.php?id=10') for _ in range(6)])
        with self.assertRaisesRegex(auth.AuthError,'redirect_limit'):
            auth.request(transport,'/mod/resource/view.php?id=10',material_route=True,stream=True)
        self.assertEqual(len(transport.calls),6)

    def test_login_once_does_not_persist_until_caller_commits(self):
        login = Response(text='<input name="logintoken" value="fixture-token">', url=auth.BASE + 'login/index.php')
        done = Response(text='ok', url=auth.BASE + 'my/')
        with patch.object(auth, 'request', side_effect=[login, done]), patch.object(auth, 'authenticated', return_value=True):
            session = auth.login_once(self.credentials)
        self.assertEqual(auth.session_account_id(session), auth.account_id(self.credentials))
        self.assertEqual(self.store.writes, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
