import importlib.util
import io
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

p=Path(__file__).with_name('hebat.py')
spec=importlib.util.spec_from_file_location('hebat',p);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
FIXTURE=TemporaryDirectory(prefix='hebat-test-')
SERVER=Path(FIXTURE.name)/'server.py'
SERVER.write_text('# offline fixture')
SERVER.with_name('login.py').write_text('# offline fixture')
CONFIG={'transport':{'command':'/usr/bin/python3','args':[str(SERVER)],'type':'stdio'}}

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.app=patch.object(h.Path,'is_dir',return_value=True);self.app.start();self.addCleanup(self.app.stop)
        self.pointer=patch.object(h,'runtime_config_path',return_value=Path(FIXTURE.name)/'no-pointer/runtime.json')
        self.pointer.start();self.addCleanup(self.pointer.stop)
    def test_read_route(self):
        self.assertTrue(h.safe_url('/mod/assign/view.php?id=12').endswith('id=12'))
    def test_external_and_write_routes(self):
        for url in ['https://example.com/my/','/login/logout.php?sesskey=x','/mod/assign/view.php?id=1&action=submit','http://hebat.elearning.unair.ac.id/my/']:
            with self.subTest(url=url),self.assertRaises(ValueError):h.safe_url(url)
    def test_moodle_overview_redirect(self):
        url=h.safe_url('/course/overview.php?id=10992&expand%5B%5D=assign#assign_overview_collapsible')
        self.assertNotIn('#',url);self.assertIn('expand%5B%5D=assign',url)
    def test_overview_write_and_other_modules_blocked(self):
        for url in ['/course/overview.php?id=1&action=delete','/course/overview.php?id=1&expand%5B%5D=quiz']:
            with self.subTest(url=url),self.assertRaises(ValueError):h.safe_url(url)
    def test_submitted_ungraded_distinct(self):
        html='<title>Tugas | HEBAT</title><main>Due: Monday, 26 October 2026, 11:59 PM<table><tr><th>Submission status</th><td>Submitted for grading</td></tr><tr><th>Grading status</th><td>Not graded</td></tr></table></main>'
        r=h.data.parse_detail(h.DOM(html).root,'/mod/assign/view.php?id=12')
        self.assertEqual(r['status'],'Submitted for grading');self.assertEqual(r['grading_status'],'Not graded')
        self.assertEqual(r['due_full'],'Monday, 26 October 2026, 11:59 PM')
    def test_dynamic_course_options(self):
        dom=h.DOM('<select name="course"><option value="1">All courses</option><option value="10926">AVD praktikum I1</option></select>').root
        r=h.data.parse_courses(dom)
        self.assertEqual([x['id'] for x in r],['10926'])
    def test_empty_courses_not_success(self):
        with self.assertRaises(ValueError):h.data.parse_courses(h.DOM('<main>Dashboard</main>').root)
    def test_launchservices_failure_is_host_specific(self):
        with patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='-10827 kLSNoExecutableErr')) as run:
            r=h.launch_login(CONFIG,SERVER,wait_seconds=.01)
        self.assertEqual(r['login_state'],'host_execution_required')
        self.assertFalse(r['terminal_started_verified']);self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0][0],'/usr/bin/open')
    def test_acceptance_alone_not_window_verified(self):
        with patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')):
            r=h.launch_login(CONFIG,SERVER,wait_seconds=.01)
        self.assertEqual(r['login_state'],'launch_requested_unverified');self.assertIsNone(r['authenticated'])
    def test_receipt_start_does_not_claim_login(self):
        def opened(cmd,**kw):
            launcher=Path(cmd[-1]);(launcher.parent/'receipt.json').write_text(json.dumps({'phase':'terminal_started'}))
            return SimpleNamespace(returncode=0,stderr='')
        with patch.object(h.subprocess,'run',side_effect=opened):r=h.launch_login(CONFIG,SERVER,wait_seconds=.01)
        self.assertTrue(r['terminal_started_verified']);self.assertIsNone(r['authenticated'])
    def test_failed_terminal_runtime_not_awaiting_credentials(self):
        def opened(cmd,**kw):
            (Path(cmd[-1]).parent/'receipt.json').write_text(json.dumps({'phase':'login_runtime_error'}))
            return SimpleNamespace(returncode=0,stderr='')
        with patch.object(h.subprocess,'run',side_effect=opened):r=h.launch_login(CONFIG,SERVER,wait_seconds=.01)
        self.assertEqual(r['login_state'],'login_runtime_error')
    def test_disabled_config_not_overridden(self):
        with patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'enabled':False}))):
            with self.assertRaises(RuntimeError):h.config()
    def test_check_nonzero_when_mcp_connected_but_account_inactive(self):
        with patch.object(h.sys,'argv',['hebat.py','check','--worker']),patch.object(h,'config',return_value=(CONFIG,SERVER)),patch.object(h.data,'BUILD_ID','fixture-build',create=True),patch.object(h,'handshake',new=lambda c:None),patch.object(h.asyncio,'run',return_value={'mcp_connected':True,'account':{'authenticated':False}}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(h.main(),1)

    def test_attachment_missing_output_rejected_before_config_or_network(self):
        with patch.object(h.sys,'argv',['hebat.py','attachment','https://hebat.elearning.unair.ac.id/pluginfile.php/1/task.pdf']),patch.object(h,'config') as config,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exited:h.main()
        self.assertEqual(exited.exception.code,2);config.assert_not_called()

    def test_output_not_accepted_for_non_attachment_operation(self):
        with patch.object(h.sys,'argv',['hebat.py','priority','--output','unused.pdf']),patch.object(h,'config') as config,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exited:h.main()
        self.assertEqual(exited.exception.code,2);config.assert_not_called()

    def run_offline_attachment(self,audit=False):
        from unittest.mock import Mock
        url='https://hebat.elearning.unair.ac.id/pluginfile.php/1/task.pdf?forcedownload=1'
        reader=Mock()
        reader.attachment.return_value={'path':'fixture/task.pdf','bytes_written':12}
        reader.run_metrics.return_value={'http_get_attempts':1}
        argv=['hebat.py','attachment',url,'--output','fixture/task.pdf','--worker']
        if audit:argv.append('--audit-metrics')
        output=io.StringIO()
        with patch.object(h.sys,'argv',argv),patch.object(h,'config',return_value=(CONFIG,SERVER)),patch.dict(h.sys.modules,{'auth':SimpleNamespace()}),patch.object(h.data,'BUILD_ID','fixture-build',create=True),patch.object(h.data,'Reader',return_value=reader),contextlib.redirect_stdout(output):
            self.assertEqual(h.main(),0)
        reader.attachment.assert_called_once_with(url,'fixture/task.pdf')
        return json.loads(output.getvalue()),reader

    def test_attachment_routes_to_guarded_reader_and_metrics_are_opt_in(self):
        result,reader=self.run_offline_attachment()
        self.assertEqual(result['build_id'],'fixture-build')
        self.assertNotIn('metrics',result)
        reader.run_metrics.assert_not_called()

    def test_audit_metrics_are_added_when_requested(self):
        result,reader=self.run_offline_attachment(audit=True)
        self.assertEqual(result['metrics'],{'http_get_attempts':1})
        reader.run_metrics.assert_called_once_with()

    def failing_offline_attachment(self,audit=False):
        from unittest.mock import Mock
        url='https://hebat.elearning.unair.ac.id/pluginfile.php/1/task.pdf?forcedownload=1'
        reader=Mock()
        error=RuntimeError('fixture-private-cookie; https://fixture.invalid/private')
        error.code='network_unavailable'
        reader.attachment.side_effect=error
        reader.run_metrics.return_value={'http_get_attempts':1,'http_post_attempts':1,
                                         'network_errors':1,'http_seconds':0.25,
                                         'url':'https://fixture.invalid/private',
                                         'cookie':'fixture-private-cookie'}
        argv=['hebat.py','attachment',url,'--output','fixture/task.pdf','--worker']
        if audit:argv.append('--audit-metrics')
        with patch.object(h.sys,'argv',argv),patch.object(h,'config',return_value=(CONFIG,SERVER)),patch.dict(h.sys.modules,{'auth':SimpleNamespace()}),patch.object(h.data,'BUILD_ID','fixture-build',create=True),patch.object(h.data,'Reader',return_value=reader):
            with self.assertRaises(RuntimeError) as raised:h.main()
            result=h.error_result(raised.exception)
        return result,reader

    def test_failed_audit_operation_retains_only_aggregate_metrics(self):
        result,reader=self.failing_offline_attachment(audit=True)
        self.assertEqual(result['error'],'network_unavailable')
        self.assertFalse(result['complete'])
        self.assertEqual(result['metrics'],{'http_get_attempts':1,'http_post_attempts':1,
                                            'network_errors':1,'http_seconds':0.25})
        self.assertNotIn('fixture-private-cookie',json.dumps(result))
        self.assertNotIn('https://fixture.invalid',json.dumps(result))
        reader.run_metrics.assert_called_once_with()

    def test_material_invalid_arguments_before_config(self):
        for args in [['material'],['material','--course','kbsi','--limit','6'],
                     ['material','https://example.invalid','--course','kbsi'],['material','--course','kbsi','--output','x.pdf']]:
            with self.subTest(args=args),patch.object(h.sys,'argv',['hebat.py',*args]),patch.object(h,'config') as config,contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):h.main()
                config.assert_not_called()

    def test_material_cli_routes_to_shared_reader(self):
        from unittest.mock import Mock
        reader=Mock();reader.material.return_value={'complete':True,'materials':[{'local_path':'/fixture/private/source.pdf'}]}
        output=io.StringIO()
        with patch.object(h.sys,'argv',['hebat.py','material','--course','kbsi','--file-type','pdf','--limit','2','--worker']),patch.object(h,'config',return_value=(CONFIG,SERVER)),patch.dict(h.sys.modules,{'auth':SimpleNamespace()}),patch.object(h.data,'Reader',return_value=reader),contextlib.redirect_stdout(output):
            self.assertEqual(h.main(),0)
        reader.material.assert_called_once_with(course_query='kbsi',url=None,limit=2,file_type='pdf',output=None)
        self.assertEqual(json.loads(output.getvalue())['materials'][0]['local_path'],'/fixture/private/source.pdf')

    def test_empty_material_result_exits_failure(self):
        from unittest.mock import Mock
        reader=Mock();reader.material.return_value={'complete':False,'error':'no_matching_course','materials':[]}
        with patch.object(h.sys,'argv',['hebat.py','material','--course','unknown','--worker']),patch.object(h,'config',return_value=(CONFIG,SERVER)),patch.dict(h.sys.modules,{'auth':SimpleNamespace()}),patch.object(h.data,'Reader',return_value=reader),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(h.main(),1)

    def test_failed_routine_operation_does_not_add_metrics(self):
        result,reader=self.failing_offline_attachment()
        self.assertEqual(result['error'],'network_unavailable')
        self.assertNotIn('metrics',result)
        reader.run_metrics.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
