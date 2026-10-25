import importlib.util
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('history_fixtures',Path(__file__).with_name('test_reader.py'))
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
r=fixtures.r;NOW=fixtures.NOW


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.auth=fixtures.FakeAuth(self.tmp.name)
        self.clock=patch.object(r,'stamp',return_value=NOW.isoformat());self.clock.start();self.addCleanup(self.clock.stop)
        times={'1':'Saturday, 24 October 2026, 10:22 PM',
               '2':'Wednesday, 21 October 2026, 8:49 PM',
               '3':'Tuesday, 1 September 2026, 8:00 AM',
               '4':'Monday, 19 October 2026, 11:52 PM',
               '8':'Monday, 1 June 2026, 7:00 AM'}
        for ident,modified in times.items():
            self.set_index(ident,'Submitted for grading')
            self.auth.pages[ident]=self.auth.pages[ident].replace('No submissions have been made yet','Submitted for grading')
            self.set_modified(ident,modified)

    def make(self,**kwargs):return r.Reader(self.auth,now=lambda:NOW,**kwargs)
    def set_index(self,ident,status):
        for key,rows in self.auth.rows.items():
            self.auth.rows[key]=[(i,day,status if i==ident else old) for i,day,old in rows]
    def set_modified(self,ident,modified):
        body=self.auth.pages[ident]
        body=re.sub(r'<tr><th>Last modified</th><td>.*?</td></tr>','',body)
        self.auth.pages[ident]=body.replace('</table>',f'<tr><th>Last modified</th><td>{modified}</td></tr></table>')
    def detail_calls(self):return [x for x in self.auth.calls if '/mod/assign/view.php' in x]
    def ids(self,data):return [x['url'].split('id=')[1] for x in data['recent_submissions']]

    def test_history_filters_last_modified_not_due_date(self):
        result=self.make().history()
        self.assertEqual(self.ids(result),['1','2','4'])
        self.assertEqual(result['submitted_candidates'],5)
        self.assertEqual(result['detail_pages_refetched'],5)
        self.assertEqual(result['semester'],'all')

    def test_repeated_history_has_zero_http_and_same_verification_time(self):
        first=self.make().history();self.auth.calls=[]
        second=self.make().history()
        self.assertEqual(self.auth.calls,[])
        self.assertEqual(second['detail_pages_refetched'],0)
        self.assertEqual(second['details_reused_count'],5)
        self.assertEqual(first['recent_submissions'][0]['detail_checked_at'],second['recent_submissions'][0]['detail_checked_at'])

    def test_changed_window_reuses_records(self):
        self.make().history();self.auth.calls=[]
        result=self.make().history(days=1)
        self.assertEqual(self.ids(result),['1']);self.assertEqual(self.auth.calls,[])

    def test_status_change_reads_only_new_submission(self):
        self.make().history();self.auth.calls=[]
        self.set_index('5','Submitted for grading')
        self.auth.pages['5']=self.auth.pages['5'].replace('No submissions have been made yet','Submitted for grading')
        self.set_modified('5','Sunday, 25 October 2026, 6:55 AM')
        result=self.make().history(recheck_index=True)
        self.assertIn('5',self.ids(result))
        self.assertEqual(self.detail_calls(),['/mod/assign/view.php?id=5'])
        self.assertEqual(result['detail_pages_refetched'],1)

    def test_same_status_revision_targeted_refresh_only(self):
        self.make().history();self.auth.calls=[]
        self.set_modified('3','Sunday, 25 October 2026, 6:55 AM')
        result=self.make().history(changed_url='/mod/assign/view.php?id=3')
        self.assertIn('3',self.ids(result))
        self.assertEqual(self.detail_calls(),['/mod/assign/view.php?id=3'])
        self.assertEqual([x for x in self.auth.calls if '/index.php?' in x],['/mod/assign/index.php?id=10'])

    def test_unexposed_revision_has_documented_periodic_bound(self):
        self.make().history();self.auth.calls=[]
        self.set_modified('3','Sunday, 25 October 2026, 6:55 AM')
        result=self.make().history(recheck_index=True)
        self.assertNotIn('3',self.ids(result))
        self.assertEqual(self.detail_calls(),[])
        self.assertEqual(result['history_refresh_policy']['older_detail_ttl_seconds'],3600)
        self.assertTrue(any('status sama' in note for note in result['coverage_notes']))

    def test_recent_entries_rechecked_after_five_minutes(self):
        self.make().history();self.auth.calls=[]
        epoch=r.time.time()
        with patch.object(r.time,'time',return_value=epoch+301):result=self.make().history()
        self.assertEqual(set(self.detail_calls()),{'/mod/assign/view.php?id=1','/mod/assign/view.php?id=2','/mod/assign/view.php?id=4'})
        self.assertEqual(result['details_reused_count'],2)

    def test_old_revision_detected_at_hourly_recheck(self):
        self.make().history();self.auth.calls=[]
        self.set_modified('3','Sunday, 25 October 2026, 6:55 AM')
        epoch=r.time.time()
        with patch.object(r.time,'time',return_value=epoch+3601):result=self.make().history()
        self.assertIn('3',self.ids(result))
        self.assertEqual(len(self.detail_calls()),5)

    def test_withdraw_and_resubmit_invalidates_previous_submission(self):
        self.make().history();self.auth.calls=[]
        self.set_index('1','Draft')
        withdrawn=self.make().history(recheck_index=True)
        self.assertNotIn('1',self.ids(withdrawn))
        self.set_index('1','Submitted for grading')
        self.set_modified('1','Sunday, 25 October 2026, 6:59 AM')
        self.auth.calls=[]
        result=self.make().history(recheck_index=True)
        self.assertEqual(self.ids(result)[0],'1')
        self.assertEqual(self.detail_calls(),['/mod/assign/view.php?id=1'])

    def test_explicit_fresh_rechecks_all_candidates(self):
        self.make().history();self.auth.calls=[]
        result=self.make(fresh=True).history()
        self.assertEqual(len(self.detail_calls()),5)
        self.assertEqual(result['detail_pages_refetched'],5)

    def test_bootstrap_existing_detail_cache_avoids_full_refetch(self):
        reader=self.make()
        for ident in ['1','2','3','4','8']:reader.detail('/mod/assign/view.php?id='+ident)
        self.auth.calls=[]
        result=self.make().history()
        self.assertEqual(self.detail_calls(),[])
        self.assertEqual(result['seeded_from_detail_cache'],5)
        self.assertEqual(self.ids(result),['1','2','4'])

    def test_failed_target_refresh_not_replaced_by_old_value(self):
        self.make().history();original=self.auth.request
        def fail(session,url):
            if '/view.php?id=1' in url:raise fixtures.AuthError('network_unavailable')
            return original(session,url)
        self.auth.request=fail
        result=self.make().history(changed_url='/mod/assign/view.php?id=1')
        self.assertNotIn('1',self.ids(result));self.assertFalse(result['complete']);self.assertTrue(result['errors'])
        self.auth.request=original;self.auth.calls=[]
        retried=self.make().history()
        self.assertIn('1',self.ids(retried));self.assertEqual(self.detail_calls(),['/mod/assign/view.php?id=1'])

    def test_unknown_modified_time_not_invented(self):
        self.set_modified('1','-')
        result=self.make().history()
        self.assertFalse(result['complete'])
        self.assertEqual(result['unknown_modified_time'][0]['url'].split('id=')[1],'1')

    def test_history_summary_paginates_without_network(self):
        self.make().history();self.auth.calls=[]
        result=r.compact_result(self.make().show('history'),limit=1,offset=1)
        self.assertEqual(result['recent_submissions'][0]['url'].split('id=')[1],'2')
        self.assertEqual(result['recent_submissions_total'],3)
        self.assertEqual(result['detail_pages_refetched'],0)
        self.assertEqual(result['source_run_metrics']['detail_pages_refetched'],5)
        self.assertEqual(self.auth.calls,[])

    def test_cache_lock_and_ledger_are_private(self):
        self.make().history()
        for p in Path(self.tmp.name).rglob('*'):
            if p.is_file():
                self.assertEqual(p.stat().st_mode&0o777,0o600)
                self.assertNotIn('fixture-private',p.read_text())

    def test_parallel_history_requests_do_not_duplicate_cold_detail_reads(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.make().history(),range(2)))
        self.assertEqual(len(self.detail_calls()),5)
        self.assertEqual(self.ids(results[0]),self.ids(results[1]))

    def test_detail_index_disagreement_is_reported(self):
        self.auth.pages['1']=self.auth.pages['1'].replace('Submitted for grading','Draft')
        result=self.make().history()
        self.assertNotIn('1',self.ids(result))
        self.assertFalse(result['complete'])
        self.assertTrue(any('berbeda' in message for message in result['warnings']))

    def test_external_changed_url_rejected_before_network(self):
        with self.assertRaises(ValueError):self.make().history(changed_url='https://evil.example/mod/assign/view.php?id=1')
        self.assertEqual(self.auth.calls,[])

    def test_invalid_window_rejected(self):
        for value in [0,-1,367,True]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.make().history(days=value)


if __name__=='__main__':unittest.main(verbosity=2)
