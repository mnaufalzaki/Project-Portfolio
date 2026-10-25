#!/usr/bin/env python3
"""Build source-only local HEBAT bundles from explicit allowlists."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import zipfile

SCRIPT = Path(__file__).resolve()
RUNTIME_FILES = (
    '.gitignore', 'README.md', 'requirements.txt', 'tools/release.py', 'tools/test_release.py',
    'hebat_mcp/auth.py', 'hebat_mcp/keychain_store.py', 'hebat_mcp/login.py',
    'hebat_mcp/server.py', 'hebat_mcp/reader.py', 'hebat_mcp/test_auth.py',
)
SHARED_TESTS = ('test_reader.py', 'test_history.py', 'test_regressions.py', 'test_attachment.py', 'test_material.py')
SKILL_FILES = (
    'SKILL.md', 'agents/openai.yaml', 'references/connection.md',
    'references/audit-cases.md', 'scripts/hebat.py', 'scripts/reader.py',
    'scripts/test_hebat.py', 'scripts/test_reader.py', 'scripts/test_history.py',
    'scripts/test_regressions.py', 'scripts/test_attachment.py', 'scripts/test_material.py',
    'scripts/test_runtime_binding.py',
)
CLAUDE_SKILL_FILES = tuple(name for name in SKILL_FILES if not name.startswith('agents/'))


def digest(content):
    return hashlib.sha256(content).hexdigest()


def default_roots():
    for candidate in (SCRIPT.parent, SCRIPT.parent.parent.parent):
        for skill in (candidate/'skills/hebat-unair',candidate/'skill'):
            if (candidate/'runtime').is_dir() and skill.is_dir():
                return candidate/'runtime',skill
    return SCRIPT.parent.parent, Path.home()/'.codex/skills/hebat-unair'


def locations(root=None, runtime_root=None, skill_root=None):
    default_runtime, default_skill = ((Path(root)/'runtime', Path(root)/'skill')
                                      if root is not None else default_roots())
    return (Path(runtime_root or default_runtime).resolve(),
            Path(skill_root or default_skill).resolve())


def source_bytes(base, relative):
    path = base/relative
    if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
        raise ValueError('source_path_outside_root: '+relative)
    if not path.is_file():
        raise ValueError('source_file_missing: '+relative)
    return path.read_bytes()


def source_entries(root=None, runtime_root=None, skill_root=None):
    """Only these source paths can enter a bundle; never walk account folders."""
    runtime_path, skill_path = locations(root, runtime_root, skill_root)
    runtime = {name: source_bytes(runtime_path, name) for name in RUNTIME_FILES}
    runtime.update({'hebat_mcp/'+name: source_bytes(skill_path, 'scripts/'+name)
                    for name in SHARED_TESTS})
    skill = {'hebat-unair/'+name: source_bytes(skill_path, name) for name in SKILL_FILES}
    if skill_path==runtime_path.parent/'skills/hebat-unair':
        for name in ('LICENSE','NOTICE.md'):
            content=source_bytes(runtime_path.parent,name)
            runtime[name]=content
            skill['hebat-unair/'+name]=content
    return {'HEBAT-Keychain-Runtime.zip': runtime, 'hebat-unair-skill.zip': skill}


def manifest(entries):
    return json.dumps({'format': 1, 'source_sha256': {name: digest(content)
                      for name, content in sorted(entries.items())}},
                      indent=2, sort_keys=True).encode()+b'\n'


def archive_bytes(entries):
    """Stable metadata makes equal source produce equal ZIP bytes."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted({**entries, 'BUILD-MANIFEST.json': manifest(entries)}.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return stream.getvalue()


def validate_copies(root=None, runtime_root=None, skill_root=None):
    runtime_path, skill_path = locations(root, runtime_root, skill_root)
    canonical = source_bytes(runtime_path, 'hebat_mcp/reader.py')
    copy = source_bytes(skill_path, 'scripts/reader.py')
    if canonical != copy:
        raise ValueError('reader_copy_differs_from_canonical_runtime')


def claude_destination(path, skill_path):
    target=Path(path).expanduser()
    if target.is_symlink() or target.resolve()==skill_path.resolve():
        raise ValueError('claude_skill_destination_invalid')
    return target.resolve()


def sync_claude_skill(skill_path, destination):
    target=claude_destination(destination,skill_path)
    sources={name:source_bytes(skill_path,name) for name in CLAUDE_SKILL_FILES}
    for name in sources:
        path=target/name
        if path.is_symlink() or not path.resolve().is_relative_to(target):
            raise ValueError('claude_skill_path_outside_root: '+name)
    for name,content in sources.items():
        path=target/name
        if path.is_file() and path.read_bytes()==content:
            continue
        path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix='.hebat-skill-',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            try:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def check(root=None, output_dir=None, runtime_root=None, skill_root=None, claude_skill_root=None):
    runtime_path, skill_path = locations(root, runtime_root, skill_root)
    validate_copies(runtime_root=runtime_path, skill_root=skill_path)
    entries = source_entries(runtime_root=runtime_path, skill_root=skill_path)
    if claude_skill_root is not None:
        target=claude_destination(claude_skill_root,skill_path)
        for name in CLAUDE_SKILL_FILES:
            if source_bytes(target,name)!=source_bytes(skill_path,name):
                raise ValueError('claude_skill_copy_differs: '+name)
    for sources in entries.values():
        for name, content in sources.items():
            if name.endswith('.py'):
                ast.parse(content, filename=name)
    if output_dir is not None:
        for name, sources in entries.items():
            path = Path(output_dir)/name
            if not path.is_file():
                raise ValueError('distribution_archive_missing: '+name)
            expected = {**sources, 'BUILD-MANIFEST.json': manifest(sources)}
            with zipfile.ZipFile(path) as archive:
                if set(archive.namelist()) != set(expected):
                    raise ValueError('distribution_entries_differ: '+name)
                if len(archive.namelist()) != len(expected):
                    raise ValueError('distribution_duplicate_entries: '+name)
                if any(archive.read(member) != content for member, content in expected.items()):
                    raise ValueError('distribution_source_differs: '+name)
    return {'source_only': True, 'reader_sha256': digest(source_bytes(runtime_path, 'hebat_mcp/reader.py')),
            'archive_source_counts': {name:len(sources) for name,sources in entries.items()},
            'archives_checked': output_dir is not None,
            **({'claude_skill_checked':True} if claude_skill_root is not None else {})}


def build(root=None, output_dir=None, runtime_root=None, skill_root=None, claude_skill_root=None):
    runtime_path, skill_path = locations(root, runtime_root, skill_root)
    if output_dir is not None:
        destination = Path(output_dir)
    elif runtime_path.name == 'runtime' and skill_path == runtime_path.parent/'skills/hebat-unair':
        destination = runtime_path.parent/'dist'
    elif runtime_path.name == 'runtime' and skill_path == runtime_path.parent/'skill':
        destination = runtime_path.parent.parents[1]/'outputs'
    else:
        destination = runtime_path/'dist'
    canonical = source_bytes(runtime_path, 'hebat_mcp/reader.py')
    copy = skill_path/'scripts/reader.py'
    if copy.is_symlink() or not copy.resolve().is_relative_to(skill_path):
        raise ValueError('reader_copy_outside_skill_root')
    if copy.read_bytes() != canonical:
        with tempfile.NamedTemporaryFile(prefix='.reader-sync-', dir=copy.parent, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(canonical)
                stream.flush()
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(copy)
        finally:
            temporary.unlink(missing_ok=True)
    check(runtime_root=runtime_path, skill_root=skill_path)
    if claude_skill_root is not None:
        sync_claude_skill(skill_path,claude_skill_root)
    destination.mkdir(parents=True, exist_ok=True)
    for name, sources in source_entries(runtime_root=runtime_path, skill_root=skill_path).items():
        with tempfile.NamedTemporaryFile(prefix='.hebat-bundle-', dir=destination, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(archive_bytes(sources))
                stream.flush()
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            temporary.replace(destination/name)
        finally:
            temporary.unlink(missing_ok=True)
    return check(output_dir=destination, runtime_root=runtime_path, skill_root=skill_path,
                 claude_skill_root=claude_skill_root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify copies; with --output-dir verify existing ZIPs')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--runtime-root', type=Path, help='Runtime sumber utama; default runtime yang memuat script')
    parser.add_argument('--skill-root', type=Path, help='Skill sumber; default ~/.codex/skills/hebat-unair atau layout staging')
    parser.add_argument('--claude-skill-root', type=Path, help='Sinkronkan/periksa salinan skill Claude Code; metadata Codex tidak disalin')
    arguments = parser.parse_args()
    operation = check if arguments.check else build
    result = operation(output_dir=arguments.output_dir, runtime_root=arguments.runtime_root,
                       skill_root=arguments.skill_root,claude_skill_root=arguments.claude_skill_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
