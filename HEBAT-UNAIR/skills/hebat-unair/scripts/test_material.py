"""Resource discovery and complete Resource-to-file reads, with no live account."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor
import json
import unittest

import test_reader as fixtures
from test_attachment import BinaryResponse, PDF

r = fixtures.r


def activity(ident, label, kind='PDF'):
    return f'<li class="activity resource modtype_resource"><img src="/f/{"pdf" if kind=="PDF" else "powerpoint"}"><a href="/mod/resource/view.php?id={ident}">{label} File</a><span>{kind}</span></li>'


def course_page(name):
    return f'''<title>Course: {name}</title><nav>{activity('99','Navigation PDF')}</nav><main>
    <li id="section-2" data-sectionname="Minggu 2">{activity('2','Materi lama')}</li>
    <li id="section-10" data-sectionname="Minggu 10">{activity('10','Materi terbaru')}</li>
    <li id="section-11" data-sectionname="Minggu 11">{activity('11','Presentasi terbaru','PPTX')}</li>
    </main>'''


class MaterialAuth(fixtures.FakeAuth):
    def __init__(self, root):
        super().__init__(root)
        self.names = {'30':'2026Ganjil - Kewirausahaan Dan Bisnis Sistem Informasi - I1',
                      '31':'2026Ganjil - Inovasi Sistem Informasi dan Teknologi - I2',
                      '32':'2026Ganjil - Analisis dan Visualisasi Data (praktikum) - I1',
                      '33':'2026Ganjil - Analisis dan Visualisasi Data - I1'}
        self.full_names = dict(self.names)
        self.binary = {}
        self.options = []

    def attachment_url(self, value):
        p = urlparse(value)
        try:query=parse_qs(p.query,keep_blank_values=True,strict_parsing=True)
        except ValueError:raise fixtures.AuthError('attachment_route_not_allowed') from None
        allowed_query=not p.query or query in ({'forcedownload':['0']},{'forcedownload':['1']})
        if p.scheme!='https' or p.netloc!=urlparse(r.BASE).netloc or not p.path.startswith('/pluginfile.php/') or not allowed_query:
            raise fixtures.AuthError('attachment_route_not_allowed')
        return value

    def material_url(self, value):
        p = urlparse(value)
        if p.path == '/mod/resource/view.php' and p.scheme=='https' and p.netloc==urlparse(r.BASE).netloc:
            q = parse_qs(p.query, keep_blank_values=True)
            if set(q)=={'id'} and len(q['id'])==1 and q['id'][0].isdigit():
                return value
            raise fixtures.AuthError('material_route_not_allowed')
        return self.attachment_url(value)

    def request(self, session, url, **kwargs):
        if urlparse(url).path=='/my/':
            return super().request(session,url)
        self.calls.append(url)
        self.options.append(kwargs)
        ident = parse_qs(urlparse(url).query).get('id',[''])[0]
        if urlparse(url).path=='/course/view.php':
            return SimpleNamespace(text=course_page(self.full_names[ident]))
        if url in self.binary:
            value = self.binary[url].pop(0)
            if isinstance(value,Exception):raise value
            return value
        response = BinaryResponse(content_type='application/vnd.ms-powerpoint' if ident=='11' else 'application/pdf')
        if ident=='11':response.chunks=[b'not a pdf']
        response.url = r.BASE+'pluginfile.php/'+(ident or '10')+'/material.'+('pptx' if ident=='11' else 'pdf')
        return response


class MaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.auth = MaterialAuth(self.tmp.name)
        self.url = r.BASE+'mod/resource/view.php?id=10'
        self.file_url = r.BASE+'pluginfile.php/10/material.pdf'

    def reader(self):return r.Reader(self.auth,now=lambda:fixtures.NOW)

    def html(self, body):
        response = BinaryResponse([body.encode()],content_type='text/html');response.url=self.url
        self.auth.binary[self.url]=[response]
        return response

    def test_kbsi_alias_downloads_two_latest_pdfs_from_only_matching_class(self):
        result = self.reader().material(course_query='kbsi',limit=2,file_type='pdf')
        self.assertTrue(result['complete'])
        self.assertEqual([x['title'] for x in result['materials']],['Materi terbaru','Materi lama'])
        self.assertEqual([x['section'] for x in result['materials']],['Minggu 10','Minggu 2'])
        self.assertEqual([x for x in self.auth.calls if '/course/view.php' in x],[r.BASE+'course/view.php?id=30'])
        self.assertNotIn('id=99',' '.join(self.auth.calls))
        self.assertNotIn(r.BASE+'mod/resource/view.php?id=11',self.auth.calls)
        for item in result['materials']:
            p=Path(item['local_path'])
            self.assertEqual(p.read_bytes(),PDF)
            self.assertEqual(p.stat().st_mode&0o777,0o600)
            self.assertEqual(p.parent.stat().st_mode&0o777,0o700)
            self.assertIn(self.reader().account_id,str(p))
            self.assertEqual(item['content_type'],'application/pdf')

    def test_isit_alias_and_existing_avd_theory_scope(self):
        for query,ident in [('isit','31'),('avd teo i1','33')]:
            self.auth.calls.clear()
            result=self.reader().material(course_query=query)
            self.assertTrue(result['complete'])
            self.assertEqual([x for x in self.auth.calls if '/course/view.php' in x],[r.BASE+'course/view.php?id='+ident])

    def test_any_type_returns_latest_presentation(self):
        result=self.reader().material(course_query='kbsi')
        self.assertEqual(result['materials'][0]['title'],'Presentasi terbaru')

    def test_ambiguous_course_returns_candidates_without_downloading(self):
        result=self.reader().material(course_query='avd')
        self.assertEqual(result['error'],'ambiguous_material_course')
        self.assertEqual({x['id'] for x in result['candidates']},{'32','33'})
        self.assertFalse(any('/mod/resource/' in x or '/pluginfile.php/' in x for x in self.auth.calls))

    def test_truncated_alias_is_resolved_from_only_relevant_course(self):
        self.auth.names['30']='2026Ganjil - Kewirausahaan Dan Bisnis ...'
        result=self.reader().material(course_query='kbsi',file_type='pdf')
        self.assertTrue(result['complete'])
        self.assertEqual(result['materials'][0]['course'],self.auth.full_names['30'])
        self.assertEqual(sum('/course/view.php' in x for x in self.auth.calls),1)

    def test_truncated_full_kbsi_name_uses_same_selection_as_alias(self):
        self.auth.names={i:name.split(' - ')[0]+' - '+name.split(' - ')[1][:12]+'...' for i,name in self.auth.names.items()}
        result=self.reader().material(course_query='Kewirausahaan dan Bisnis Sistem Informasi',file_type='pdf')
        self.assertTrue(result['complete'])
        self.assertEqual([x for x in self.auth.calls if '/course/view.php' in x],[r.BASE+'course/view.php?id=30'])

    def test_direct_resource_bypasses_course_discovery(self):
        result=self.reader().material(url=self.url,file_type='pdf')
        self.assertTrue(result['complete'])
        self.assertEqual(self.auth.calls,[self.url])
        self.assertEqual(result['materials'][0]['source_url'],self.url)
        self.assertEqual(result['materials'][0]['file_url'],self.file_url)
        self.assertEqual(self.auth.options,[{'material_route':True,'stream':True}])

    def test_original_attachment_resource_call_now_works(self):
        path=Path(self.tmp.name)/'original.pdf'
        result=self.reader().attachment(self.url,path)
        self.assertEqual(path.read_bytes(),PDF)
        self.assertEqual(result['local_path'],str(path))

    def test_relative_embed_is_resolved_once_and_uses_attachment_guard(self):
        html=self.html('<iframe src="../../pluginfile.php/10/material.pdf"></iframe>')
        result=self.reader().material(url=self.url,file_type='pdf')
        self.assertTrue(result['complete'])
        self.assertEqual(self.auth.calls,[self.url,self.file_url])
        self.assertEqual(self.auth.options[-1],{'attachment_route':True,'stream':True})
        self.assertTrue(html.closed)

    def test_object_and_download_anchor_can_name_same_file(self):
        self.html(f'<object data="{self.file_url}"></object><a href="{self.file_url}">Download</a>')
        self.assertTrue(self.reader().material(url=self.url)['complete'])

    def test_download_mode_variants_of_same_file_are_not_ambiguous(self):
        for suffix in ['?forcedownload=0','?forcedownload=1']:
            with self.subTest(suffix=suffix):
                self.html(f'<a href="{self.file_url}">Open</a><a href="{self.file_url}{suffix}">Download</a>')
                result=self.reader().material(url=self.url,file_type='pdf')
                self.assertTrue(result['complete'])
                self.assertEqual(self.auth.calls[-1],self.file_url)

    def test_unsafe_query_is_not_removed_before_validation(self):
        self.html(f'<a href="{self.file_url}">Open</a><a href="{self.file_url}?token=private">Bad</a>')
        result=self.reader().material(url=self.url)
        self.assertFalse(result['complete'])
        self.assertEqual(self.auth.calls,[self.url])

    def test_material_shares_full_names_with_later_index_selection_without_extending_ttl(self):
        from unittest.mock import patch
        import types
        self.auth.names={i:name.split(' - ')[0]+' - '+name.split(' - ')[1][:12]+'...' for i,name in self.auth.names.items()}
        first=self.reader();first.courses()
        before=first.cache.read('courses',600)
        with patch.object(r.time,'time',return_value=before['fetched_at']+10):
            first.material(course_query='kbsi',file_type='pdf')
        after=first.cache.read('courses',600)
        self.assertEqual(after['fetched_at'],before['fetched_at'])
        self.assertEqual(next(c['name'] for c in after['data'] if c['id']=='30'),self.auth.full_names['30'])
        self.assertEqual(first.dependencies['courses'],after['revision'])
        later=self.reader();seen=[]
        def index(reader,course,force=False):
            seen.append(course['id'])
            return {'course':dict(course,name=self.auth.full_names[course['id']]),'entries':[],
                    'warning':None,'checked_at':r.stamp()}
        later.index=types.MethodType(index,later)
        _,courses,_=later.select_courses('auto');later.indices(courses,'kbsi')
        self.assertEqual(seen,['30'])

    def test_multiple_files_are_reported_without_following_them(self):
        self.html('<a href="/pluginfile.php/1/a.pdf">A</a><a href="/pluginfile.php/2/b.pdf">B</a>')
        result=self.reader().material(url=self.url)
        self.assertEqual(result['errors'][0]['error'],'ambiguous_material_files')
        self.assertFalse(result['materials']);self.assertEqual(self.auth.calls,[self.url])

    def test_external_embed_is_rejected_before_destination(self):
        self.html('<iframe src="https://outside.invalid/file.pdf"></iframe>')
        result=self.reader().material(url=self.url)
        self.assertFalse(result['complete']);self.assertEqual(self.auth.calls,[self.url])

    def test_resource_with_no_file_reports_failure(self):
        self.html('<main>No file here</main>')
        self.assertEqual(self.reader().material(url=self.url)['errors'][0]['error'],'material_file_not_found')

    def test_resource_login_recovers_once(self):
        response=BinaryResponse();response.url=self.file_url
        self.auth.binary[self.url]=[None,response]
        self.assertTrue(self.reader().material(url=self.url)['complete'])
        self.assertEqual(self.auth.ensures,2)

    def test_failed_latest_material_does_not_hide_partial_coverage(self):
        self.auth.binary[self.url]=[fixtures.AuthError('network_unavailable')]
        result=self.reader().material(course_query='kbsi',file_type='pdf')
        self.assertFalse(result['complete'])
        self.assertEqual(result['materials'][0]['title'],'Materi lama')
        self.assertEqual(result['errors'][0]['source_url'],self.url)

    def test_pdf_filter_checks_actual_binary_before_publishing(self):
        response=BinaryResponse([b'not pdf'],content_type='application/octet-stream');response.url=self.file_url
        self.auth.binary[self.url]=[response]
        result=self.reader().material(course_query='kbsi',file_type='pdf')
        self.assertEqual(result['materials'][0]['title'],'Materi lama')
        self.assertTrue(response.closed)

    def test_invalid_inputs_have_no_network(self):
        for kwargs in [{},{'course_query':'kbsi','url':self.url},{'course_query':'kbsi','limit':6},
                       {'url':self.url,'limit':2},{'course_query':'kbsi','file_type':'exe'},
                       {'course_query':'kbsi','output':'x.pdf'}]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.reader().material(**kwargs)
        self.assertEqual(self.auth.calls,[])

    def test_expanding_previous_materials_only_downloads_new_files(self):
        first=self.reader().material(course_query='kbsi',limit=1)
        self.auth.calls.clear()
        later=self.reader().material(course_query='kbsi',limit=3)
        self.assertTrue(later['complete'])
        self.assertEqual((later['files_reused'],later['files_downloaded']),(1,2))
        self.assertEqual(first['materials'][0]['local_path'],later['materials'][0]['local_path'])
        resources=[x for x in self.auth.calls if '/mod/resource/' in x]
        self.assertEqual(resources,[self.url,r.BASE+'mod/resource/view.php?id=2'])
        self.assertEqual(later['materials'][0]['checked_at'],first['materials'][0]['checked_at'])
        self.assertTrue(later['materials'][0]['from_cache'])

    def test_repeated_direct_resource_and_file_alias_use_same_verified_file(self):
        first=self.reader().material(url=self.url)['materials'][0]
        self.auth.calls.clear()
        for url in (self.url,self.file_url,self.file_url+'?forcedownload=1'):
            result=self.reader().material(url=url,file_type='pdf')
            self.assertTrue(result['complete'])
            self.assertEqual(result['materials'][0]['local_path'],first['local_path'])
            self.assertEqual((result['files_reused'],result['files_downloaded']),(1,0))
        self.assertEqual(self.auth.calls,[])

    def test_fresh_rechecks_source_and_changed_content_without_overwriting(self):
        first=self.reader().material(url=self.url)['materials'][0]
        changed=PDF+b'updated'
        response=BinaryResponse([changed]);response.url=self.file_url
        self.auth.binary[self.url]=[response]
        self.auth.calls.clear()
        result=r.Reader(self.auth,fresh=True,now=lambda:fixtures.NOW).material(url=self.url)
        item=result['materials'][0]
        self.assertEqual(self.auth.calls,[self.url])
        self.assertEqual((result['files_reused'],result['files_downloaded']),(0,1))
        self.assertNotEqual(item['local_path'],first['local_path'])
        self.assertEqual(Path(item['local_path']).read_bytes(),changed)
        self.assertEqual(Path(first['local_path']).read_bytes(),PDF)

    def test_missing_or_corrupt_file_is_downloaded_again(self):
        for mode in ('missing','same_size_corrupt'):
            with self.subTest(mode=mode):
                item=self.reader().material(url=self.url)['materials'][0]
                path=Path(item['local_path'])
                if mode=='missing':path.unlink()
                else:path.write_bytes(b'x'*item['bytes'])
                self.auth.calls.clear()
                result=self.reader().material(url=self.url)
                new=Path(result['materials'][0]['local_path'])
                self.assertNotEqual(path,new)
                self.assertEqual(new.read_bytes(),PDF)
                self.assertEqual(self.auth.calls,[self.url])

    def test_cached_paths_cannot_escape_account_or_follow_symlinks(self):
        outside=Path(self.tmp.name)/'outside.pdf';outside.write_bytes(PDF)
        outside.chmod(0o600)
        for mode in ('outside','symlink','public_file','public_folder'):
            with self.subTest(mode=mode):
                reader=self.reader();item=reader.material(url=self.url)['materials'][0]
                item=dict(item);path=Path(item['local_path'])
                if mode=='outside':item['local_path']=str(outside)
                elif mode=='symlink':path.unlink();path.symlink_to(outside)
                elif mode=='public_file':path.chmod(0o644)
                else:path.parent.chmod(0o755)
                reader.cache.write(reader.material_file_key(self.url),item)
                self.auth.calls.clear()
                result=self.reader().material(url=self.url)
                self.assertEqual(result['files_downloaded'],1)
                self.assertEqual(self.auth.calls,[self.url])
                self.assertEqual(outside.read_bytes(),PDF)

    def test_corrupt_metadata_is_a_miss_and_other_account_cannot_reuse(self):
        reader=self.reader();reader.material(url=self.url)
        key=reader.material_file_key(self.url)
        for data in ([],{'bytes':True},{'local_path':'/tmp/no-file'}):
            reader.cache.write(key,data)
            self.auth.calls.clear()
            self.assertEqual(self.reader().material(url=self.url)['files_downloaded'],1)
            self.assertEqual(self.auth.calls,[self.url])
        path=reader.cache.folder/(key+'.json')
        payload=json.loads(path.read_text());payload['account_id']='other-account'
        path.write_text(json.dumps(payload));self.auth.calls.clear()
        self.assertEqual(self.reader().material(url=self.url)['files_downloaded'],1)
        self.assertEqual(self.auth.calls,[self.url])

    def test_cached_non_pdf_is_not_returned_as_pdf(self):
        url=r.BASE+'mod/resource/view.php?id=11'
        self.reader().material(url=url)
        self.auth.calls.clear()
        result=self.reader().material(url=url,file_type='pdf')
        self.assertFalse(result['complete'])
        self.assertFalse(result['materials'])
        self.assertEqual(self.auth.calls,[])

    def test_explicit_output_still_downloads_and_never_overwrites(self):
        first=self.reader().material(url=self.url)['materials'][0]
        output=Path(self.tmp.name)/'explicit.pdf'
        self.auth.calls.clear()
        self.reader().material(url=self.url,output=output)
        self.assertEqual(self.auth.calls,[self.url])
        self.assertEqual(output.read_bytes(),PDF)
        self.auth.calls.clear()
        result=self.reader().material(url=self.url,output=output)
        self.assertEqual(result['errors'][0]['error'],'attachment_output_exists')
        self.assertEqual(self.auth.calls,[])
        self.assertEqual(Path(first['local_path']).read_bytes(),PDF)

    def test_concurrent_same_resource_downloads_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: self.reader().material(url=self.url),range(2)))
        self.assertEqual(sum(x['files_downloaded'] for x in results),1)
        self.assertEqual(sum(x['files_reused'] for x in results),1)
        self.assertEqual(self.auth.calls,[self.url])
        self.assertEqual(results[0]['materials'][0]['local_path'],results[1]['materials'][0]['local_path'])

    def test_assignment_reader_gives_material_guidance(self):
        with self.assertRaisesRegex(ValueError,'use_material_for_resource_url'):
            self.reader().detail(self.url)
        self.assertEqual(self.auth.calls,[])


if __name__=='__main__':unittest.main(verbosity=2)
