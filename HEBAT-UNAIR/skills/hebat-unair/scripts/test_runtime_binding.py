"""Shared local runtime discovery, with no campus or Keychain access."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('helper_binding_test',Path(__file__).with_name('hebat.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class RuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix='hebat binding ');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.pointer=self.root/'config/runtime.json'
        self.patcher=patch.object(h,'runtime_config_path',return_value=self.pointer)
        self.patcher.start();self.addCleanup(self.patcher.stop)
        self.python,self.server=self.runtime('runtime one')

    def runtime(self,name):
        root=self.root/name;folder=root/'hebat_mcp';folder.mkdir(parents=True)
        python=root/'.venv/bin/python';python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        server=folder/'server.py';server.write_text('# fixture server\n')
        (folder/'login.py').write_text('# fixture login\n')
        return str(python.absolute()),str(server.resolve())

    def bind(self):return h.bind_runtime(self.python,self.server)

    def test_binding_is_private_atomic_and_idempotent_preserving_venv(self):
        self.assertTrue(self.bind()['changed'])
        before=self.pointer.stat().st_mtime_ns
        self.assertFalse(self.bind()['changed'])
        self.assertEqual(self.pointer.stat().st_mtime_ns,before)
        self.assertEqual(self.pointer.stat().st_mode&0o777,0o600)
        self.assertEqual(self.pointer.parent.stat().st_mode&0o777,0o700)
        self.assertEqual(set(json.loads(self.pointer.read_text())),{'version','python','server'})
        self.assertEqual(list(self.pointer.parent.glob('.runtime-*')),[])
        c,p=h.config();self.assertEqual(c['transport']['command'],self.python)
        self.assertEqual(p,Path(self.server).resolve())

    def test_existing_different_runtime_is_not_overwritten(self):
        self.bind();before=self.pointer.read_bytes()
        python,server=self.runtime('runtime two')
        with self.assertRaisesRegex(RuntimeError,'runtime_binding_conflict'):h.bind_runtime(python,server)
        self.assertEqual(self.pointer.read_bytes(),before)

    def test_valid_pointer_works_without_codex_and_from_another_directory(self):
        self.bind();cwd=Path.cwd()
        try:
            os.chdir(self.root)
            with patch.object(h.shutil,'which',return_value=None) as which,patch.object(h.subprocess,'run') as run:
                c,_=h.config()
            which.assert_not_called();run.assert_not_called()
            self.assertEqual(c['transport']['command'],self.python)
        finally:os.chdir(cwd)

    def test_missing_pointer_preserves_legacy_config(self):
        legacy={'enabled':True,'transport':{'type':'stdio','command':self.python,'args':[self.server]}}
        with patch.object(h.shutil,'which',return_value='/fixture/codex'),patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(legacy))) as run:
            c,p=h.config()
        self.assertEqual(c,legacy);self.assertEqual(p,Path(self.server).resolve())
        self.assertEqual(run.call_args.args[0],['/fixture/codex','mcp','get','hebat','--json'])
        self.assertFalse(self.pointer.exists())

    def test_missing_pointer_and_codex_has_actionable_error(self):
        with patch.object(h.shutil,'which',return_value=None),patch.object(h.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'runtime_not_configured'):h.config()
        run.assert_not_called()

    def test_legacy_disabled_config_is_not_enabled(self):
        with patch.object(h.shutil,'which',return_value='/fixture/codex'),patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"enabled":false}')):
            with self.assertRaisesRegex(RuntimeError,'disabled'):h.config()

    def test_corrupt_pointer_does_not_fall_back(self):
        self.bind()
        invalid=['{','[]','{"version":true,"python":"/x","server":"/y"}',
                 json.dumps({'version':1,'python':self.python,'server':self.server,'password':'fixture'})]
        for value in invalid:
            with self.subTest(value=value):
                self.pointer.write_text(value)
                with patch.object(h.subprocess,'run') as run:
                    with self.assertRaisesRegex(RuntimeError,'runtime_pointer_invalid'):h.config()
                run.assert_not_called()

    def test_missing_files_and_relative_paths_are_rejected_without_rebinding(self):
        for python,server in [(self.python,'relative/server.py'),('/missing/python',self.server),(self.python,str(self.root/'missing/server.py'))]:
            with self.subTest(python=python,server=server),self.assertRaises(RuntimeError):h.bind_runtime(python,server)
        self.assertFalse(self.pointer.exists())
        self.bind();Path(self.server).unlink()
        with patch.object(h.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'runtime_files_unavailable'):h.config()
        run.assert_not_called()

    def test_symlink_and_public_pointer_are_rejected(self):
        self.bind();original=self.pointer.read_bytes();self.pointer.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,'runtime_pointer_not_private'):h.config()
        self.pointer.unlink();outside=self.root/'outside.json';outside.write_bytes(original);outside.chmod(0o600)
        self.pointer.symlink_to(outside)
        with self.assertRaisesRegex(RuntimeError,'runtime_pointer_invalid'):h.config()
        self.assertEqual(outside.read_bytes(),original)

    def test_cli_bind_does_not_resolve_existing_config_or_touch_auth(self):
        argv=['hebat.py','bind-runtime','--python',self.python,'--server',self.server]
        out=io.StringIO()
        with patch.object(h.sys,'argv',argv),patch.object(h,'config') as config,contextlib.redirect_stdout(out):
            self.assertEqual(h.main(),0)
        config.assert_not_called();self.assertTrue(json.loads(out.getvalue())['runtime_bound'])

    def test_worker_receives_exact_selected_runtime(self):
        self.bind();c,_=h.config()
        with patch.object(h.sys,'argv',['hebat.py','courses']),patch.object(h,'config',return_value=(c,Path(self.server))),patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(h.main(),0)
        args=run.call_args.args[0]
        self.assertEqual(args[0],self.python)
        self.assertEqual(args[-5:],['--worker','--python',self.python,'--server',self.server])

    def test_explicit_worker_does_not_read_changed_pointer(self):
        argv=['hebat.py','check','--worker','--python',self.python,'--server',self.server]
        with patch.object(h.sys,'argv',argv),patch.object(h,'config',side_effect=AssertionError('should not rediscover')),patch.object(h,'handshake',new=lambda _:None),patch.object(h.asyncio,'run',return_value={'account':{'authenticated':True}}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(h.main(),0)

    def test_terminal_launcher_and_login_keep_selected_runtime(self):
        c,server=h.config_from_paths(self.python,self.server)
        with patch.object(h.Path,'is_dir',return_value=True),patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0,stderr='')) as run:
            h.launch_login(c,server,wait_seconds=0)
        launcher=Path(run.call_args.args[0][-1]);self.addCleanup(lambda: __import__('shutil').rmtree(launcher.parent))
        args=shlex.split(launcher.read_text().splitlines()[2])
        self.assertEqual(args[-4:],['--python',self.python,'--server',self.server])
        with patch.object(h,'config',side_effect=AssertionError('should not rediscover')),patch.object(h.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(h.terminal_login(str(self.root/'receipt.json'),python=self.python,server=self.server),0)
        self.assertEqual(run.call_args.args[0],[self.python,str(server.parent/'login.py')])

    def test_runtime_flags_rejected_for_routine_user_operations(self):
        for args in [['courses','--python',self.python,'--server',self.server],['bind-runtime'],['bind-runtime','--python',self.python]]:
            with self.subTest(args=args),patch.object(h.sys,'argv',['hebat.py',*args]),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):h.main()

if __name__=='__main__':unittest.main()
