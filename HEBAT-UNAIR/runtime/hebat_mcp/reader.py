"""Structured, bounded HEBAT reads. Only parsed academic data enters the private cache."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, unquote
from zoneinfo import ZoneInfo
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import threading
import time
import uuid

VERSION = '2.3.2'
CACHE_SCHEMA = 4
BUILD_ID = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
HISTORY_RECENT_TTL = 300
HISTORY_OLDER_TTL = 3600
BASE = 'https://hebat.elearning.unair.ac.id/'
ZONE = ZoneInfo('Asia/Jakarta')
MONTHS = {name: number for number, names in enumerate([
    'january januari jan', 'february februari feb', 'march maret mar',
    'april apr', 'may mei', 'june juni jun', 'july juli jul', 'august agustus aug agu',
    'september sep', 'october oktober oct okt', 'november nov', 'december desember dec des'
], 1) for name in names.split()}
SUBMITTED = {'submitted for grading', 'submitted', 'submitted for assessment'}
COURSE_ALIASES = {'avd':('analisis visualisasi data', 'analisis'),
                  'ppl':('perangkat lunak', 'pembangunan'),
                  'pap':('arsitektur perusahaan', 'perencanaan'),
                  'kbsi':('kewirausahaan bisnis sistem informasi', 'kewirausahaan'),
                  'isit':('inovasi sistem informasi teknologi', 'inovasi')}


def submission_state(value):
    status = (value or '').strip().casefold()
    if status in SUBMITTED:
        return 'submitted'
    if any(word in status for word in ('no submission', 'not submitted', 'draft', 'belum', 'draf')):
        return 'pending'
    return 'unknown'


class Metrics:
    """Aggregate counts and durations only; never URLs, page bodies or secrets."""
    def __init__(self):
        self.lock = threading.Lock()
        self.values = {}

    def inc(self, key, amount=1):
        with self.lock:
            self.values[key] = self.values.get(key, 0) + amount

    def add_time(self, key, seconds):
        self.inc(key, seconds)

    def snapshot(self):
        with self.lock:
            return {k: round(v, 6) if isinstance(v, float) else v for k, v in self.values.items()}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def text(self):
        if self.tag in ('script', 'style', 'noscript', 'nav'):
            return ''
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c
                                for c in self.children).split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def find(self, tag):
        return [n for n in self.walk() if n is not self and n.tag == tag]


class DOM(HTMLParser):
    VOID = set('area base br col embed hr img input link meta param source track wbr'.split())

    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        child = Node(tag, attrs)
        self.stack[-1].children.append(child)
        if tag not in self.VOID:
            self.stack.append(child)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def safe_url(value):
    p = urlparse(urljoin(BASE, value))._replace(fragment='')
    if p.scheme != 'https' or p.netloc != urlparse(BASE).netloc or p.username or p.password:
        raise ValueError('untrusted_origin')
    q = parse_qs(p.query, keep_blank_values=True)
    if p.path == '/my/' and not q:
        return p.geturl()
    if p.path in ('/course/view.php', '/mod/assign/index.php', '/mod/assign/view.php'):
        if set(q) == {'id'} and len(q['id']) == 1 and q['id'][0].isdigit():
            return p.geturl()
    if p.path == '/course/overview.php' and set(q) in ({'id'}, {'id', 'expand[]'}):
        if len(q.get('id', [])) == 1 and q['id'][0].isdigit() and q.get('expand[]', ['assign']) == ['assign']:
            return p.geturl()
    raise ValueError('read_route_not_allowed')


def title(dom):
    return next((n.text().removesuffix(' | HEBAT') for n in dom.find('title')), '')


def stamp():
    return datetime.now(ZONE).isoformat(timespec='seconds')


def semester(name):
    match = re.search(r'\b(20\d{2})(Ganjil|Genap)\b', name, re.I)
    return match.group(1)+match.group(2).title() if match else None


def latest_semester(courses):
    terms = {semester(c['name']) for c in courses} - {None}
    return max(terms, key=lambda s: (int(s[:4]), s.endswith('Genap'))) if terms else None


def expanded_course_query(query):
    query = query.casefold().strip()
    for alias, (words, _) in COURSE_ALIASES.items():
        query = re.sub(r'\b'+alias+r'\b', words, query)
    return query


def course_matches(name, query):
    if not query:
        return True
    text = name.casefold()
    query = expanded_course_query(query)
    for word in query.split():
        if word in ('teo', 'teori'):
            if 'praktik' in text:
                return False
        elif word in ('prak', 'praktikum'):
            if 'praktik' not in text:
                return False
        elif not re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)', text):
            return False
    return True


def course_candidates(courses, query=''):
    """Reject incompatible title prefixes; retain labels too short to resolve safely."""
    query = query.casefold().strip()
    if not query:
        return list(courses)
    query_words = set(re.findall(r'\w+', query))
    anchors = {prefix for alias, (words, prefix) in COURSE_ALIASES.items()
               if re.search(r'\b'+alias+r'\b', query) or set(words.split()) <= query_words}
    result = []
    for course in courses:
        if query.isdigit():
            if course['id'] == query:
                result.append(course)
            continue
        name = course['name']
        if course_matches(name, query):
            result.append(course)
            continue
        if not name.rstrip().endswith(('...', '…')):
            continue
        parts = re.split(r'\s+-\s+', name)
        offset = 2 if len(parts)>1 and re.fullmatch(r'[A-Za-z]+[0-9]+', parts[1]) else 1
        prefix = re.match(r'\w+', parts[offset]) if len(parts)>offset else None
        unresolved = prefix is None or (prefix[0].isupper() and len(parts[offset])<12)
        if not anchors or unresolved or any(anchor.startswith(prefix[0].casefold()) for anchor in anchors):
            result.append(course)
    return result


def material_index(dom, course, validate):
    """Resources in section/activity order, never navigation or Assignment uploads."""
    main = next((n for n in dom.walk() if n.attrs.get('id') == 'region-main'), None)
    main = main or next((n for n in dom.walk() if n.tag == 'main' or n.attrs.get('role') == 'main'), dom)
    sections = [n for n in main.walk() if re.fullmatch(r'section-[0-9]+', n.attrs.get('id', ''))]
    sections.sort(key=lambda n: int(n.attrs['id'].split('-')[1]))
    entries, seen = [], set()
    for section in sections or [main]:
        label = section.attrs.get('data-sectionname') or next((n.text() for n in section.walk()
                 if n.tag in ('h2', 'h3', 'h4') and 'sectionname' in n.attrs.get('class', '')), '')
        blocks = [n for n in section.walk() if 'activity' in n.attrs.get('class', '').split()
                  and 'resource' in n.attrs.get('class', '').split()]
        for block in blocks or [section]:
            for link in block.find('a'):
                candidate = urljoin(BASE, link.attrs.get('href', ''))
                if urlparse(candidate).path != '/mod/resource/view.php':
                    continue
                try:
                    url = validate(candidate)
                except (ValueError, RuntimeError):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                icons = ' '.join(n.attrs.get('src', '') for n in block.find('img'))
                hint = ('pdf' if '/f/pdf' in icons or re.search(r'\bPDF\b', block.text())
                        else 'other' if re.search(r'/f/(?:powerpoint|word|spreadsheet)|\b(?:PPTX?|DOCX?|XLSX?)\b', icons+' '+block.text(), re.I)
                        else 'unknown')
                entries.append({'course_id':course['id'], 'course':course['name'], 'title':re.sub(r'\s+(?:File|Berkas)$', '', link.text()),
                                'section':label, 'source_url':url, 'file_type_hint':hint})
    return list(reversed(entries))


def material_file_link(dom, base, validate):
    embedded, links = {}, {}
    for node in dom.walk():
        attr = 'src' if node.tag in ('iframe', 'embed') else 'data' if node.tag == 'object' else 'href' if node.tag == 'a' else None
        value = node.attrs.get(attr, '') if attr else ''
        if not value:
            continue
        url = urljoin(base, value)
        if node.tag == 'a' and not urlparse(url).path.startswith('/pluginfile.php/'):
            continue
        target = validate(url)
        # Validate first: only approved forcedownload variants may share one identity.
        identity = urlparse(target)._replace(query='', fragment='').geturl()
        (links if node.tag == 'a' else embedded).setdefault(identity, target)
    candidates = embedded or links
    if len(candidates) != 1:
        raise ValueError('ambiguous_material_files' if candidates else 'material_file_not_found')
    return next(iter(candidates.values()))


def is_administrative(entry):
    return bool(re.search(r'^(?:wadah (?:pengumpulan )?)?surat (?:ijin|izin)\b', entry['title'].strip(), re.I))


def parse_date(value, term=None):
    """Only index sorting may infer a year. Detail dates require an explicit year."""
    value = value.strip()
    match = re.search(r'(\d{1,2})\s+([A-Za-z]+)(?:\s+(20\d{2}))?,?\s+(\d{1,2})[:.](\d{2})(?:\s*(AM|PM))?', value, re.I)
    if not match or match[2].lower() not in MONTHS:
        return None
    day, month = int(match[1]), MONTHS[match[2].lower()]
    if match[3]:
        year = int(match[3])
    elif term:
        year = int(term[:4]) + (term.endswith('Genap') or month <= 1)
    else:
        return None
    hour, minute = int(match[4]), int(match[5])
    if match[6]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match[6].upper() == 'PM' else 0)
    try:
        return datetime(year, month, day, hour, minute, tzinfo=ZONE)
    except ValueError:
        return None


def parse_courses(dom):
    found = {}
    for select in dom.find('select'):
        if 'course' not in str(select.attrs).lower():
            continue
        for option in select.find('option'):
            ident = option.attrs.get('value', '')
            name = option.attrs.get('title') or option.attrs.get('data-fullname') or option.text()
            if ident.isdigit() and ident != '1' and name and name.lower() != 'all courses':
                found[ident] = {'id': ident, 'name': name, 'url': BASE+'course/view.php?id='+ident}
    for link in dom.find('a'):
        try:
            url = safe_url(link.attrs.get('href', ''))
        except ValueError:
            continue
        if urlparse(url).path != '/course/view.php':
            continue
        ident = parse_qs(urlparse(url).query)['id'][0]
        name = link.attrs.get('title') or link.text()
        if ident not in found or len(name) > len(found[ident]['name']):
            found[ident] = {'id': ident, 'name': name, 'url': url}
    if not found:
        raise ValueError('course_list_not_parsed')
    return list(found.values())


def parse_index(dom, course):
    entries = []
    full_name = title(dom).removeprefix('Course activities: ')
    if not semester(full_name):
        full_name = course['name']
    for row in dom.find('tr'):
        cells = [n for n in row.children if isinstance(n, Node) and n.tag in ('td', 'th')]
        links = [a for a in row.find('a') if urlparse(urljoin(BASE, a.attrs.get('href', ''))).path == '/mod/assign/view.php']
        if not links:
            continue
        if len(cells) < 3:
            raise ValueError('assignment_index_structure_changed')
        entries.append({'course_id': course['id'], 'course': full_name,
                        'title': links[0].text(), 'url': safe_url(links[0].attrs['href']),
                        'index_due': cells[1].text(), 'index_status': cells[2].text()})
    empty_confirmed = bool(re.search(r'no assignments|no instances|there are no (?:assignments|activities)|no activities|tidak ada (?:tugas|aktivitas)', dom.text(), re.I))
    return {'course': {'id': course['id'], 'name': full_name, 'url': course['url']},
            'entries': entries, 'empty_confirmed': empty_confirmed,
            'warning': None if entries or empty_confirmed else 'Indeks tanpa tugas belum dapat dikonfirmasi: '+course['id']}


def parse_detail(dom, url):
    # Moodle uses div[role=main], not necessarily an HTML <main> element.
    content = next((n for n in dom.walk() if n.attrs.get('id') == 'region-main'), None)
    content = content or next((n for n in dom.walk() if n.tag == 'main' or n.attrs.get('role') == 'main'), dom)
    rows = {}
    for row in content.find('tr'):
        cells = [n for n in row.children if isinstance(n, Node) and n.tag in ('td', 'th')]
        if len(cells) == 2:
            key = cells[0].text()
            if key not in ('Submission comments', 'Komentar pengumpulan'):
                rows[key] = cells[1].text()
    text = content.text()
    due_match = re.search(r'\bDue:\s*([^\n]*?\d{1,2}:\d{2}(?:\s*[AP]M)?)', text, re.I)
    original = rows.get('Due date') or rows.get('Tanggal jatuh tempo') or (due_match[1] if due_match else None)
    extension = rows.get('Extension due date') or rows.get('Extension granted until')
    effective = extension or original
    parsed = parse_date(effective or '')
    intro = next((n for n in content.walk() if n.attrs.get('id') == 'intro'), None)
    instructions = intro.text() if intro is not None else text.split('Submission status')[0]
    if not intro:
        instructions = re.sub(r'^.*?Completion requirements\s*', '', instructions)
    links = []
    intro_links = {id(link) for link in intro.find('a')} if intro else set()
    for link in content.find('a'):
        p = urlparse(urljoin(BASE, link.attrs.get('href', '')))
        try:
            query = parse_qs(p.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            continue
        allowed_query = not p.query or query in ({'forcedownload': ['0']}, {'forcedownload': ['1']})
        if p.scheme == 'https' and p.netloc == urlparse(BASE).netloc and p.path.startswith('/pluginfile.php/') and allowed_query:
            if id(link) in intro_links or '/mod_assign/introattachment/' in p.path or '/mod_assign/intro/' in p.path:
                source = 'instruction'
            elif '/assignsubmission_' in p.path:
                source = 'submission'
            elif '/assignfeedback_' in p.path:
                source = 'feedback'
            else:
                source = 'unknown'
            links.append({'name': link.text(), 'url': p._replace(fragment='').geturl(), 'source': source})
    group = None
    if re.search(r'perwakilan|wakil kelompok|satu (?:orang|anggota).*kelompok|salah satu anggota'
                 r'|\bpengumpulan\b[^.!?;]{0,160}\b(?:cukup|hanya)\b[^.!?;]{0,80}'
                 r'(?:diwakil(?:i|kan)|oleh\s+ketua\s+(?:tim|kelompok))', instructions, re.I):
        group = 'representative'
    if re.search(r'setiap (?:mahasiswa|anggota)|masing.masing (?:mahasiswa|anggota)|upload.*sendiri', instructions, re.I):
        group = 'uncertain' if group else 'each_student'
    return {'title': title(dom), 'url': safe_url(url), 'due_full': effective,
            'due_iso': parsed.isoformat() if parsed else None, 'original_due': original,
            'extension_due': extension, 'cutoff': rows.get('Cut-off date'),
            'status': rows.get('Submission status') or rows.get('Status pengumpulan'),
            'grading_status': rows.get('Grading status') or rows.get('Status penilaian'),
            'status_rows': rows, 'instructions': instructions, 'attachment_links': links,
            'submission_rule': group}


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def aware_iso(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def string_fields(value, fields):
    return isinstance(value, dict) and all(isinstance(value.get(k), str) for k in fields)


def valid_detail(value):
    return (string_fields(value, ('title', 'url', 'instructions')) and aware_iso(value.get('checked_at'))
            and 'status' in value and 'due_iso' in value
            and (value.get('due_iso') is None or aware_iso(value['due_iso']))
            and (value.get('status') is None or isinstance(value['status'], str))
            and isinstance(value.get('status_rows'), dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in value['status_rows'].items())
            and isinstance(value.get('attachment_links'), list)
            and all(string_fields(x, ('name', 'url', 'source')) for x in value['attachment_links']))


def valid_history_item(value):
    return (string_fields(value, ('title', 'course', 'course_id', 'url'))
            and 'status' in value and (value['status'] is None or isinstance(value['status'], str))
            and aware_iso(value.get('detail_checked_at'))
            and 'last_modified_iso' in value
            and (value['last_modified_iso'] is None or aware_iso(value['last_modified_iso'])))


def valid_cache_data(key, value):
    """Validate the fields consumers dereference; corrupt JSON is a cache miss."""
    if key == 'courses':
        return isinstance(value, list) and bool(value) and all(string_fields(x, ('id', 'name', 'url')) for x in value)
    if key.startswith('index-'):
        return (isinstance(value, dict) and aware_iso(value.get('checked_at'))
                and string_fields(value.get('course'), ('id', 'name', 'url'))
                and isinstance(value.get('warning'), (str, type(None)))
                and 'warning' in value and isinstance(value.get('entries'), list)
                and all(string_fields(x, ('course_id', 'course', 'title', 'url', 'index_due', 'index_status'))
                        for x in value['entries']))
    if key.startswith('detail-'):
        return valid_detail(value)
    if key == 'history-ledger':
        if not (isinstance(value, dict) and value.get('version') == 1
                and isinstance(value.get('records'), dict) and isinstance(value.get('observed'), dict)):
            return False
        return (all(isinstance(k, str) and isinstance(v, str) for k, v in value['observed'].items())
                and all(isinstance(k, str) and isinstance(v, dict) and isinstance(v.get('fingerprint'), str)
                        and finite_number(v.get('verified_at_epoch')) and 0 <= v['verified_at_epoch'] <= time.time()
                        and valid_history_item(v.get('data')) for k, v in value['records'].items()))
    if key.startswith('last-'):
        if not (isinstance(value, dict) and aware_iso(value.get('checked_at'))
                and isinstance(value.get('errors'), list) and isinstance(value.get('warnings'), list)):
            return False
        if key == 'last-priority':
            return (isinstance(value.get('query'), dict) and isinstance(value.get('source_dependencies'), dict)
                    and all(re.fullmatch(r'courses|(?:index|detail)-\d+', k) and (v is None or isinstance(v, str))
                            for k, v in value['source_dependencies'].items())
                    and all(isinstance(value.get(k), list) for k in ('upcoming', 'overdue', 'uncertain', 'administrative'))
                    and all(isinstance(x, dict) and ('detail' not in x or valid_detail(x['detail']))
                            for k in ('upcoming', 'overdue', 'uncertain', 'administrative') for x in value[k]))
        if key == 'last-history':
            return all(isinstance(value.get(k), list) and all(valid_history_item(x) for x in value[k])
                       for k in ('recent_submissions', 'unknown_modified_time', 'uncertain_status'))
        if key == 'last-scan':
            entries = value.get('non_submitted_or_uncertain')
            return (isinstance(entries, list) and all(isinstance(x, dict)
                    and ('detail' not in x or valid_detail(x['detail'])) for x in entries))
    return True


class Cache:
    def __init__(self, folder, account_id=None, metrics=None):
        self.folder = Path(folder) if folder else None
        self.account_id = account_id or (self.folder.name if self.folder else None)
        self.metrics = metrics or Metrics()
        self.hits = 0

    def prepare(self):
        if self.folder.name == 'schema-'+str(CACHE_SCHEMA):
            self.folder.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            self.folder.parent.chmod(0o700)
        self.folder.mkdir(parents=True, mode=0o700, exist_ok=True)
        self.folder.chmod(0o700)

    def read(self, key, ttl=None):
        if self.folder is None:
            return None
        started = time.perf_counter()
        try:
            payload = json.loads((self.folder/(key+'.json')).read_text())
            if (not isinstance(payload, dict) or payload.get('schema_version') != CACHE_SCHEMA
                    or payload.get('account_id') != self.account_id or not isinstance(payload.get('revision'), str)
                    or not finite_number(payload.get('fetched_at'))
                    or not valid_cache_data(key, payload.get('data'))):
                self.metrics.inc('cache_invalid')
                return None
            age = time.time()-payload['fetched_at']
            if age < 0 or (ttl is not None and age > ttl):
                self.metrics.inc('cache_expired')
                return None
            self.hits += 1
            return payload
        except (OSError, ValueError, TypeError):
            return None
        finally:
            self.metrics.add_time('cache_read_seconds', time.perf_counter()-started)

    def write(self, key, data, fetched_at=None):
        if self.folder is None:
            return
        self.prepare()
        fetched_at = time.time() if fetched_at is None else fetched_at
        if not finite_number(fetched_at) or fetched_at < 0:
            raise ValueError('cache_timestamp_invalid')
        revision = uuid.uuid4().hex
        payload = {'schema_version': CACHE_SCHEMA, 'account_id':self.account_id, 'revision':revision,
                   'fetched_at': fetched_at, 'data': data}
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
        started = time.perf_counter()
        fd, path = tempfile.mkstemp(prefix='.write-', dir=self.folder)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(path, self.folder/(key+'.json'))
        finally:
            if os.path.exists(path):
                os.unlink(path)
            self.metrics.add_time('cache_write_seconds', time.perf_counter()-started)
        return revision

    def signature(self, key):
        """A source revision identifies the exact value used, including concurrent writes."""
        payload = self.read(key)
        return payload['revision'] if payload else None

    def discard(self, key):
        if self.folder:
            try:
                (self.folder/(key+'.json')).unlink()
            except FileNotFoundError:
                pass

    @contextmanager
    def operation_lock(self, key):
        if self.folder is None:
            yield
            return
        self.prepare()
        fd = os.open(self.folder/('.'+key+'.lock'), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


class Reader:
    def __init__(self, auth, fresh=False, progress=None, cache_root=None, now=None):
        self.auth = auth
        self.fresh = fresh
        self.progress = progress or (lambda message: None)
        self.now = now or (lambda: datetime.now(ZONE))
        self.local = threading.local()
        self.lock = threading.RLock()
        self.generation = 0
        self.base_session = None
        self.renewed = False
        self.recovery_used = False
        self.pages_read = 0
        self.metrics = Metrics()
        self.started = time.perf_counter()
        self.dependencies = {}
        credentials = auth.STORE.read('credentials')
        ident = auth.account_id(credentials) if credentials else None
        self.account_id = ident
        folder = (Path(cache_root or auth.ROOT/'.cache/hebat-reader')/ident/('schema-'+str(CACHE_SCHEMA))) if ident else None
        self.cache = Cache(folder, ident, self.metrics)

    def run_metrics(self):
        return {**self.metrics.snapshot(), 'reader_pages':self.pages_read,
                'reader_total_seconds':round(time.perf_counter()-self.started, 6)}

    def measuring(self):
        return self.auth.measure(self.metrics) if hasattr(self.auth, 'measure') else nullcontext()

    def ensure_session(self):
        session, renewed = self.auth.ensure_client(expected_account_id=self.account_id)
        if self.account_id is None or self.auth.session_account_id(session) != self.account_id:
            raise self.auth.AuthError('session_account_mismatch')
        return session, renewed

    def response(self, url, attachment=False, material=False):
        """Shared identity and recovery budget for all worker requests in one operation."""
        with self.measuring():
            def fetch():
                kwargs = ({'material_route':True, 'stream':True} if material else
                          {'attachment_route':True, 'stream':True} if attachment else {})
                response = self.auth.request(self.local.session, url, **kwargs)
                if response is not None and (attachment or material):
                    started = time.perf_counter()
                    try:
                        chunks = iter(response.iter_content(chunk_size=65536))
                        parts, size = [], 0
                        while size < 65536:
                            chunk = next(chunks, None)
                            if chunk is None:
                                break
                            parts.append(chunk)
                            size += len(chunk)
                        prefix = b''.join(parts)
                    except Exception:
                        response.close()
                        raise self.auth.AuthError('network_unavailable') from None
                    finally:
                        self.metrics.add_time('stream_read_seconds', time.perf_counter()-started)
                    text = prefix[:65536].decode('utf-8', errors='ignore')
                    html = ('html' in response.headers.get('Content-Type', '').lower()
                            or prefix.lstrip().startswith(b'<'))
                    if (html and re.search(r"\bname\s*=\s*['\"]?(?:logintoken|username)\b", text, re.I)
                            and re.search(r"\bname\s*=\s*['\"]?password\b", text, re.I)):
                        response.close()
                        return None
                    response._hebat_prefix = prefix
                    response._hebat_chunks = chunks
                return response
            with self.lock:
                if self.base_session is None:
                    self.base_session, self.renewed = self.ensure_session()
                if getattr(self.local, 'generation', -1) != self.generation:
                    self.local.session = self.auth.session_from(self.auth.serialize(self.base_session))
                    self.local.generation = self.generation
                generation = self.generation
            response = fetch()
            if response is None:
                with self.lock:
                    if generation == self.generation:
                        if self.recovery_used or self.renewed:
                            raise self.auth.AuthError('session_recovery_limit')
                        self.recovery_used = True
                        self.metrics.inc('session_recoveries')
                        self.base_session, renewed = self.ensure_session()
                        self.renewed = self.renewed or renewed
                        self.generation += 1
                    self.local.session = self.auth.session_from(self.auth.serialize(self.base_session))
                    self.local.generation = self.generation
                response = fetch()
                if response is None:
                    raise self.auth.AuthError('session_or_page_access_rejected')
            return response

    def attachment(self, url, output):
        if urlparse(urljoin(BASE, url)).path == '/mod/resource/view.php':
            return self.download_material(url, output=output)
        url = self.auth.attachment_url(url)
        return self._download(url, output)

    def download_material(self, url, output=None, file_type='any'):
        url = self.auth.material_url(url)
        # Explicit destinations retain the existing no-overwrite contract.
        if output is not None:
            return self._download(url, output, material=True, file_type=file_type)
        key = self.material_file_key(url)
        with self.cache.operation_lock(key):
            saved = None if self.fresh else self.cache.read(key)
            cached = self.verified_material_file(saved, url)
            if cached is not None:
                item, prefix = cached
                if file_type == 'pdf' and not prefix.startswith(b'%PDF-'):
                    raise ValueError('material_not_pdf')
                self.metrics.inc('material_files_reused')
                return {**item, 'reader_version':VERSION, 'build_id':BUILD_ID,
                        'from_cache':True, 'file_reused':True,
                        'local_verified_at':self.now().isoformat(timespec='seconds')}
            item = self._download(url, material=True, file_type=file_type)
            for address in {url, item['file_url']}:
                self.cache.write(self.material_file_key(address), item)
            self.metrics.inc('material_files_downloaded')
            return {**item, 'file_reused':False}

    def material_file_key(self, url):
        url = self.auth.material_url(url)
        if urlparse(url).path.startswith('/pluginfile.php/'):
            url = urlparse(url)._replace(query='').geturl()
        return 'material-file-'+hashlib.sha256(url.encode()).hexdigest()

    def verified_material_file(self, saved, url):
        """Reuse only account-local regular files with intact size/hash and private modes."""
        if saved is None:
            return None
        item = saved['data']
        if (not string_fields(item, ('local_path', 'sha256', 'source_url', 'file_url', 'content_type', 'url'))
                or not aware_iso(item.get('checked_at'))
                or type(item.get('bytes')) is not int or item['bytes'] <= 0
                or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])):
            return None
        try:
            keys = {self.material_file_key(item['source_url']), self.material_file_key(item['file_url'])}
            if self.material_file_key(url) not in keys:
                return None
            base = self.auth.ROOT/'.cache/hebat-materials'
            owner = base/self.account_id
            target = Path(item['local_path'])
            relative = target.relative_to(owner)
            if not target.is_absolute() or '..' in relative.parts:
                return None
            for directory in (base, owner, *target.parents[:len(relative.parts)-1]):
                if directory.is_symlink() or not directory.is_dir() or directory.stat().st_mode & 0o077:
                    return None
            fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size != item['bytes']:
                    return None
                prefix = stream.read(65536)
                digest = hashlib.sha256(prefix)
                for chunk in iter(lambda: stream.read(65536), b''):
                    digest.update(chunk)
                if digest.hexdigest() != item['sha256']:
                    return None
            return item, prefix
        except (OSError, ValueError, self.auth.AuthError):
            return None

    @staticmethod
    def check_output(target):
        if target.exists() or target.is_symlink():
            raise ValueError('attachment_output_exists')
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        if target.parent.stat().st_mode & 0o077:
            raise ValueError('attachment_directory_not_private')

    def _download(self, url, output=None, material=False, file_type='any'):
        target = Path(output).expanduser().absolute() if output else None
        if target is not None:
            self.check_output(target)
        started = time.perf_counter()
        response = self.response(url, attachment=not material, material=material)
        path = None
        try:
            source_url = url
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if material and ('html' in content_type or response._hebat_prefix.lstrip().startswith(b'<')):
                if urlparse(getattr(response, 'url', url)).path != '/mod/resource/view.php':
                    raise ValueError('attachment_html_response')
                parts, size = [response._hebat_prefix], len(response._hebat_prefix)
                try:
                    for chunk in response._hebat_chunks:
                        size += len(chunk)
                        if size > 2*1024*1024:
                            raise ValueError('material_page_too_large')
                        parts.append(chunk)
                except ValueError:
                    raise
                except Exception:
                    raise self.auth.AuthError('network_unavailable') from None
                if size > 2*1024*1024:
                    raise ValueError('material_page_too_large')
                dom = DOM(b''.join(parts).decode('utf-8', errors='replace')).root
                file_url = material_file_link(dom, getattr(response, 'url', url), self.auth.attachment_url)
                response.close()
                response = self.response(file_url, attachment=True)
                url = file_url
            content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
            if content_type in ('text/html', 'application/xhtml+xml') or response._hebat_prefix.lstrip().startswith(b'<'):
                raise ValueError('attachment_html_response')
            if file_type == 'pdf' and not response._hebat_prefix.startswith(b'%PDF-'):
                raise ValueError('material_not_pdf')
            file_url = self.auth.material_url(getattr(response, 'url', url)) if material else url
            if target is None:
                base = self.auth.ROOT/'.cache/hebat-materials'
                for directory in (base, base/self.account_id):
                    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
                    if directory.is_symlink() or directory.stat().st_mode & 0o077:
                        raise ValueError('attachment_directory_not_private')
                name = unquote(urlparse(file_url).path.rsplit('/', 1)[-1])
                if not name or name == 'view.php':
                    suffix = '.pdf' if response._hebat_prefix.startswith(b'%PDF-') else '.bin'
                    name = 'materi'+suffix
                name = re.sub(r'[^\w. -]', '_', name).strip('. ')[:160] or 'materi.bin'
                target = Path(tempfile.mkdtemp(prefix='download-', dir=base/self.account_id))/name
                self.check_output(target)
            fd, path = tempfile.mkstemp(prefix='.attachment-', dir=target.parent)
            digest, size = hashlib.sha256(), 0
            with os.fdopen(fd, 'wb') as stream:
                chunk = response._hebat_prefix
                while True:
                    if chunk:
                        stream.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    reading = time.perf_counter()
                    try:
                        chunk = next(response._hebat_chunks)
                    except StopIteration:
                        break
                    except Exception:
                        raise self.auth.AuthError('network_unavailable') from None
                    finally:
                        self.metrics.add_time('stream_read_seconds', time.perf_counter()-reading)
                stream.flush()
                os.fsync(stream.fileno())
            expected = response.headers.get('Content-Length')
            if not response.headers.get('Content-Encoding') and expected and expected.isdigit() and int(expected) != size:
                raise ValueError('attachment_length_mismatch')
            if size == 0:
                raise ValueError('attachment_empty')
            # Linking is atomic and fails if another writer has created the destination.
            os.link(path, target)
            self.metrics.inc('attachment_bytes', size)
            return {'reader_version':VERSION, 'build_id':BUILD_ID, 'checked_at':self.now().isoformat(timespec='seconds'),
                    'from_cache':False, 'url':url, 'local_path':str(target), 'bytes':size,
                    'sha256':digest.hexdigest(), 'content_type':content_type,
                    'source_url':source_url, 'file_url':file_url}
        finally:
            response.close()
            if path is not None and os.path.exists(path):
                os.unlink(path)
            self.metrics.add_time('attachment_seconds', time.perf_counter()-started)

    def material(self, course_query='', url=None, limit=1, file_type='any', output=None):
        if bool(course_query.strip()) == bool(url):
            raise ValueError('material_requires_course_or_url')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
            raise ValueError('invalid_material_limit')
        if file_type not in ('any', 'pdf'):
            raise ValueError('invalid_material_file_type')
        if url and limit != 1:
            raise ValueError('material_url_requires_limit_one')
        if output and (not url or limit != 1):
            raise ValueError('material_output_requires_single_url')
        errors, materials, candidates = [], [], []
        checked_at = self.now().isoformat(timespec='seconds')
        if url:
            candidates = [{'source_url':self.auth.material_url(url), 'title':'', 'section':'', 'course':None, 'course_id':None}]
        else:
            _, courses, _ = self.select_courses('auto')
            matches, names = [], {}
            for course in course_candidates(courses, course_query):
                dom = self.get(course['url'])
                full_name = title(dom).removeprefix('Course: ')
                resolved = dict(course, name=full_name or course['name'])
                names[course['id']] = resolved['name']
                if course['id'] == course_query or course_matches(resolved['name'], course_query):
                    matches.append((resolved, dom))
            self.remember_course_names(names)
            if len(matches) != 1:
                return {'reader_version':VERSION, 'build_id':BUILD_ID, 'checked_at':checked_at,
                        'complete':False, 'error':'ambiguous_material_course' if matches else 'no_matching_course',
                        'candidates':[c for c, _ in matches], 'materials':[]}
            course, dom = matches[0]
            candidates = material_index(dom, course, self.auth.material_url)
        for candidate in candidates:
            if len(materials) >= limit:
                break
            if file_type == 'pdf' and candidate.get('file_type_hint') == 'other':
                continue
            try:
                item = self.download_material(candidate['source_url'], output=output, file_type=file_type)
                materials.append({**candidate, **item, 'title':candidate['title'] or Path(item['local_path']).name})
            except Exception as error:
                if file_type == 'pdf' and str(error) == 'material_not_pdf':
                    continue
                errors.append({'source_url':candidate['source_url'], 'error':error_code(error)})
        return {'reader_version':VERSION, 'build_id':BUILD_ID, 'checked_at':checked_at,
                'complete':len(materials) == limit and not errors, 'materials':materials, 'errors':errors,
                'ordering':'Urutan bagian/pertemuan terakhir, lalu aktivitas terakhir; bukan tanggal unggah.',
                'warnings':[] if len(materials) == limit else ['Jumlah materi yang berhasil diambil kurang dari yang diminta.'],
                'from_cache':False, 'pages_read_this_run':self.pages_read,
                'files_reused':sum(bool(item.get('file_reused')) for item in materials),
                'files_downloaded':sum(not item.get('file_reused', False) for item in materials),
                **({'error':'material_not_found'} if not materials and not errors else {})}

    def get(self, path):
        url = safe_url(path)
        response = self.response(url)
        started = time.perf_counter()
        try:
            dom = DOM(response.text).root
        finally:
            self.metrics.add_time('parse_seconds', time.perf_counter()-started)
            if hasattr(response, 'close'):
                response.close()
        with self.lock:
            self.pages_read += 1
        return dom

    def cached(self, key, ttl, read, force=False):
        old = self.cache.read(key, ttl) if not (self.fresh or force) else None
        if old:
            self.local.last_from_cache = True
            self.local.last_fetched_at = old['fetched_at']
            self.metrics.inc('cache_reuses')
            with self.lock:
                self.dependencies[key] = old['revision']
            return copy.deepcopy(old['data'])
        self.metrics.inc('cache_misses')
        self.local.last_from_cache = False
        try:
            data = read()
        except Exception:
            self.cache.discard(key)
            raise
        fetched_at = time.time()
        revision = self.cache.write(key, data, fetched_at)
        self.local.last_fetched_at = fetched_at
        with self.lock:
            self.dependencies[key] = revision
        return data

    def courses(self):
        result = self.cached('courses', 600, lambda: parse_courses(self.get('my/')))
        entry = self.cache.read('courses', 600)
        self.course_checked_at = datetime.fromtimestamp(entry['fetched_at'], ZONE).isoformat(timespec='seconds') if entry else stamp()
        return result

    def index(self, course, force=False):
        def read():
            result = parse_index(self.get('mod/assign/index.php?id='+course['id']), course)
            result['checked_at'] = stamp()
            return result
        result = self.cached('index-'+course['id'], 120, read, force=force)
        for entry in result['entries']:
            entry['index_checked_at'] = result['checked_at']
            entry['index_fetched_at'] = self.local.last_fetched_at
        return result

    def detail(self, url, force=False):
        if urlparse(urljoin(BASE, url)).path == '/mod/resource/view.php':
            self.auth.material_url(url)
            raise ValueError('use_material_for_resource_url')
        url = safe_url(url)
        if urlparse(url).path != '/mod/assign/view.php':
            raise ValueError('assignment_url_required')
        ident = parse_qs(urlparse(url).query)['id'][0]
        def read():
            data = parse_detail(self.get(url), url)
            data['checked_at'] = stamp()
            return data
        result = self.cached('detail-'+ident, 120, read, force=force)
        result.update(reader_version=VERSION, build_id=BUILD_ID,
                      from_cache=self.local.last_from_cache,
                      cache_age_seconds=max(0, round((self.now()-datetime.fromisoformat(result['checked_at'])).total_seconds(), 1)))
        return result

    def select_courses(self, term='auto', course_query=''):
        found = self.courses()
        selected = latest_semester(found) if term == 'auto' else term
        if term == 'auto' and not selected:
            raise ValueError('semester_not_detected_choose_explicit_scope')
        scoped = [c for c in found if (not selected or semester(c['name']) == selected)]
        # Resolve shortened calendar labels from their index before course-name matching.
        return found, scoped, selected

    def remember_course_names(self, names):
        """Share verified names without extending TTL or accepting an unread revision."""
        with self.cache.operation_lock('courses'):
            cached_courses = self.cache.read('courses', 600)
            if cached_courses:
                changed = False
                for course in cached_courses['data']:
                    new_name = names.get(course['id'], course['name'])
                    if new_name.rstrip().endswith(('...', '…')) or semester(new_name) != semester(course['name']):
                        continue
                    changed |= new_name != course['name']
                    course['name'] = new_name
                if changed:
                    revision = self.cache.write('courses', cached_courses['data'], cached_courses['fetched_at'])
                    if self.dependencies.get('courses') == cached_courses['revision']:
                        self.dependencies['courses'] = revision

    def indices(self, scoped, course_query='', force=False, force_course_ids=None):
        results, errors, warnings, names = [], [], [], {}
        scoped = course_candidates(scoped, course_query)
        completed = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.index, c, force or c['id'] in (force_course_ids or set())): c for c in scoped}
            for future in as_completed(futures):
                course = futures[future]
                try:
                    result = future.result()
                    names[result['course']['id']] = result['course']['name']
                    if course_matches(result['course']['name'], course_query) or course_query == course['id']:
                        results.append(result)
                        if result['warning']:
                            warnings.append(result['warning'])
                except Exception as error:
                    errors.append({'course_id': course['id'], 'error': error_code(error)})
                completed += 1
                self.progress('Indeks kelas dibaca: '+str(completed)+'/'+str(len(scoped)))
        self.remember_course_names(names)
        return results, errors, warnings

    def effective_state(self, entry):
        """Newer direct verification wins over an older index, preserving source fields."""
        ident = parse_qs(urlparse(entry['url']).query)['id'][0]
        key = 'detail-'+ident
        detail = self.cache.read(key, 120)
        self.dependencies[key] = detail['revision'] if detail else None
        if detail and detail['fetched_at'] > entry.get('index_fetched_at', float('inf')):
            entry['candidate_due_iso'] = detail['data']['due_iso']
            return submission_state(detail['data']['status'])
        return submission_state(entry['index_status'])

    def read_details(self, entries):
        output = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.detail, x['url']): x for x in entries}
            for future in as_completed(futures):
                entry = dict(futures[future])
                try:
                    entry['detail'] = future.result()
                    if not entry['detail']['status']:
                        entry['error'] = 'submission_status_not_parsed'
                except Exception as error:
                    entry['error'] = error_code(error)
                output.append(entry)
        return output

    def priority(self, term='auto', course_query='', limit=5, overdue_limit=3):
        if not 1 <= limit <= 50 or not 0 <= overdue_limit <= 20:
            raise ValueError('invalid_result_limit')
        query = {'semester': term, 'course_query': course_query, 'limit': limit, 'overdue_limit': overdue_limit,
                 'strategy': 'priority_v2_admin_separated'}
        old = self.cache.read('last-priority', 120) if not self.fresh else None
        source_age = (self.now()-datetime.fromisoformat(old['data']['checked_at'])).total_seconds() if old else None
        dependencies = old['data'].get('source_dependencies', {}) if old else {}
        sources_match = bool(dependencies) and all(self.cache.signature(k) == v for k, v in dependencies.items())
        if old and sources_match and old['data'].get('query') == query and not old['data'].get('errors') and 0 <= source_age <= 120:
            result = old['data']
            result['from_cache'] = True
            result['cache_age_seconds'] = round(source_age, 1)
            result['pages_read_this_run'] = 0
            result['cache_hits'] = self.cache.hits
            result['build_id'] = BUILD_ID
            return result
        all_courses, scoped, selected = self.select_courses(term)
        indices, errors, warnings = self.indices(scoped, course_query)
        if not indices and not errors:
            raise ValueError('no_matching_course')
        entries = [x for i in indices for x in i['entries']]
        pending_all = [x for x in entries if self.effective_state(x) != 'submitted']
        administrative = [dict(x, note='Wadah surat izin; kewajiban pengguna belum ditentukan, bukan prioritas tugas otomatis.')
                          for x in pending_all if is_administrative(x)]
        pending = [x for x in pending_all if not is_administrative(x)]
        now = self.now()
        upcoming, overdue, uncertain = [], [], []
        for entry in pending:
            estimated = candidate_date(entry)
            if estimated is None:
                uncertain.append(entry)
            elif estimated >= now:
                upcoming.append((estimated, entry))
            else:
                overdue.append((estimated, entry))
        upcoming.sort(key=lambda x: (x[0], x[1]['url']))
        overdue.sort(key=lambda x: (x[0], x[1]['url']), reverse=True)
        queue = [e for _, e in upcoming]
        checked = []
        # Inspect a bounded first batch, then continue only if top candidates prove unsuitable.
        batch_size = max(limit, 5)
        while queue:
            batch, queue = queue[:batch_size], queue[batch_size:]
            checked.extend(self.read_details(batch))
            good = [e for e in checked if verified_bucket(e, now) == 'upcoming']
            if len(good) >= limit:
                worst = sorted(datetime.fromisoformat(e['detail']['due_iso']) for e in good)[limit-1]
                next_estimate = candidate_date(queue[0]) if queue else None
                if not queue or (next_estimate is not None and next_estimate > worst):
                    break
        additional = [e for _, e in overdue[:overdue_limit]] + uncertain[:3]
        checked.extend(self.read_details(additional))
        source_times = [i['checked_at'] for i in indices] + [e['detail']['checked_at'] for e in checked if e.get('detail')]
        result = {'reader_version': VERSION, 'build_id':BUILD_ID, 'checked_at': min(source_times) if source_times else stamp(),
                  'assembled_at': stamp(), 'course_list_checked_at': self.course_checked_at, 'timezone': str(ZONE),
                  'query': query, 'semester': selected or 'all', 'scope': 'Assignment pada kelas yang ditemukan',
                  'from_cache': self.pages_read == 0, 'course_count': len(indices), 'available_course_count': len(all_courses),
                  'assignment_count': len(entries), 'pending_index_count': len(pending_all),
                  'administrative': administrative,
                  'verified_detail_count': len(checked), 'unverified_index_count': len(pending)-len(checked),
                  'saved_locally': self.cache.folder is not None,
                  'index_complete': not errors and not warnings, 'errors': errors, 'warnings': warnings,
                  'coverage_notes': ['Kuis, forum, kegiatan tersembunyi, dan tugas di luar HEBAT tidak termasuk.',
                    'Tahun pada indeks tanpa tahun hanya diperkirakan untuk memilih kandidat; urutan hasil memakai tanggal lengkap detail.',
                    'Detail tugas lama dan tanggal tidak jelas tidak semuanya diverifikasi; tenggat perpanjangan yang tersembunyi di detail lain dapat terlewat.'],
                  'upcoming': [], 'overdue': [], 'uncertain': []}
        for entry in checked:
            bucket = verified_bucket(entry, now)
            if bucket == 'submitted':
                continue
            result[bucket].append(entry)
            if entry.get('error'):
                result['errors'].append({'url': entry['url'], 'error': entry['error']})
        result['upcoming'].sort(key=lambda e: e['detail']['due_iso'])
        result['overdue'].sort(key=lambda e: e['detail']['due_iso'], reverse=True)
        result['upcoming'] = result['upcoming'][:limit]
        result['overdue'] = result['overdue'][:overdue_limit]
        result['complete'] = (result['index_complete'] and not result['errors'] and not result['uncertain']
                              and result['unverified_index_count'] == 0)
        result['pages_read_this_run'] = self.pages_read
        result['cache_hits'] = self.cache.hits
        dependencies = dict(self.dependencies)
        for entry in entries:
            ident = parse_qs(urlparse(entry['url']).query)['id'][0]
            key = 'detail-'+ident
            if key not in dependencies:
                dependencies[key] = self.cache.signature(key)
        result['source_dependencies'] = dependencies
        self.cache.write('last-priority', result)
        return result

    def scan(self, term=None, course_query=''):
        all_courses, scoped, selected = self.select_courses(term)
        indices, errors, warnings = self.indices(scoped, course_query)
        if not indices and not errors:
            raise ValueError('no_matching_course')
        entries = [x for i in indices for x in i['entries']]
        pending = [x for x in entries if self.effective_state(x) != 'submitted']
        checked = self.read_details(pending)
        errors.extend({'url': e['url'], 'error': e['error']} for e in checked if e.get('error'))
        warnings.extend('Status pengumpulan belum dikenal pada detail: '+e['url'] for e in checked
                        if not e.get('error') and submission_state(e.get('detail', {}).get('status')) == 'unknown')
        source_times = [i['checked_at'] for i in indices] + [e['detail']['checked_at'] for e in checked if e.get('detail')]
        remaining = [e for e in checked if e.get('error')
                     or submission_state(e.get('detail', {}).get('status')) != 'submitted']
        result = {'reader_version': VERSION, 'build_id':BUILD_ID, 'checked_at': min(source_times) if source_times else stamp(),
                  'assembled_at': stamp(), 'from_cache': self.pages_read == 0, 'semester': selected or 'all',
                  'scope': 'Assignment pada kelas yang ditemukan', 'course_count': len(indices),
                  'assignment_count': len(entries), 'non_submitted_or_uncertain': remaining,
                  'complete': not errors and not warnings, 'errors': errors, 'warnings': warnings,
                  'saved_locally': self.cache.folder is not None,
                  'coverage_notes': ['Tidak termasuk kuis, forum, kegiatan tersembunyi, atau tugas di luar HEBAT.'],
                  'pages_read_this_run': self.pages_read, 'cache_hits': self.cache.hits}
        self.cache.write('last-scan', result)
        return result

    def history(self, days=7, term=None, course_query='', changed_url=None, recheck_index=False):
        """Incremental history, not an immutable log of every submission version.

        Index status/due/name changes invalidate a record immediately when checked.
        Same-status revisions require a targeted refresh or bounded detail recheck.
        """
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 366:
            raise ValueError('invalid_history_days')
        if changed_url:
            changed_url = safe_url(changed_url)
            if urlparse(changed_url).path != '/mod/assign/view.php':
                raise ValueError('assignment_url_required')
        with self.cache.operation_lock('history'):
            return self._history(days, term, course_query, changed_url, recheck_index)

    def _history(self, days, term, course_query, changed_url, recheck_index):
        now = self.now()
        cutoff = now-timedelta(days=days)
        saved = self.cache.read('history-ledger')
        ledger = saved['data'] if saved and saved['data'].get('version') == 1 else {'version':1,'records':{},'observed':{}}
        records, observed = ledger['records'], ledger['observed']
        _, scoped, selected = self.select_courses(term)
        target_courses = set()
        if changed_url:
            known = records.get(changed_url, {}).get('data', {}).get('course_id')
            if known:
                target_courses.add(known)
            else:
                for course in scoped:
                    index = self.cache.read('index-'+course['id'], 120)
                    if index and any(e['url']==changed_url for e in index['data']['entries']):
                        target_courses.add(course['id'])
        indices, errors, warnings = self.indices(scoped, course_query,
            force=recheck_index or bool(changed_url and not target_courses), force_course_ids=target_courses)
        if not indices and not errors:
            raise ValueError('no_matching_course')
        entries = [entry for index in indices for entry in index['entries']]
        by_url = {entry['url']: entry for entry in entries}
        if changed_url and changed_url not in by_url:
            raise ValueError('changed_assignment_not_in_selected_scope')
        candidates, refresh, seeded = [], [], 0
        fingerprints = {}
        for entry in entries:
            url = entry['url']
            fingerprint = history_fingerprint(entry)
            fingerprints[url] = fingerprint
            state = self.effective_state(entry)
            if state == 'pending' and url != changed_url:
                records.pop(url, None)
                continue
            candidates.append(entry)
            previous = records.get(url)
            ident = parse_qs(urlparse(url).query)['id'][0]
            canonical = self.cache.read('detail-'+ident, 120) if not self.fresh and url != changed_url else None
            if canonical and (canonical['fetched_at'] > entry.get('index_fetched_at', float('inf'))
                              or (previous and previous['fingerprint'] == fingerprint
                                  and observed.get(url) == fingerprint
                                  and canonical['fetched_at'] > previous['verified_at_epoch'])):
                records[url] = history_record(entry, canonical['data'], canonical['fetched_at'], fingerprint)
                seeded += 1
                continue
            valid = (previous and not self.fresh and url != changed_url
                     and previous['fingerprint'] == fingerprint
                     and observed.get(url) == fingerprint
                     and 0 <= time.time()-previous['verified_at_epoch'] <= history_ttl(previous['data'], now))
            if valid:
                continue
            # Bootstrap only previously unseen records from parsed detail cache.
            # A witnessed status transition must never reuse an earlier submission.
            if previous is None and url not in observed and not self.fresh and url != changed_url:
                ident = parse_qs(urlparse(url).query)['id'][0]
                detail = self.cache.read('detail-'+ident, HISTORY_OLDER_TTL)
                if detail:
                    record = history_record(entry, detail['data'], detail['fetched_at'], fingerprint)
                    age = time.time()-detail['fetched_at']
                    if (record['data']['status'] or '').casefold() in SUBMITTED and age <= history_ttl(record['data'], now):
                        records[url] = record
                        seeded += 1
                        continue
            refresh.append(entry)
        successful_refresh = 0
        failed = set()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.detail, e['url'], True): e for e in refresh}
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    detail = future.result()
                    if not detail.get('status'):
                        raise ValueError('submission_status_not_parsed')
                    records[entry['url']] = history_record(entry, detail, time.time(), fingerprints[entry['url']])
                    successful_refresh += 1
                except Exception as error:
                    # Do not present the previous value as freshly verified after a failed refresh.
                    failed.add(entry['url'])
                    records.pop(entry['url'], None)
                    errors.append({'url':entry['url'],'error':error_code(error)})
                self.progress('Detail riwayat diperiksa: '+str(successful_refresh+len(failed))+'/'+str(len(refresh)))
        changed_count = sum(url in observed and observed[url] != fp for url, fp in fingerprints.items())
        observed.update(fingerprints)
        self.cache.write('history-ledger', ledger)
        recent, unknown, uncertain_status, verification_times = [], [], [], []
        reused = 0
        refreshed_urls = {entry['url'] for entry in refresh}
        for entry in candidates:
            url = entry['url']
            if url in failed or url not in records:
                continue
            record = records[url]
            item = dict(record['data'], course=entry['course'], title=entry['title'])
            verification_times.append(item['detail_checked_at'])
            detail_state = submission_state(item['status'])
            detail_submitted = detail_state == 'submitted'
            index_submitted = submission_state(entry['index_status']) == 'submitted'
            if detail_state == 'unknown':
                uncertain_status.append(item)
                warnings.append('Status pengumpulan belum dikenal pada detail: '+url)
                continue
            if detail_submitted != index_submitted:
                warnings.append('Status detail berbeda dari indeks: '+url)
            if not detail_submitted:
                continue
            if url not in refreshed_urls:
                reused += 1
            modified = datetime.fromisoformat(item['last_modified_iso']) if item['last_modified_iso'] else None
            if modified is None or modified > now:
                unknown.append(item)
                if modified is not None:
                    warnings.append('Last modified berada di masa depan: '+url)
            elif cutoff <= modified <= now:
                recent.append(item)
        recent.sort(key=lambda item:(item['last_modified_iso'],item['url']), reverse=True)
        index_time = min((i['checked_at'] for i in indices), default=stamp())
        source_time = min([index_time, *verification_times])
        result = {'reader_version':VERSION,'build_id':BUILD_ID,'checked_at':source_time,'index_checked_at':index_time,
                  'assembled_at':self.now().isoformat(timespec='seconds'),'timezone':str(ZONE),
                  'window_start':cutoff.isoformat(),'window_end':now.isoformat(),'days':days,
                  'semester':selected or 'all','course_query':course_query,'course_count':len(indices),
                  'assignment_count':len(entries),'submitted_candidates':len(candidates),
                  'recent_submissions':recent,'unknown_modified_time':unknown,'uncertain_status':uncertain_status,
                  'detail_pages_refetched':successful_refresh,'detail_refresh_attempted':len(refresh),
                  'details_reused_count':reused,'seeded_from_detail_cache':seeded,
                  'index_changes_detected':changed_count,'from_cache':self.pages_read==0,
                  'pages_read_this_run':self.pages_read,'cache_hits':self.cache.hits,
                  'oldest_detail_checked_at':min(verification_times) if verification_times else None,
                  'newest_detail_checked_at':max(verification_times) if verification_times else None,
                  'history_refresh_policy':{'index_ttl_seconds':120,'recent_detail_ttl_seconds':HISTORY_RECENT_TTL,
                                            'older_detail_ttl_seconds':HISTORY_OLDER_TTL},
                  'complete':not errors and not warnings and not unknown and not uncertain_status,'errors':errors,'warnings':warnings,
                  'saved_locally':self.cache.folder is not None,
                  'coverage_notes':['Last modified dapat berarti unggahan awal atau revisi terakhir, bukan riwayat setiap versi.',
                    'Status indeks dicek maksimal tiap 120 detik saat diminta. Revisi dengan status sama tidak selalu mengubah indeks.',
                    'Detail yang diubah dalam tujuh hari terakhir diperiksa maksimal tiap lima menit; detail lama maksimal tiap satu jam saat diminta.',
                    'Gunakan changed_url untuk memeriksa satu tugas setelah revisi; fresh memverifikasi ulang semua kandidat.',
                    'Cakupan hanya Assignment pada kelas yang ditemukan; pengumpulan wakil kelompok di akun lain tidak tercatat di sini.']}
        result['cache_age_seconds'] = max(0, round((now-datetime.fromisoformat(source_time)).total_seconds(),1))
        self.cache.write('last-history', result)
        return result

    def show(self, kind='priority'):
        cached = self.cache.read('last-'+kind)
        if not cached:
            raise ValueError('no_saved_result')
        result = cached['data']
        result['build_id'] = BUILD_ID
        result['from_cache'] = True
        result['cache_age_seconds'] = max(0, round((self.now()-datetime.fromisoformat(result['checked_at'])).total_seconds(), 1))
        result['pages_read_this_run'] = 0
        if kind == 'history':
            metric_keys = ('detail_pages_refetched','detail_refresh_attempted','details_reused_count',
                           'seeded_from_detail_cache','index_changes_detected')
            result['source_run_metrics'] = {key:result.get(key) for key in metric_keys}
            for key in metric_keys:
                result[key] = 0
        return result


def candidate_date(entry):
    if 'candidate_due_iso' in entry:
        return datetime.fromisoformat(entry['candidate_due_iso']) if entry['candidate_due_iso'] else None
    return parse_date(entry['index_due'], semester(entry['course']))


def verified_bucket(entry, now):
    if entry.get('error'):
        return 'uncertain'
    data = entry.get('detail', {})
    state = submission_state(data.get('status'))
    if state == 'submitted':
        return 'submitted'
    if state != 'pending' or not data.get('due_iso'):
        return 'uncertain'
    return 'upcoming' if datetime.fromisoformat(data['due_iso']) >= now else 'overdue'


def history_fingerprint(entry):
    due = parse_date(entry['index_due'], semester(entry['course']))
    values = [entry['url'], entry['title'], entry['index_status'].strip().casefold(),
              due.isoformat() if due else entry['index_due']]
    return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()


def history_record(entry, detail, fetched_at, fingerprint):
    modified = detail.get('status_rows',{}).get('Last modified') or detail.get('status_rows',{}).get('Terakhir diubah')
    date = parse_date(modified or '')
    item = {'title':entry['title'],'course':entry['course'],'course_id':entry['course_id'],'url':entry['url'],
            'status':detail.get('status'),'grading_status':detail.get('grading_status'),
            'last_modified':modified,'last_modified_iso':date.isoformat() if date else None,
            'detail_checked_at':detail.get('checked_at',stamp()),'submission_rule':detail.get('submission_rule')}
    return {'fingerprint':fingerprint,'verified_at_epoch':fetched_at,'data':item}


def history_ttl(item, now):
    modified = datetime.fromisoformat(item['last_modified_iso']) if item.get('last_modified_iso') else None
    pending = (item.get('status') or '').strip().casefold() not in SUBMITTED
    return HISTORY_RECENT_TTL if pending or modified is None or modified >= now-timedelta(days=7) else HISTORY_OLDER_TTL


def compact_detail(data, max_chars=6000):
    result = {k: v for k, v in data.items() if k != 'status_rows'}
    instructions = result.get('instructions', '')
    result['instructions'] = instructions[:max_chars]
    result['instructions_truncated'] = len(instructions) > max_chars
    if result.get('submission_rule') == 'representative':
        result['note'] = 'Unggah oleh wakil kelompok; status akun ini belum membuktikan kelompok belum mengumpulkan.'
    return result


def compact_result(data, limit=20, offset=0):
    result = copy.deepcopy(data)
    result.pop('source_dependencies', None)
    for key in ('upcoming', 'overdue', 'uncertain', 'administrative', 'non_submitted_or_uncertain', 'recent_submissions', 'unknown_modified_time', 'uncertain_status'):
        if key not in result:
            continue
        entries = result[key]
        if key in ('uncertain', 'administrative', 'non_submitted_or_uncertain', 'recent_submissions', 'unknown_modified_time', 'uncertain_status'):
            result[key+'_total'] = len(entries)
            result[key] = entries[offset:offset+limit]
            result[key+'_more'] = len(entries) > offset+limit
        for entry in result[key]:
            if 'detail' in entry:
                entry['detail'] = compact_detail(entry['detail'], 500)
    result.setdefault('saved_locally', False)
    return result


def error_code(error):
    if hasattr(error, 'code'):
        return error.code
    if isinstance(error, ValueError) and re.fullmatch('[a-z_]+', str(error)):
        return str(error)
    return 'read_failed'
