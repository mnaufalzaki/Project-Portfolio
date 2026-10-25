"""Isolated attachment transport and atomic-output behavior; no account access."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_reader as fixtures

r = fixtures.r
PDF = b'%PDF-1.7\nfixture academic attachment\n%%EOF\n'
URL = r.BASE + 'pluginfile.php/1/mod_assign/introattachment/0/question.pdf?forcedownload=1'


class BinaryResponse:
    def __init__(self, chunks=None, content_type='application/pdf', error_after=None, length=None):
        self.chunks = [PDF] if chunks is None else chunks
        self.headers = {'Content-Type': content_type}
        if length is not None:
            self.headers['Content-Length'] = str(length)
        self.error_after = error_after
        self.closed = False
        self.requested_chunk_size = None

    def iter_content(self, chunk_size):
        self.requested_chunk_size = chunk_size
        for index, chunk in enumerate(self.chunks):
            if index == self.error_after:
                raise OSError('synthetic interrupted stream')
            yield chunk

    def close(self):
        self.closed = True


class AttachmentAuth(fixtures.FakeAuth):
    """Route validator is a spy; URL policy itself is tested in test_auth.py."""
    def __init__(self, root):
        super().__init__(root)
        self.responses = [BinaryResponse()]
        self.validation_calls = []
        self.request_options = []

    def attachment_url(self, value):
        self.validation_calls.append(value)
        if value != URL:
            raise fixtures.AuthError('attachment_route_not_allowed')
        return value

    def request(self, session, url, **kwargs):
        with self.lock:
            self.calls.append(url)
            self.request_options.append(kwargs)
            response = self.responses.pop(0)
        if kwargs != {'attachment_route': True, 'stream': True}:
            raise AssertionError('Attachment must use guarded streaming transport')
        return response


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.auth = AttachmentAuth(self.root)
        self.output = self.root / 'question.pdf'

    def make(self):
        return r.Reader(self.auth, now=lambda: fixtures.NOW)

    def assert_clean_failure(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.attachment-*')))

    def test_forcedownload_preserves_binary_hash_and_private_mode(self):
        response = BinaryResponse([PDF[:8], b'', PDF[8:]], length=len(PDF))
        self.auth.responses = [response]
        result = self.make().attachment(URL, self.output)
        self.assertEqual(self.output.read_bytes(), PDF)
        self.assertEqual(result['sha256'], hashlib.sha256(PDF).hexdigest())
        self.assertEqual(result['bytes'], len(PDF))
        self.assertEqual(result['content_type'], 'application/pdf')
        self.assertEqual(result['local_path'], str(self.output))
        self.assertEqual(result['build_id'], r.BUILD_ID)
        self.assertEqual(result['checked_at'], fixtures.NOW.isoformat())
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.parent.stat().st_mode & 0o777, 0o700)
        self.assertTrue(response.closed)
        self.assertNotIn('fixture-private', json.dumps(result))
        self.assertFalse(list(self.root.glob('.attachment-*')))

    def test_existing_output_rejected_before_session_or_network(self):
        self.output.write_bytes(b'keep existing file')
        with self.assertRaisesRegex(ValueError, 'attachment_output_exists'):
            self.make().attachment(URL, self.output)
        self.assertEqual(self.output.read_bytes(), b'keep existing file')
        self.assertEqual(self.auth.calls, [])
        self.assertEqual(self.auth.ensures, 0)

    def test_existing_symlink_rejected_before_network(self):
        self.output.symlink_to(self.root / 'nonexistent-target')
        with self.assertRaisesRegex(ValueError, 'attachment_output_exists'):
            self.make().attachment(URL, self.output)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(self.auth.calls, [])

    def test_shared_parent_directory_rejected_before_network(self):
        shared = self.root / 'shared'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'attachment_directory_not_private'):
            self.make().attachment(URL, shared / 'file.pdf')
        self.assertEqual(self.auth.calls, [])
        self.assertEqual(self.auth.ensures, 0)

    def test_rejected_url_has_zero_page_or_session_access(self):
        with self.assertRaisesRegex(fixtures.AuthError, 'attachment_route_not_allowed'):
            self.make().attachment('https://outside.invalid/file.pdf', self.output)
        self.assertEqual(self.auth.validation_calls, ['https://outside.invalid/file.pdf'])
        self.assertEqual(self.auth.calls, [])
        self.assertEqual(self.auth.ensures, 0)
        self.assert_clean_failure()

    def test_wrong_session_owner_has_zero_download_access(self):
        self.auth.ensure_client = lambda **kwargs: (SimpleNamespace(hebat_account_id='wrong-owner'), False)
        with self.assertRaisesRegex(fixtures.AuthError, 'account|identity'):
            self.make().attachment(URL, self.output)
        self.assertEqual(self.auth.calls, [])
        self.assert_clean_failure()

    def test_interrupted_stream_never_publishes_partial_output(self):
        response = BinaryResponse([PDF[:8], PDF[8:]], error_after=1)
        self.auth.responses = [response]
        with self.assertRaisesRegex(fixtures.AuthError, 'network_unavailable'):
            self.make().attachment(URL, self.output)
        self.assertTrue(response.closed)
        self.assert_clean_failure()

    def test_content_length_mismatch_never_publishes_output(self):
        response = BinaryResponse(length=len(PDF) + 1)
        self.auth.responses = [response]
        with self.assertRaisesRegex(ValueError, 'attachment_length_mismatch'):
            self.make().attachment(URL, self.output)
        self.assertTrue(response.closed)
        self.assert_clean_failure()

    def test_empty_attachment_never_publishes_output(self):
        response = BinaryResponse([])
        self.auth.responses = [response]
        with self.assertRaisesRegex(ValueError, 'attachment_empty'):
            self.make().attachment(URL, self.output)
        self.assertTrue(response.closed)
        self.assert_clean_failure()

    def test_html_error_is_rejected_and_closed(self):
        response = BinaryResponse([b'<html>Access denied</html>'], 'text/html; charset=utf-8')
        self.auth.responses = [response]
        with self.assertRaisesRegex(ValueError, 'attachment_html_response'):
            self.make().attachment(URL, self.output)
        self.assertTrue(response.closed)
        self.assert_clean_failure()

    def test_login_form_split_across_chunks_recovers_once(self):
        expired = BinaryResponse([b'', b'<html><form><input name="username">',
                                  b'<input name="password"></form></html>'], 'text/html')
        restored = BinaryResponse()
        self.auth.responses = [expired, restored]
        self.make().attachment(URL, self.output)
        self.assertEqual(self.output.read_bytes(), PDF)
        self.assertEqual(self.auth.ensures, 2)
        self.assertEqual(len(self.auth.calls), 2)
        self.assertTrue(expired.closed)
        self.assertTrue(restored.closed)

    def test_rejected_login_after_recovery_stops_without_output(self):
        login = b'<html><input name="username"><input name="password"></html>'
        responses = [BinaryResponse([login], 'text/html'), BinaryResponse([login], 'text/html')]
        self.auth.responses = list(responses)
        with self.assertRaisesRegex(fixtures.AuthError, 'session_or_page_access_rejected'):
            self.make().attachment(URL, self.output)
        self.assertEqual(self.auth.ensures, 2)
        self.assertTrue(all(x.closed for x in responses))
        self.assert_clean_failure()

    def test_no_second_recovery_after_initial_operation_login(self):
        original = self.auth.ensure_client
        def already_renewed(**kwargs):
            session, _ = original(**kwargs)
            return session, True
        self.auth.ensure_client = already_renewed
        self.auth.responses = [None]
        with self.assertRaisesRegex(fixtures.AuthError, 'session_recovery_limit'):
            self.make().attachment(URL, self.output)
        self.assertEqual(self.auth.ensures, 1)
        self.assertEqual(len(self.auth.calls), 1)
        self.assert_clean_failure()

    def test_racing_writer_cannot_be_overwritten(self):
        original = r.os.link
        def race(source, target):
            self.output.write_bytes(b'another completed download')
            return original(source, target)
        with patch.object(r.os, 'link', side_effect=race):
            with self.assertRaises(FileExistsError):
                self.make().attachment(URL, self.output)
        self.assertEqual(self.output.read_bytes(), b'another completed download')
        self.assertFalse(list(self.root.glob('.attachment-*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
