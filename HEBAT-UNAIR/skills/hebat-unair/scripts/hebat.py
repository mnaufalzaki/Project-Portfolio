#!/usr/bin/env python3
"""HEBAT helper: discover the configured runtime; GET-only account reads, no saved secrets."""
import argparse
import importlib.util
import asyncio
import json
import math
import os
from pathlib import Path
import subprocess
import shutil
import shlex
import stat
import tempfile
import time
import sys
from urllib.parse import urlparse

BASE = 'https://hebat.elearning.unair.ac.id/'
ORIGIN = urlparse(BASE).netloc


def runtime_config_path():
    return Path.home()/'.config/hebat-unair/runtime.json'


def config_from_paths(python, server):
    if not isinstance(python,str) or not isinstance(server,str):
        raise RuntimeError('runtime_pointer_invalid')
    executable, script = Path(python).expanduser(), Path(server).expanduser()
    if not executable.is_absolute() or not script.is_absolute():
        raise RuntimeError('runtime_paths_must_be_absolute')
    if (not executable.is_file() or not os.access(executable,os.X_OK)
            or not script.is_file() or script.name!='server.py'):
        raise RuntimeError('runtime_files_unavailable')
    # Preserve the venv executable path: resolving its symlink loses the venv.
    script=script.resolve()
    return {'enabled':True,'transport':{'type':'stdio','command':str(executable),
            'args':[str(script)],'cwd':str(script.parent)}},script


def read_runtime_pointer(path):
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise RuntimeError('runtime_pointer_not_private')
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd) as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise RuntimeError('runtime_pointer_not_private')
            payload=json.load(stream)
    except (OSError,ValueError):
        raise RuntimeError('runtime_pointer_invalid') from None
    if (not isinstance(payload,dict) or set(payload)!={'version','python','server'}
            or type(payload['version']) is not int or payload['version']!=1):
        raise RuntimeError('runtime_pointer_invalid')
    config_from_paths(payload['python'],payload['server'])
    return payload


def bind_runtime(python,server):
    c,script=config_from_paths(python,server)
    payload={'version':1,'python':c['transport']['command'],'server':str(script)}
    path=runtime_config_path()
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    if path.parent.is_symlink() or path.parent.stat().st_mode & 0o077:
        raise RuntimeError('runtime_pointer_not_private')
    if path.exists() or path.is_symlink():
        if read_runtime_pointer(path)!=payload:
            raise RuntimeError('runtime_binding_conflict')
        return {'runtime_bound':True,'changed':False,'config_path':str(path)}
    fd,temporary=tempfile.mkstemp(prefix='.runtime-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(payload,stream,ensure_ascii=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        try:
            os.link(temporary,path)
            changed=True
        except FileExistsError:
            if read_runtime_pointer(path)!=payload:
                raise RuntimeError('runtime_binding_conflict')
            changed=False
    finally:
        os.unlink(temporary)
    return {'runtime_bound':True,'changed':changed,'config_path':str(path)}


def config():
    path=runtime_config_path()
    if path.exists() or path.is_symlink():
        payload=read_runtime_pointer(path)
        return config_from_paths(payload['python'],payload['server'])
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('runtime_not_configured: jalankan bind-runtime --python PATH --server PATH; tidak perlu akun ulang.')
    r = subprocess.run([codex, 'mcp', 'get', 'hebat', '--json'], capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise RuntimeError('MCP hebat belum ditemukan; baca references/connection.md. Tidak ada konfigurasi yang diubah.')
    c = json.loads(r.stdout)
    if not c.get('enabled', True):
        raise RuntimeError('MCP hebat terdaftar tetapi disabled; tidak diaktifkan otomatis.')
    t = c['transport']
    if t['type'] != 'stdio':
        raise RuntimeError('Transport berubah; gunakan tool native dan periksa konfigurasi sebelum melanjutkan.')
    args = t.get('args') or []
    candidates = [Path(x) for x in args if x.endswith('server.py')]
    if not candidates or not candidates[0].is_file() or not Path(t['command']).is_file():
        raise RuntimeError('Runtime/server pada konfigurasi tidak tersedia; baca references/connection.md.')
    return c, candidates[0].resolve()


_spec = importlib.util.spec_from_file_location('hebat_reader', Path(__file__).with_name('reader.py'))
data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(data)
DOM, Node, safe_url = data.DOM, data.Node, data.safe_url


async def handshake(c):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    t=c['transport']
    params=StdioServerParameters(command=t['command'],args=t.get('args') or [],cwd=t.get('cwd'))
    async with stdio_client(params) as (reader,writer):
        async with ClientSession(reader,writer) as session:
            await session.initialize()
            listed=await session.list_tools()
            result=await session.call_tool('hebat_status',{})
            text='\n'.join(x.text for x in result.content if hasattr(x,'text'))
            try: status=json.loads(text)
            except ValueError: status={'message':text}
            return {'mcp_connected':True,'tools':[x.name for x in listed.tools],'account':status}



def launch_login(c, server_path, wait_seconds=8, purpose="login"):
    """Ask LaunchServices to open a local script; never control Terminal's UI."""
    login_script = server_path.parent / 'login.py'
    if not login_script.is_file():
        raise RuntimeError('login.py tidak ditemukan di sebelah server aktif; tidak memakai launcher dari instalasi lain.')
    app = Path('/System/Applications/Utilities/Terminal.app')
    if not app.is_dir():
        return {'login_state':'terminal_app_missing','launch_requested':False,
                'terminal_started_verified':False,'authenticated':None}
    folder = Path(tempfile.mkdtemp(prefix='hebat-login-', dir='/private/tmp'))
    folder.chmod(0o700)
    receipt = folder / 'receipt.json'
    launcher = folder / ('Setup-Keychain-HEBAT.command' if purpose=='setup-keychain' else 'Login-HEBAT.command')
    # All interpolated values are locally resolved paths, shell-quoted; no credentials.
    helper = Path(__file__).resolve()
    python = str(Path(sys.executable).absolute())
    command = ' '.join(shlex.quote(x) for x in [python,str(helper),'terminal-login','--receipt',str(receipt),'--purpose',purpose,
                        '--python',c['transport']['command'],'--server',str(server_path)])
    launcher.write_text('#!/bin/zsh\numask 077\n'+command+'\nprintf "\\n"\nread -r "?Tekan Enter untuk menutup jendela ini."\n')
    launcher.chmod(0o700)
    try:
        launched = subprocess.run(['/usr/bin/open','-a',str(app),str(launcher)],
            capture_output=True,text=True,timeout=15)
    except subprocess.TimeoutExpired:
        return {'login_state':'launch_timeout','launch_requested':False,
                'terminal_started_verified':False,'authenticated':None,
                'next_action':'Periksa kondisi host; jangan mencoba kontrol GUI Terminal.'}
    if launched.returncode:
        reason = launched.stderr.strip()
        environmental = any(x in reason for x in ['-10827','kLSNoExecutableErr','Unable to find application'])
        return {'login_state':'host_execution_required' if environmental else 'launch_failed',
                'launch_requested':False,'terminal_started_verified':False,'authenticated':None,
                'exit_code':launched.returncode,
                'reason':reason[:1000],
                'next_action':'Gunakan mekanisme izin shell/host yang tersedia satu kali jika belum ditolak pengguna atau kebijakan; jangan memakai Computer Use untuk Terminal.'}
    deadline = time.monotonic()+wait_seconds
    last = {}
    while time.monotonic()<deadline:
        try:
            data = json.loads(receipt.read_text())
            if data.get('phase') in ('terminal_started','login_script_finished','login_runtime_error'):
                last = data; break
        except (FileNotFoundError,ValueError):
            pass
        time.sleep(.1)
    started = bool(last)
    state = {'terminal_started':'awaiting_user_login','login_script_finished':'login_finished_needs_check','login_runtime_error':'login_runtime_error'}.get(last.get('phase'),'launch_requested_unverified')
    return {'login_state':state,
            'launch_requested':True,'terminal_started_verified':started,'authenticated':None,
            'receipt_phase':last.get('phase'),
            'next_action':{'awaiting_user_login':'Pengguna isi NIM/password di Terminal lalu periksa check lagi.',
                'login_finished_needs_check':'Proses login selesai; verifikasi akun melalui check sebelum membaca tugas.',
                'login_runtime_error':'Terminal mulai tetapi runtime login gagal; periksa konfigurasi, jangan meminta kredensial lagi.'}.get(state,
                'LaunchServices menerima permintaan, tetapi proses Terminal belum memberi tanda mulai. Jangan mengklaim jendela sudah terlihat.')}


def terminal_login(receipt_path,purpose='login',python=None,server=None):
    """Runs only inside the user's Terminal. Never capture stdin or password."""
    os.umask(0o077)
    receipt = Path(receipt_path)
    def write(phase, **values):
        tmp=receipt.with_suffix('.tmp')
        tmp.write_text(json.dumps({'phase':phase,'pid':os.getpid(),**values}))
        tmp.chmod(0o600);tmp.replace(receipt)
    write('terminal_started')
    print('PENGATURAN KEYCHAIN HEBAT — simpan akun sekali untuk login otomatis.' if purpose=='setup-keychain' else 'Login HEBAT UNAIR — masukkan akun langsung di Terminal.')
    print('Password tidak ditampilkan. Jangan kirim password atau cookie ke chat.\n',flush=True)
    try:
        c,server_path=config_from_paths(python,server) if python is not None else config()
        login_script=server_path.parent/'login.py'
        if not login_script.is_file():raise RuntimeError('login.py tidak tersedia pada runtime aktif.')
        result=subprocess.run([c['transport']['command'],str(login_script)],cwd=str(server_path.parent))
        write('login_script_finished',exit_code=result.returncode)
        print('\nKembali ke chat dan beri tahu hasil login. Status akun akan diperiksa lagi.')
        return result.returncode
    except Exception as e:
        write('login_runtime_error',error_type=type(e).__name__)
        print('Runtime login tidak dapat dijalankan. Beri tahu pesan ini tanpa kredensial.')
        return 1


def main():
    p=argparse.ArgumentParser(description='HEBAT lokal: prioritas ringkas, detail, dan audit Assignment; Keychain tetap lokal.')
    p.add_argument('action',choices=['bind-runtime','check','login','setup-keychain','refresh','courses','detail','attachment','material','priority','history','show','scan','terminal-login'])
    p.add_argument('url',nargs='?')
    scope=p.add_mutually_exclusive_group()
    scope.add_argument('--semester')
    scope.add_argument('--all-semesters',action='store_true')
    p.add_argument('--course',default='',help='Nama/kode kelas, misalnya avd praktikum i1')
    p.add_argument('--fresh',action='store_true',help='Baca ulang data kampus, tanpa memaksa login baru')
    p.add_argument('--limit',type=int)
    p.add_argument('--offset',type=int,default=0)
    p.add_argument('--overdue-limit',type=int,default=3)
    p.add_argument('--kind',choices=['priority','scan','history'],default='priority')
    p.add_argument('--days',type=int,default=7,help='Jendela riwayat pengumpulan, default tujuh hari')
    p.add_argument('--changed-url',help='Periksa ulang detail satu tugas yang baru diunggah/direvisi')
    p.add_argument('--recheck-index',action='store_true',help='Periksa perubahan indeks tanpa memaksa semua detail')
    p.add_argument('--full',action='store_true',help='Instruksi detail lengkap; tidak dipakai untuk scan')
    p.add_argument('--progress',action='store_true')
    p.add_argument('--output',help='Berkas tujuan privat untuk attachment; tidak menimpa berkas yang ada')
    p.add_argument('--file-type',choices=['any','pdf'],default='any',help='Jenis materi; default semua jenis')
    p.add_argument('--audit-metrics',action='store_true',help='Tambahkan hitungan akses dan durasi tahap operasi ini')
    p.add_argument('--receipt',help=argparse.SUPPRESS)
    p.add_argument('--purpose',default='login',choices=['login','setup-keychain'],help=argparse.SUPPRESS)
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    p.add_argument('--python',dest='runtime_python',help='Python absolut untuk bind-runtime')
    p.add_argument('--server',dest='runtime_server',help='server.py absolut untuk bind-runtime')
    a=p.parse_args()
    if bool(a.runtime_python)!=bool(a.runtime_server):p.error('--python dan --server harus berpasangan')
    if a.action=='bind-runtime':
        if not a.runtime_python:p.error('bind-runtime membutuhkan --python dan --server')
        print(json.dumps(bind_runtime(a.runtime_python,a.runtime_server),ensure_ascii=False))
        return 0
    if a.runtime_python and not (a.worker or a.action=='terminal-login'):
        p.error('--python/--server hanya untuk bind-runtime atau peluncur internal')
    if a.offset<0 or (a.limit is not None and not 1<=a.limit<=50):p.error('limit harus 1–50 dan offset tidak negatif')
    if a.action=='attachment' and (not a.url or not a.output):
        p.error('attachment membutuhkan URL dan --output PATH')
    if a.output and a.action not in ('attachment','material'):
        p.error('--output hanya untuk attachment atau material')
    if a.action=='material':
        if bool(a.url)==bool(a.course.strip()):p.error('material membutuhkan salah satu: URL atau --course')
        if a.limit is not None and a.limit>5:p.error('limit material harus 1–5')
        if a.output and (not a.url or (a.limit or 1)!=1):p.error('--output material hanya untuk satu URL langsung')
        if a.url and (a.limit or 1)!=1:p.error('URL materi langsung hanya memakai limit 1')
        if a.semester or a.all_semesters:p.error('material memilih semester terbaru otomatis; gunakan URL untuk semester lain')
    if a.action=='terminal-login':
        if not a.receipt:p.error('terminal-login membutuhkan receipt lokal')
        return terminal_login(a.receipt,a.purpose,a.runtime_python,a.runtime_server)
    c,server_path=config_from_paths(a.runtime_python,a.runtime_server) if a.runtime_python else config()
    if a.action in ('login','setup-keychain'):
        result=launch_login(c,server_path,purpose=a.action)
    elif not a.worker:
        args=[x for x in sys.argv[1:] if x!='--worker']
        return subprocess.run([c['transport']['command'],str(Path(__file__).resolve()),*args,'--worker',
                               '--python',c['transport']['command'],'--server',str(server_path)]).returncode
    elif a.action=='check':
        result=asyncio.run(handshake(c))
        result['checked_at']=data.stamp()
        result['build_id']=data.BUILD_ID
        print(json.dumps(result,ensure_ascii=False))
        return 0 if result.get('account',{}).get('authenticated') else 1
    else:
        sys.path.insert(0,str(server_path.parent))
        import auth
        if a.action=='refresh':
            result=auth.status(force=True)
        else:
            def progress(message):
                if a.progress:print(message,file=sys.stderr,flush=True)
            reader=data.Reader(auth,fresh=a.fresh,progress=progress)
            try:
                term=None if a.all_semesters else a.semester
                if a.action=='courses':
                    items=reader.courses()
                    if term:items=[x for x in items if data.semester(x['name'])==term]
                    if a.course:items=data.course_candidates(items,a.course)
                    result={'reader_version':data.VERSION,'checked_at':reader.course_checked_at,'courses':items,
                            'coverage':'Pilihan kalender dan tautan dashboard; label yang berakhiran ... dipendekkan sumber.',
                            'from_cache':reader.pages_read==0,'pages_read_this_run':reader.pages_read,'cache_hits':reader.cache.hits}
                elif a.action=='detail':
                    if not a.url:p.error('detail membutuhkan URL tugas')
                    result=data.compact_detail(reader.detail(a.url),1000000 if a.full else 6000)
                    result['pages_read_this_run']=reader.pages_read
                    result['cache_hits']=reader.cache.hits
                elif a.action=='attachment':
                    result=reader.attachment(a.url,a.output)
                elif a.action=='material':
                    result=reader.material(course_query=a.course,url=a.url,limit=a.limit or 1,
                                           file_type=a.file_type,output=a.output)
                elif a.action=='priority':
                    result=data.compact_result(reader.priority(
                        term=term if (a.semester or a.all_semesters) else 'auto',
                        course_query=a.course,limit=a.limit or 5,overdue_limit=a.overdue_limit))
                elif a.action=='show':
                    result=data.compact_result(reader.show(a.kind),a.limit or 20,a.offset)
                elif a.action=='history':
                    result=data.compact_result(reader.history(days=a.days,term=term,course_query=a.course,
                        changed_url=a.changed_url,recheck_index=a.recheck_index),a.limit or 20,a.offset)
                else:
                    result=data.compact_result(reader.scan(term=term,course_query=a.course),a.limit or 20,a.offset)
                if a.audit_metrics:
                    result['metrics']=reader.run_metrics()
            except Exception as error:
                if a.audit_metrics:
                    error.hebat_audit_metrics=reader.run_metrics()
                raise
    result.setdefault('checked_at',data.stamp())
    result.setdefault('build_id',data.BUILD_ID)
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return 1 if a.action=='material' and (result.get('error') or not result.get('materials')) else 0


def error_result(error):
    result={'complete':False,'error':data.error_code(error),'build_id':data.BUILD_ID}
    if result['error']=='use_material_for_resource_url':
        result['next_action']='Gunakan material URL atau tool hebat_material untuk halaman materi; bukan detail Assignment.'
    metrics=getattr(error,'hebat_audit_metrics',None)
    if isinstance(metrics,dict):
        result['metrics']={key:value for key,value in metrics.items()
                           if isinstance(key,str) and key.isascii() and key.replace('_','').isalnum()
                           and key==key.lower() and isinstance(value,(int,float))
                           and not isinstance(value,bool) and math.isfinite(value)}
    if hasattr(error,'status'):
        result['os_status']=error.status
        result['next_action']='Jika konteks terbatas gagal tetapi MCP native aktif, coba tool shell host yang diizinkan satu kali. Jangan minta akun ulang atau melewati penolakan izin.'
    return result


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print(json.dumps(error_result(error),ensure_ascii=False))
        sys.exit(1)
