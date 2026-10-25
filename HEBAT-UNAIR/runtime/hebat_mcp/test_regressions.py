"""Behavior regressions for account-bound reads, cache recovery, and scoped queries."""
from datetime import timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_reader as fixtures
import test_history as history_fixtures

r = fixtures.r
NOW = fixtures.NOW


class ReaderRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.auth = fixtures.FakeAuth(self.tmp.name)
        self.clock = patch.object(r, 'stamp', return_value=NOW.isoformat())
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def make(self, **kwargs):
        return r.Reader(self.auth, now=lambda: NOW, **kwargs)

    def test_fresh_detail_invalidates_priority_without_extra_http(self):
        first = self.make().priority()
        self.assertIn('Tugas 1', [e['title'] for e in first['upcoming']])
        self.auth.pages['1'] = fixtures.detail_html('1', status='Submitted for grading')
        self.make(fresh=True).detail('/mod/assign/view.php?id=1')
        historical = self.make().show()
        self.assertEqual(historical['checked_at'], first['checked_at'])
        self.assertIn('Tugas 1', [e['title'] for e in historical['upcoming']])
        self.auth.calls = []
        updated = self.make().priority()
        self.assertNotIn('Tugas 1', [e['title'] for e in updated['upcoming']])
        self.assertEqual(self.auth.calls, [])

    def test_newer_draft_detail_overrides_stale_submitted_index(self):
        self.auth.names = {'10': self.auth.names['10']}
        self.auth.rows = {'10': [('1', 26, 'Submitted for grading')]}
        self.auth.pages['1'] = fixtures.detail_html('1', status='Submitted for grading')
        first = self.make().priority()
        self.assertEqual(first['upcoming'], [])
        self.auth.pages['1'] = fixtures.detail_html('1', status='Draft')
        self.make(fresh=True).detail('/mod/assign/view.php?id=1')
        self.auth.calls = []
        result = self.make().priority()
        self.assertEqual([x['title'] for x in result['upcoming']], ['Tugas 1'])
        self.assertEqual(result['upcoming'][0]['detail']['status'], 'Draft')
        self.assertEqual(self.auth.calls, [])

    def test_scan_unknown_status_is_visible_and_not_complete(self):
        self.auth.names = {'10': self.auth.names['10']}
        self.auth.rows = {'10': [('1', 26, 'Novel unknown state')]}
        self.auth.pages['1'] = fixtures.detail_html('1', status='Novel unknown state')
        result = self.make().scan()
        self.assertEqual(len(result['non_submitted_or_uncertain']), 1)
        self.assertEqual(result['non_submitted_or_uncertain'][0]['detail']['status'], 'Novel unknown state')
        self.assertFalse(result['complete'])
        self.assertTrue(result['warnings'])

    def test_scan_excludes_fresh_submitted_detail_but_keeps_draft(self):
        result = self.make().scan(term='auto')
        entries = result['non_submitted_or_uncertain']
        self.assertNotIn('Tugas 4', [e['title'] for e in entries])
        self.assertIn('Tugas 7', [e['title'] for e in entries])
        self.assertFalse(any(r.submission_state(e.get('detail', {}).get('status')) == 'submitted' for e in entries))

    def test_scan_keeps_failed_detail_visible(self):
        self.auth.names = {'10':self.auth.names['10']}
        original = self.auth.request
        def request(session,url):
            if '/mod/assign/view.php?id=1' in url:
                raise fixtures.AuthError('network_unavailable')
            return original(session,url)
        self.auth.request = request
        result = self.make().scan()
        self.assertFalse(result['complete'])
        self.assertTrue(any(e.get('error') == 'network_unavailable' for e in result['non_submitted_or_uncertain']))

    def test_group_representative_phrases_from_real_instructions(self):
        for text in ['Pengumpulan tugas tiap kelompok hanya diwakilkan oleh satu orang saja!',
                     'Pengumpulan cukup diwakili ketua tim.',
                     'Pengumpulan cukup dilakukan oleh ketua tim.']:
            with self.subTest(text=text):
                data=r.parse_detail(r.DOM(fixtures.detail_html('1',instructions=text)).root,'/mod/assign/view.php?id=1')
                self.assertEqual(data['submission_rule'],'representative')

    def test_group_and_individual_conflict_remains_uncertain(self):
        text='Pengumpulan cukup diwakili ketua tim. Setiap mahasiswa mengirimkan tugas sendiri.'
        data=r.parse_detail(r.DOM(fixtures.detail_html('1',instructions=text)).root,'/mod/assign/view.php?id=1')
        self.assertEqual(data['submission_rule'],'uncertain')

    def test_leader_mention_or_prohibition_does_not_imply_representative(self):
        for text in ['Desain dibuat oleh ketua tim. Setiap mahasiswa mengumpulkan sendiri.',
                     'Pengumpulan tidak boleh diwakili ketua tim.']:
            with self.subTest(text=text):
                data=r.parse_detail(r.DOM(fixtures.detail_html('1',instructions=text)).root,'/mod/assign/view.php?id=1')
                self.assertNotEqual(data['submission_rule'],'representative')

    def test_truncated_course_candidates_keep_unknown_and_exclude_incompatible_prefix(self):
        names=['2026Ganjil - MNW409 - Kew...', '2026Ganjil - SII213 - Inovasi Sistem ...',
               '2026Ganjil - ...', '2026Ganjil - MNW...']
        courses=[{'id':str(i),'name':name} for i,name in enumerate(names)]
        self.assertEqual([c['id'] for c in r.course_candidates(courses,'KBSI')],['0','2','3'])
        self.assertEqual([c['id'] for c in r.course_candidates(courses,'1')],['1'])
        self.assertEqual(r.course_candidates(courses,'generic title'),courses)

    def test_known_full_course_query_reads_only_its_index(self):
        result = self.make().priority(course_query='avd prak i1')
        self.assertEqual(result['course_count'], 1)
        indices = [url for url in self.auth.calls if '/index.php?' in url]
        self.assertEqual(indices, ['/mod/assign/index.php?id=10'])

    def test_corrupt_snapshot_items_and_dependencies_are_rejected(self):
        reader = self.make()
        result = reader.priority()
        invalid = dict(result, administrative=[None])
        reader.cache.write('last-priority', invalid)
        self.assertIsNone(reader.cache.read('last-priority'))
        invalid = dict(result, source_dependencies={'../../unrelated': None})
        reader.cache.write('last-priority', invalid)
        self.assertIsNone(reader.cache.read('last-priority'))
        reader.cache.write('last-scan', {'checked_at': NOW.isoformat(), 'errors': [], 'warnings': [],
                                         'non_submitted_or_uncertain': [None]})
        self.assertIsNone(reader.cache.read('last-scan'))

    def test_exact_course_id_reads_only_its_index(self):
        self.make().priority(course_query='11')
        indices = [url for url in self.auth.calls if '/index.php?' in url]
        self.assertEqual(indices, ['/mod/assign/index.php?id=11'])

    def test_resolved_nonmatching_short_names_survive_query_change(self):
        original = self.auth.request
        def shortened(session, url):
            response = original(session, url)
            if '/my/' in url:
                for name in self.auth.names.values():
                    if name.startswith('2026Ganjil'):
                        response.text = response.text.replace(name, '2026Ganjil - Analisis...')
            return response
        self.auth.request = shortened
        self.make().priority(course_query='avd prak i1')
        self.auth.calls = []
        epoch = r.time.time()
        with patch.object(r.time, 'time', return_value=epoch + 121):
            self.make().priority(course_query='avd teo i1')
        indices = [url for url in self.auth.calls if '/index.php?' in url]
        self.assertEqual(indices, ['/mod/assign/index.php?id=11'])

    def test_concurrent_course_refresh_cannot_validate_old_scope_snapshot(self):
        self.auth.names = {'10': self.auth.names['10']}
        self.auth.rows = {'10': [('1', 26, 'No submission')]}
        original = self.auth.request
        refreshed = False
        def concurrent_refresh(session, url):
            nonlocal refreshed
            if '/index.php?id=10' in url and not refreshed:
                refreshed = True
                cache = self.make().cache
                prior = cache.read('courses', 600)
                self.auth.names['20'] = '2027Ganjil - Kelas baru - I1'
                self.auth.rows['20'] = [('20', 26, 'No submission')]
                self.auth.pages['20'] = fixtures.detail_html('20').replace('2026', '2027')
                added = {'id': '20', 'name': self.auth.names['20'], 'url': r.BASE + 'course/view.php?id=20'}
                cache.write('courses', [*prior['data'], added], prior['fetched_at'])
            response = original(session, url)
            if '/my/' in url:
                response.text = response.text.replace(self.auth.names['10'], '2026Ganjil - Analisis...')
            return response
        self.auth.request = concurrent_refresh
        first = self.make().priority()
        self.assertEqual(first['semester'], '2026Ganjil')
        second = self.make().priority()
        self.assertEqual(second['semester'], '2027Ganjil')
        self.assertEqual([x['title'] for x in second['upcoming']], ['Tugas 20'])

    def test_extension_beyond_first_batch_does_not_hide_nearer_task(self):
        self.auth.names = {'10': self.auth.names['10']}
        self.auth.rows = {'10': []}
        for number, day in enumerate(range(26, 32), 21):
            ident = str(number)
            self.auth.rows['10'].append((ident, day, 'No submission'))
            extension = f'Tuesday, {number - 20} December 2026, 8:00 AM' if number < 26 else None
            self.auth.pages[ident] = fixtures.detail_html(ident, day, extension=extension)
        result = self.make().priority(limit=5)
        self.assertEqual(result['upcoming'][0]['title'], 'Tugas 26')
        self.assertEqual(result['upcoming'][0]['detail']['due_iso'], '2026-10-31T23:59:00+07:00')

    def test_recovery_budget_is_shared_by_entire_reader_operation(self):
        original = self.auth.request
        attempts = {}
        def expired_once_per_page(session, url):
            attempts[url] = attempts.get(url, 0) + 1
            return None if attempts[url] == 1 else original(session, url)
        self.auth.request = expired_once_per_page
        reader = self.make()
        reader.get('/mod/assign/view.php?id=1')
        self.assertEqual(self.auth.ensures, 2)
        with self.assertRaises(fixtures.AuthError):
            reader.get('/mod/assign/view.php?id=2')
        self.assertEqual(self.auth.ensures, 2)

    def test_wrong_session_owner_is_rejected_before_page_request(self):
        self.auth.ensure_client = lambda **kwargs: (SimpleNamespace(hebat_account_id='different-owner'), False)
        with self.assertRaisesRegex(fixtures.AuthError, 'account|identity'):
            self.make().detail('/mod/assign/view.php?id=1')
        self.assertEqual(self.auth.calls, [])

    def test_malformed_cache_wrappers_rebuild_instead_of_crashing(self):
        reader = self.make()
        reader.detail('/mod/assign/view.php?id=1')
        path = reader.cache.folder / 'detail-1.json'
        original = json.loads(path.read_text())
        variants = [None, [], 'not-a-wrapper', {}, {**original, 'data': []},
                    {**original, 'data': {}}, {**original, 'account_id': 'another-account'},
                    {**original, 'schema_version': r.CACHE_SCHEMA - 1}]
        for invalid in variants:
            with self.subTest(invalid=invalid):
                path.write_text(json.dumps(invalid))
                self.auth.calls = []
                data = self.make().detail('/mod/assign/view.php?id=1')
                self.assertEqual(data['status'], 'No submissions have been made yet')
                self.assertEqual(self.auth.calls, ['/mod/assign/view.php?id=1'])

    def test_nonfinite_boolean_and_future_cache_timestamps_are_not_reused(self):
        reader = self.make()
        reader.detail('/mod/assign/view.php?id=1')
        path = reader.cache.folder / 'detail-1.json'
        original = json.loads(path.read_text())
        for invalid in [True, False, float('nan'), float('inf'), -float('inf'), r.time.time() + 60]:
            with self.subTest(timestamp=invalid):
                path.write_text(json.dumps({**original, 'fetched_at': invalid}))
                self.auth.calls = []
                self.make().detail('/mod/assign/view.php?id=1')
                self.assertEqual(self.auth.calls, ['/mod/assign/view.php?id=1'])

    def test_truncated_cache_rebuild_failure_is_visible(self):
        reader = self.make()
        reader.detail('/mod/assign/view.php?id=1')
        (reader.cache.folder / 'detail-1.json').write_text('{')
        self.auth.request = lambda *args: (_ for _ in ()).throw(fixtures.AuthError('network_unavailable'))
        with self.assertRaisesRegex(fixtures.AuthError, 'network_unavailable'):
            self.make().detail('/mod/assign/view.php?id=1')

    def test_backward_system_clock_does_not_extend_cache_lifetime(self):
        self.make().detail('/mod/assign/view.php?id=1')
        self.auth.calls = []
        epoch = r.time.time()
        with patch.object(r.time, 'time', return_value=epoch - 60):
            self.make().detail('/mod/assign/view.php?id=1')
        self.assertEqual(self.auth.calls, ['/mod/assign/view.php?id=1'])


class ParseRegressions(unittest.TestCase):
    def test_am_pm_hour_bounds_are_validated_before_conversion(self):
        for value in ['0:00 AM', '0:00 PM', '13:00 AM', '25:00 AM', '25:00 PM']:
            with self.subTest(value=value):
                self.assertIsNone(r.parse_date('Sunday, 25 October 2026, ' + value))
        self.assertEqual(r.parse_date('Sunday, 25 October 2026, 12:00 AM').hour, 0)
        self.assertEqual(r.parse_date('Sunday, 25 October 2026, 12:00 PM').hour, 12)
        self.assertEqual(r.parse_date('Sunday, 25 October 2026, 23:59').hour, 23)

    def test_attachment_origin_distinguishes_question_submission_and_feedback(self):
        links = {
            'instruction': r.BASE + 'pluginfile.php/1/mod_assign/introattachment/0/question.pdf?forcedownload=1',
            'submission': r.BASE + 'pluginfile.php/1/assignsubmission_file/submission_files/0/my-answer.pdf',
            'feedback': r.BASE + 'pluginfile.php/1/assignfeedback_file/feedback_files/0/review.pdf',
            'unknown': r.BASE + 'pluginfile.php/1/local_misc/other/0/reference.pdf',
        }
        body = fixtures.detail_html('1', instructions=f'<a href="{links["instruction"]}">Question</a>')
        extra = ''.join(f'<tr><th>{kind}</th><td><a href="{url}">{kind}</a></td></tr>'
                        for kind, url in links.items() if kind != 'instruction')
        body = body.replace('</table>', extra + '</table>')
        result = r.parse_detail(r.DOM(body).root, '/mod/assign/view.php?id=1')
        self.assertEqual({x['source']: x['url'] for x in result['attachment_links']}, links)

    def test_midnight_year_boundary_keeps_jakarta_and_explicit_year(self):
        before = r.parse_date('Thursday, 31 December 2026, 11:59 PM')
        after = r.parse_date('Friday, 1 January 2027, 12:00 AM')
        self.assertEqual(after - before, timedelta(minutes=1))
        self.assertEqual(after.utcoffset(), timedelta(hours=7))


class HistoryRegressions(unittest.TestCase):
    def setUp(self):
        self.case = history_fixtures.HistoryTests('test_history_filters_last_modified_not_due_date')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.r = history_fixtures.r
        self.auth = self.case.auth

    def test_unknown_index_status_is_verified_through_detail(self):
        self.case.set_index('1', 'Novel submitted state')
        result = self.case.make().history()
        self.assertIn('/mod/assign/view.php?id=1', self.case.detail_calls())
        self.assertIn('1', self.case.ids(result))

    def test_unknown_detail_status_remains_visible_as_uncertainty(self):
        self.case.set_index('1', 'Novel submitted state')
        self.auth.pages['1'] = self.auth.pages['1'].replace('Submitted for grading', 'Novel submitted state')
        result = self.case.make().history()
        self.assertFalse(result['complete'])
        self.assertTrue(any(x['url'].endswith('id=1') for x in result['uncertain_status']))

    def test_future_modified_time_has_no_silent_five_minute_gap(self):
        for delta, now_shift in [(1, 59), (5, 0), (6, 0)]:
            with self.subTest(minutes=delta, now_shift=now_shift):
                modified = NOW + timedelta(minutes=delta)
                self.case.set_modified('1', modified.strftime('%A, %d %B %Y, %I:%M %p'))
                now = NOW + timedelta(seconds=now_shift)
                result = self.r.Reader(self.auth, now=lambda: now).history(changed_url='/mod/assign/view.php?id=1')
                self.assertNotIn('1', self.case.ids(result))
                self.assertTrue(any(x['url'].endswith('id=1') for x in result['unknown_modified_time']))
                self.assertFalse(result['complete'])

    def test_exact_now_and_seven_day_cutoff_are_inclusive(self):
        for modified in [NOW, NOW - timedelta(days=7)]:
            with self.subTest(modified=modified.isoformat()):
                self.case.set_modified('1', modified.strftime('%A, %d %B %Y, %I:%M %p'))
                result = self.case.make().history(changed_url='/mod/assign/view.php?id=1')
                self.assertIn('1', self.case.ids(result))
        self.case.set_modified('1', (NOW - timedelta(days=7, minutes=1)).strftime('%A, %d %B %Y, %I:%M %p'))
        result = self.case.make().history(changed_url='/mod/assign/view.php?id=1')
        self.assertNotIn('1', self.case.ids(result))

    def test_checked_at_is_oldest_source_not_only_refreshed_index(self):
        earlier = (NOW - timedelta(seconds=60)).isoformat()
        with patch.object(self.r, 'stamp', return_value=earlier):
            self.case.make().history()
        result = self.case.make().history(recheck_index=True)
        self.assertEqual(result['index_checked_at'], NOW.isoformat())
        self.assertEqual(result['oldest_detail_checked_at'], earlier)
        self.assertEqual(result['checked_at'], earlier)

    def test_malformed_ledger_records_are_rebuilt(self):
        reader = self.case.make()
        reader.history()
        path = reader.cache.folder / 'history-ledger.json'
        wrapper = json.loads(path.read_text())
        for invalid in [[], None, {'version': 1, 'records': [], 'observed': {}},
                        {'version': 1, 'records': {}, 'observed': []}]:
            with self.subTest(data=invalid):
                path.write_text(json.dumps({**wrapper, 'data': invalid}))
                result = self.case.make().history()
                self.assertEqual(self.case.ids(result), ['1', '2', '4'])

    def test_history_refresh_updates_priority_without_additional_http(self):
        self.case.make().priority()
        self.case.set_index('5', 'Submitted for grading')
        self.auth.pages['5'] = self.auth.pages['5'].replace('No submissions have been made yet', 'Submitted for grading')
        self.case.set_modified('5', 'Sunday, 25 October 2026, 6:59 AM')
        self.case.make().history(recheck_index=True)
        self.auth.calls = []
        result = self.case.make().priority()
        self.assertNotIn('Tugas 5', [e['title'] for e in result['upcoming']])
        self.assertEqual(self.auth.calls, [])

    def test_newer_canonical_draft_replaces_cached_history_submission(self):
        initial = self.case.make().history()
        self.assertIn('1', self.case.ids(initial))
        self.auth.pages['1'] = self.auth.pages['1'].replace('Submitted for grading', 'Draft')
        self.case.make(fresh=True).detail('/mod/assign/view.php?id=1')
        self.auth.calls = []
        result = self.case.make().history()
        self.assertNotIn('1', self.case.ids(result))
        self.assertEqual(self.auth.calls, [])

    def test_newer_canonical_revision_replaces_cached_history_modified_time(self):
        self.case.make().history()
        self.case.set_modified('3', 'Sunday, 25 October 2026, 6:59 AM')
        self.case.make(fresh=True).detail('/mod/assign/view.php?id=3')
        self.auth.calls = []
        result = self.case.make().history()
        self.assertEqual(self.case.ids(result)[0], '3')
        self.assertEqual(self.auth.calls, [])


class ProcessCacheRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.auth = fixtures.FakeAuth(self.root)

    def run_child(self, code, *args):
        return subprocess.Popen([sys.executable, '-c', code, str(Path(__file__).parent), str(fixtures.reader_path),
                                 str(self.root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def wait_for(self, path, process, timeout=10):
        end = time.monotonic() + timeout
        while not path.exists():
            if process.poll() is not None:
                out, error = process.communicate()
                self.fail(f'Child exited before signal: {process.returncode}: {out} {error}')
            if time.monotonic() >= end:
                process.kill()
                process.communicate()
                self.fail('Timed out waiting for isolated cache worker')
            time.sleep(.01)

    def test_two_process_history_queries_share_cold_read(self):
        code = '''
import json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);os.environ['HEBAT_READER_PATH']=sys.argv[2]
import test_history as h
root=Path(sys.argv[3]);case=h.HistoryTests('test_history_filters_last_modified_not_due_date');case.setUp()
try:
 case.auth.ROOT=root
 original=case.auth.request
 def request(session,url):
  with (root/'calls.log').open('a') as stream:stream.write(url+'\\n')
  return original(session,url)
 case.auth.request=request
 while not (root/'start').exists():time.sleep(.01)
 result=case.make().history()
 print(json.dumps({'recent':[x['url'] for x in result['recent_submissions']],'complete':result['complete']}))
finally:case.doCleanups()
'''
        processes = [self.run_child(code) for _ in range(2)]
        try:
            (self.root / 'start').touch()
            results = []
            for process in processes:
                out, error = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, error)
                results.append(json.loads(out))
            self.assertEqual(results[0], results[1])
            self.assertTrue(results[0]['complete'])
            calls = (self.root / 'calls.log').read_text().splitlines()
            self.assertEqual(sum('/mod/assign/view.php?' in x for x in calls), 5)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_process_termination_preserves_old_or_new_complete_snapshot(self):
        code = '''
import os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1]);os.environ['HEBAT_READER_PATH']=sys.argv[2]
import test_reader as f
root=Path(sys.argv[3]);mode=sys.argv[4];reader=f.r.Reader(f.FakeAuth(root));cache=reader.cache
old=cache.read('detail-1')['data'];old['status']='Draft'
original=f.r.os.replace
def intercepted(source,destination):
 if mode=='after':original(source,destination)
 (root/'ready').touch()
 while True:time.sleep(.1)
f.r.os.replace=intercepted
cache.write('detail-1',old)
'''
        reader = r.Reader(self.auth)
        for mode, expected in [('before', 'No submissions have been made yet'), ('after', 'Draft')]:
            with self.subTest(mode=mode):
                reader.detail('/mod/assign/view.php?id=1', force=True)
                (self.root / 'ready').unlink(missing_ok=True)
                process = self.run_child(code, mode)
                try:
                    self.wait_for(self.root / 'ready', process)
                    process.terminate()
                    process.communicate(timeout=10)
                    value = reader.cache.read('detail-1')
                    self.assertIsNotNone(value)
                    self.assertEqual(value['data']['status'], expected)
                    self.assertEqual((reader.cache.folder / 'detail-1.json').stat().st_mode & 0o777, 0o600)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()


if __name__ == '__main__':
    unittest.main(verbosity=2)
