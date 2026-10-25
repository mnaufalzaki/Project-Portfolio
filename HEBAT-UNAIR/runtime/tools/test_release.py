"""Source-only release and optional Claude skill synchronization."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

spec=importlib.util.spec_from_file_location('release_under_test',Path(__file__).with_name('release.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.runtime=self.root/'runtime';self.skill=self.root/'skill'
        for base,names in [(self.runtime,r.RUNTIME_FILES),(self.skill,r.SKILL_FILES)]:
            for name in names:
                p=base/name;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text('# fixture source\n')
        self.out=self.root/'dist';self.claude=self.root/'claude/hebat-unair'

    def kwargs(self):return {'runtime_root':self.runtime,'skill_root':self.skill,'output_dir':self.out}

    def test_default_build_has_no_claude_side_effect(self):
        result=r.build(**self.kwargs())
        self.assertNotIn('claude_skill_checked',result)
        self.assertFalse(self.claude.exists())
        self.assertTrue(r.check(**self.kwargs())['archives_checked'])

    def test_optional_copy_is_identical_excludes_codex_metadata_and_is_verified(self):
        result=r.build(**self.kwargs(),claude_skill_root=self.claude)
        self.assertTrue(result['claude_skill_checked'])
        self.assertFalse((self.claude/'agents/openai.yaml').exists())
        for name in r.CLAUDE_SKILL_FILES:self.assertEqual((self.claude/name).read_bytes(),(self.skill/name).read_bytes())
        p=self.claude/'scripts/hebat.py';before=p.stat().st_mtime_ns
        r.build(**self.kwargs(),claude_skill_root=self.claude)
        self.assertEqual(p.stat().st_mtime_ns,before)
        p.write_text('# changed\n')
        with self.assertRaisesRegex(ValueError,'claude_skill_copy_differs'):r.check(**self.kwargs(),claude_skill_root=self.claude)

    def test_escaped_destination_is_rejected_and_unrelated_files_preserved(self):
        outside=self.root/'outside';outside.mkdir();self.claude.parent.mkdir(parents=True)
        self.claude.symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'claude_skill_destination_invalid'):r.build(**self.kwargs(),claude_skill_root=self.claude)
        self.assertEqual(list(outside.iterdir()),[])
        self.claude.unlink();self.claude.mkdir()
        (self.claude/'my-notes.txt').write_text('keep')
        (self.claude/'scripts').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'claude_skill_path_outside_root'):r.build(**self.kwargs(),claude_skill_root=self.claude)
        self.assertEqual((self.claude/'my-notes.txt').read_text(),'keep')

    def test_only_allowlisted_sources_enter_archives(self):
        for base in (self.runtime,self.skill):
            for name in ('.cache/private.json','.session/cookies.txt','runtime.json'):
                p=base/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture private data')
        r.build(**self.kwargs(),claude_skill_root=self.claude)
        for archive in self.out.glob('*.zip'):
            with zipfile.ZipFile(archive) as z:
                self.assertFalse(any('.cache/' in x or '.session/' in x or x.endswith('runtime.json') for x in z.namelist()))
                self.assertIn('BUILD-MANIFEST.json',z.namelist())

    def test_repo_layout_uses_colocated_skill_and_includes_attribution(self):
        new=self.root/'skills/hebat-unair';new.parent.mkdir()
        self.skill.rename(new);self.skill=new
        for name in ('LICENSE','NOTICE.md'):(self.root/name).write_text('fixture attribution\n')
        with patch.object(r,'SCRIPT',self.runtime/'tools/release.py'):
            self.assertEqual(r.default_roots(),(self.runtime,self.skill))
            self.assertTrue(r.build()['archives_checked'])
            self.assertTrue(r.check(output_dir=self.out)['archives_checked'])
        with zipfile.ZipFile(self.out/'HEBAT-Keychain-Runtime.zip') as z:
            self.assertEqual(z.read('NOTICE.md'),b'fixture attribution\n')
        with zipfile.ZipFile(self.out/'hebat-unair-skill.zip') as z:
            self.assertEqual(z.read('hebat-unair/LICENSE'),b'fixture attribution\n')

if __name__=='__main__':unittest.main()
