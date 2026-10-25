import importlib.util
import hashlib
import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
from datetime import datetime

reader_path = Path(os.environ.get('HEBAT_READER_PATH', Path(__file__).with_name('reader.py')))
spec = importlib.util.spec_from_file_location('reader_under_test', reader_path)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
NOW = datetime(2026,10,25,7,tzinfo=r.ZONE)


class AuthError(RuntimeError):
    def __init__(self,code):self.code=code;super().__init__(code)


def detail_html(ident, day=26, status='No submissions have been made yet', instructions='Kerjakan tugas.', extension=None):
    due=f'Monday, {day} October 2026, 11:59 PM' if day else ''
    ext=f'<tr><th>Extension due date</th><td>{extension}</td></tr>' if extension else ''
    return f'''<title>Tugas {ident} | HEBAT</title><nav>PRIVATE PROFILE MUST NOT APPEAR</nav>
      <div role="main">Completion requirements Due: {due}<div id="intro">{instructions}</div>
      <table><tr><th>Submission status</th><td>{status}</td></tr>
      <tr><th>Grading status</th><td>Not graded</td></tr>{ext}
      <tr><th>Submission comments</th><td>PRIVATE COMMENT UI</td></tr></table></div>'''


class FakeAuth:
    AuthError=AuthError
    def __init__(self,root):
        self.ROOT=Path(root)
        self.STORE=SimpleNamespace(read=lambda key:{'username':'fixture-private-id','password':'fixture-private-secret'} if key=='credentials' else None)
        self.calls=[];self.ensures=0;self.lock=threading.Lock()
        self.names={'10':'2026Ganjil - Analisis dan Visualisasi Data (praktikum) - I1',
                    '11':'2026Ganjil - Analisis dan Visualisasi Data - I1',
                    '12':'2026Ganjil - Analisis dan Visualisasi Data (praktikum) - I2',
                    '9':'2025Genap - Kelas lama - I1'}
        self.rows={'10':[('1',26,'No submission'),('2',27,'No submission'),('3',24,'No submission')],
                   '11':[('4',26,'No submission'),('5',28,'No submission')],
                   '12':[('6',None,'No submission'),('7',29,'Draft')],
                   '9':[('8',26,'No submission')]}
        self.pages={'1':detail_html('1'), '2':detail_html('2',27),
                    '3':detail_html('3',24,extension='Tuesday, 27 October 2026, 8:00 AM'),
                    '4':detail_html('4',26,status='Submitted for grading'),
                    '5':detail_html('5',28,instructions='Cukup perwakilan kelompok yang mengunggah.'),
                    '6':detail_html('6',None), '7':detail_html('7',29,status='Draft'),
                    '8':detail_html('8')}
    @staticmethod
    def account_id(credentials):
        return hashlib.sha256(('hebat:'+credentials['username']).encode()).hexdigest()[:24] if credentials else None
    @staticmethod
    def session_account_id(session):return getattr(session,'hebat_account_id',None)
    def ensure_client(self,force=False,expected_account_id=None):
        with self.lock:self.ensures+=1
        owner=self.account_id(self.STORE.read('credentials'))
        if expected_account_id is not None and owner!=expected_account_id:raise AuthError('account_identity_changed')
        return SimpleNamespace(hebat_account_id=owner),False
    def serialize(self,session):return {'version':2,'account_id':self.session_account_id(session),'cookies':[]}
    def session_from(self,bundle):return SimpleNamespace(hebat_account_id=bundle.get('account_id'))
    def request(self,session,url):
        p=urlparse(url)
        with self.lock:self.calls.append(p.path+'?'+p.query)
        if p.path=='/my/':
            body='<select name="course">'+''.join(f'<option value="{k}">{v}</option>' for k,v in self.names.items())+'</select>'
        elif p.path=='/mod/assign/index.php':
            ident=parse_qs(p.query)['id'][0]
            rows=''.join(f'<tr><td><a href="/mod/assign/view.php?id={key}">Tugas {key}</a></td><td>{"Monday, "+str(day)+" October, 11:59 PM" if day else "-"}</td><td>{status}</td></tr>' for key,day,status in self.rows[ident])
            body=f'<title>Course activities: {self.names[ident]} | HEBAT</title><table>{rows}</table>'
        else:
            body=self.pages[parse_qs(p.query)['id'][0]]
        return SimpleNamespace(text=body)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.auth=FakeAuth(self.tmp.name)
        self.clock=patch.object(r,'stamp',return_value=NOW.isoformat());self.clock.start();self.addCleanup(self.clock.stop)
    def make(self,**kwargs):return r.Reader(self.auth,now=lambda:NOW,**kwargs)
    def test_priority_uses_latest_semester_and_verified_dates(self):
        result=self.make().priority()
        self.assertEqual(result['semester'],'2026Ganjil')
        self.assertEqual(result['course_count'],3)
        self.assertEqual([e['title'] for e in result['upcoming']],['Tugas 1','Tugas 3','Tugas 2','Tugas 5','Tugas 7'])
        self.assertFalse(any('id=9' in x for x in self.auth.calls))
    def test_submitted_ungraded_excluded_and_draft_retained(self):
        result=self.make().priority()
        self.assertNotIn('Tugas 4',[e['title'] for e in result['upcoming']])
        self.assertIn('Tugas 7',[e['title'] for e in result['upcoming']])
    def test_unknown_date_never_invented(self):
        result=self.make().priority()
        entry=next(e for e in result['uncertain'] if e['title']=='Tugas 6')
        self.assertIsNone(entry['detail']['due_iso'])
    def test_repeat_priority_has_zero_network_and_original_timestamp(self):
        first=self.make().priority();before=len(self.auth.calls)
        with patch.object(r.Reader,'indices',side_effect=AssertionError('A cached priority must not rebuild indices')):
            second=self.make().priority()
        self.assertEqual(len(self.auth.calls),before)
        self.assertTrue(second['from_cache'])
        self.assertEqual(second['checked_at'],first['checked_at'])
    def test_fresh_bypasses_snapshot_indices_and_details(self):
        self.make().priority();before=len(self.auth.calls)
        self.auth.pages['1']=detail_html('1',status='Submitted for grading')
        result=self.make(fresh=True).priority()
        self.assertGreater(len(self.auth.calls),before)
        self.assertNotIn('Tugas 1',[e['title'] for e in result['upcoming']])
    def test_detail_followup_uses_cache_without_relogin(self):
        self.make().priority();before=len(self.auth.calls);ensures=self.auth.ensures
        detail=self.make().detail('/mod/assign/view.php?id=1')
        self.assertEqual(len(self.auth.calls),before)
        self.assertEqual(self.auth.ensures,ensures)
        self.assertIn('2026',detail['due_full'])
    def test_scan_reads_all_semesters_when_explicit(self):
        result=self.make().scan()
        self.assertEqual(result['course_count'],4)
        self.assertTrue(any('id=9' in x for x in self.auth.calls))
    def test_show_does_not_fetch_or_change_timestamp(self):
        first=self.make().priority();before=len(self.auth.calls)
        result=self.make().show()
        self.assertEqual(len(self.auth.calls),before)
        self.assertEqual(result['checked_at'],first['checked_at'])
    def test_class_parallel_filter_is_exact(self):
        result=self.make().priority(course_query='avd prak i1')
        self.assertEqual(result['course_count'],1)
        self.assertTrue(all('I1' in e['course'] and 'praktikum' in e['course'] for e in result['upcoming']))
    def test_theory_filter_does_not_merge_practical(self):
        result=self.make().priority(course_query='avd teo i1')
        self.assertEqual(result['course_count'],1)
        self.assertTrue(all('praktikum' not in e['course'] for e in result['upcoming']))
    def test_one_auth_check_per_operation_not_per_page(self):
        result=self.make().priority()
        self.assertGreater(result['pages_read_this_run'],3)
        self.assertEqual(self.auth.ensures,1)
    def test_partial_index_failure_not_claimed_complete(self):
        original=self.auth.request
        def request(session,url):
            if '/index.php?id=11' in url:raise AuthError('network_unavailable')
            return original(session,url)
        self.auth.request=request
        result=self.make().priority()
        self.assertFalse(result['index_complete']);self.assertFalse(result['complete'])
        self.assertEqual(result['errors'][0]['course_id'],'11')
    def test_retry_partial_result_reuses_successful_indices(self):
        original=self.auth.request
        def failing(session,url):
            if '/index.php?id=11' in url:raise AuthError('network_unavailable')
            return original(session,url)
        self.auth.request=failing
        first=self.make().priority();self.assertTrue(first['errors'])
        self.auth.request=original;self.auth.calls=[]
        second=self.make().priority()
        self.assertFalse(second['errors'])
        index_calls=[x for x in self.auth.calls if '/index.php?' in x]
        self.assertEqual(index_calls,['/mod/assign/index.php?id=11'])
    def test_group_status_caveat_present(self):
        result=r.compact_result(self.make().priority())
        group=next(e for e in result['upcoming'] if e['title']=='Tugas 5')
        self.assertEqual(group['detail']['submission_rule'],'representative')
        self.assertIn('belum membuktikan',group['detail']['note'])
    def test_permission_letter_not_prioritized_as_coursework(self):
        self.auth.rows['10'].append(('99',30,'No submission'))
        self.auth.pages['99']=detail_html('99',30)
        original=self.auth.request
        def request(session,url):
            response=original(session,url)
            if '/index.php' in url:response.text=response.text.replace('Tugas 99','SURAT IJIN')
            return response
        self.auth.request=request
        result=self.make().priority()
        self.assertEqual(result['administrative'][0]['title'],'SURAT IJIN')
        self.assertNotIn('SURAT IJIN',[e['title'] for e in result['upcoming']])
        self.assertFalse(any('/view.php?id=99' in x for x in self.auth.calls))
    def test_cache_private_and_never_contains_credentials(self):
        self.make().priority()
        for file in Path(self.tmp.name).rglob('*.json'):
            self.assertEqual(file.stat().st_mode&0o777,0o600)
            self.assertNotIn('fixture-private',file.read_text())
            self.assertEqual(file.parent.stat().st_mode&0o777,0o700)
    def test_cache_bound_to_user(self):
        self.make().priority()
        self.auth.STORE=SimpleNamespace(read=lambda key:{'username':'another-fixture','password':'another-secret'})
        with self.assertRaisesRegex(ValueError,'no_saved_result'):self.make().show()
    def test_expired_cache_refetches(self):
        self.make().priority();before=len(self.auth.calls)
        original=r.time.time
        with patch.object(r.time,'time',return_value=original()+700):self.make().priority()
        self.assertGreater(len(self.auth.calls),before)
    def test_expiry_during_read_recovered_once(self):
        original=self.auth.request;attempts=[]
        def request(session,url):
            attempts.append(url)
            return None if len(attempts)==1 else original(session,url)
        self.auth.request=request
        data=self.make().detail('/mod/assign/view.php?id=1')
        self.assertIsNotNone(data['status']);self.assertEqual(len(attempts),2);self.assertEqual(self.auth.ensures,2)
    def test_rejected_after_recovery_stops(self):
        self.auth.request=lambda *args:None
        with self.assertRaisesRegex(AuthError,'session_or_page_access_rejected'):self.make().detail('/mod/assign/view.php?id=1')
        self.assertEqual(self.auth.ensures,2)
    def test_compact_output_is_bounded_and_pageable(self):
        data={'non_submitted_or_uncertain':[{'title':str(i),'detail':{'instructions':'x'*10000}} for i in range(80)]}
        output=r.compact_result(data,limit=5,offset=5)
        self.assertEqual([e['title'] for e in output['non_submitted_or_uncertain']],list(map(str,range(5,10))))
        self.assertTrue(output['non_submitted_or_uncertain_more'])
        self.assertLess(len(json.dumps(output)),5000)
    def test_empty_scope_errors_instead_of_empty_success(self):
        with self.assertRaisesRegex(ValueError,'no_matching_course'):self.make().priority(course_query='no such class')


class ParseTests(unittest.TestCase):
    def test_attachment_accepts_moodle_forcedownload(self):
        for query in ['', '?forcedownload=0', '?forcedownload=1']:
            url=r.BASE+'pluginfile.php/430004/mod_assign/introattachment/0/Tugas%202.pdf'+query
            with self.subTest(query=query):
                data=r.parse_detail(r.DOM(detail_html('1',instructions=f'<a href="{url}">Tugas 2 PDF</a>')).root,'/mod/assign/view.php?id=1')
                self.assertEqual(data['attachment_links'],[{'name':'Tugas 2 PDF','url':url,'source':'instruction'}])
    def test_attachment_removes_fragment(self):
        url=r.BASE+'pluginfile.php/1/task.pdf?forcedownload=1'
        data=r.parse_detail(r.DOM(detail_html('1',instructions=f'<a href="{url}#page=2">PDF</a>')).root,'/mod/assign/view.php?id=1')
        self.assertEqual(data['attachment_links'][0]['url'],url)
    def test_attachment_rejects_unsafe_or_malformed_links(self):
        base=r.BASE+'pluginfile.php/1/task.pdf'
        urls=[base+'?sesskey=secret',base+'?token=secret',base+'?forcedownload=',base+'?forcedownload=2',base+'?forcedownload=1&forcedownload=1',base+'?forcedownload=1&sesskey=secret',base+'?forcedownload=1&broken',base.replace('https:','http:'),base.replace('hebat.elearning.unair.ac.id','evil.example'),r.BASE+'login/logout.php?forcedownload=1']
        for url in urls:
            with self.subTest(url=url):
                data=r.parse_detail(r.DOM(detail_html('1',instructions=f'<a href="{url}">PDF</a>')).root,'/mod/assign/view.php?id=1')
                self.assertEqual(data['attachment_links'],[])
    def test_moodle_header_outside_nested_role_main(self):
        html='<nav>PRIVATE PROFILE</nav><div id="region-main">Due: Tuesday, 27 October 2026, 9:00 AM<div id="intro">Rincian tugas kelompok.</div><div role="main"><table><tr><th>Submission status</th><td>No submissions have been made yet</td></tr></table></div></div>'
        data=r.parse_detail(r.DOM(html).root,'/mod/assign/view.php?id=1')
        self.assertEqual(data['due_iso'],'2026-10-27T09:00:00+07:00')
        self.assertEqual(data['instructions'],'Rincian tugas kelompok.')
        self.assertNotIn('PRIVATE',json.dumps(data))
    def test_blank_write_queries_rejected(self):
        for value in ['/mod/assign/view.php?id=1&action=','/course/overview.php?id=1&expand%5B%5D=']:
            with self.subTest(value=value),self.assertRaises(ValueError):r.safe_url(value)
    def test_other_origin_or_mutation_routes_rejected(self):
        for value in ['https://evil.example/my/','http://hebat.elearning.unair.ac.id/my/','/login/logout.php?sesskey=x','/mod/assign/view.php?id=1&action=submit','/mod/assign/view.php?id=1&id=2']:
            with self.subTest(value=value),self.assertRaises(ValueError):r.safe_url(value)
    def test_allowed_overview_fragment_removed(self):
        self.assertNotIn('#',r.safe_url('/course/overview.php?id=1&expand%5B%5D=assign#x'))
    def test_div_main_excludes_profile_navigation_and_comment_ui(self):
        data=r.parse_detail(r.DOM(detail_html('1')).root,'/mod/assign/view.php?id=1')
        self.assertNotIn('PRIVATE',json.dumps(data));self.assertEqual(data['instructions'],'Kerjakan tugas.')
    def test_due_year_required_for_verified_date(self):
        self.assertIsNone(r.parse_date('Monday, 26 October, 11:59 PM'))
        self.assertEqual(r.parse_date('Senin, 26 Oktober 2026, 23:59').year,2026)
    def test_academic_year_rollover_only_for_index_hint(self):
        self.assertEqual(r.parse_date('Monday, 5 January, 9:00 AM','2026Ganjil').year,2027)
        self.assertEqual(r.parse_date('Monday, 5 June, 9:00 AM','2025Genap').year,2026)
    def test_extension_effective_deadline(self):
        data=r.parse_detail(r.DOM(detail_html('1',24,extension='Tuesday, 27 October 2026, 8:00 AM')).root,'/mod/assign/view.php?id=1')
        self.assertEqual(data['due_iso'],'2026-10-27T08:00:00+07:00')
        self.assertIn('24 October',data['original_due'])
    def test_unknown_submission_status_uncertain(self):
        entry={'detail':{'status':'a new unknown status','due_iso':'2026-10-26T00:00:00+07:00'}}
        self.assertEqual(r.verified_bucket(entry,NOW),'uncertain')
    def test_unconfirmed_empty_index_warns(self):
        data=r.parse_index(r.DOM('<title>Course</title>').root,{'id':'1','name':'2026Ganjil - Test','url':'x'})
        self.assertIsNotNone(data['warning'])
    def test_full_course_title_replaces_short_calendar_label(self):
        course={'id':'1','name':'2026Ganjil - Analisis...','url':'x'}
        data=r.parse_index(r.DOM('<title>Course activities: 2026Ganjil - Analisis Praktikum I2 | HEBAT</title>No assignments').root,course)
        self.assertEqual(data['course']['name'],'2026Ganjil - Analisis Praktikum I2')


if __name__=='__main__':unittest.main(verbosity=2)
