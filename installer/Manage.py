#!/usr/bin/env python3
"""Offline installer for the Windows Steam build under Proton, Python 3.8+."""
import argparse
import contextlib
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import time

APP = '835430'
STATE = '.lm2chs-fixes'

def require(value, message):
    if not value:
        raise ValueError(message)

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.lm2-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        replace_file(temp, path)
        if sys.platform == 'linux':
            fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def replace_file(src, dst):
    # Windows antivirus can briefly hold a newly written game assembly.
    for attempt in range(8):
        try:
            os.replace(str(src), str(dst)); return
        except PermissionError:
            if os.name != 'nt' or attempt == 7: raise
            time.sleep(0.1 * (attempt + 1))

def atomic_json(path, obj):
    atomic_bytes(path, (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

def target(game, relative):
    parts = relative.split('/')
    require(parts and all(p not in ('', '.', '..') and '\\' not in p and ':' not in p for p in parts), 'Invalid path in manifest')
    path = game
    for part in parts:
        path = path / part
        require(not path.is_symlink(), 'Unexpected symlink: ' + str(path))
    return path

def parse_vdf(text):
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[{}]', re.sub(r'(?m)^\s*//[^\n]*', '', text))
    def obj(i, nested=False):
        result = {}
        while i < len(tokens):
            if tokens[i] == '}':
                require(nested, 'Malformed Steam library file')
                return result, i + 1
            key = re.sub(r'\\([\\"])', r'\1', tokens[i][1:-1]); i += 1
            require(i < len(tokens), 'Malformed Steam library file')
            if tokens[i] == '{': value, i = obj(i + 1, True)
            else:
                value = re.sub(r'\\([\\"])', r'\1', tokens[i][1:-1]); i += 1
            result[key] = value
        require(not nested, 'Malformed Steam library file')
        return result, i
    return obj(0)[0]

def find_game(explicit):
    if explicit:
        game = Path(explicit).expanduser().resolve()
    else:
        home = Path.home()
        roots = [home/'.local/share/Steam', home/'.steam/steam', home/'.steam/root', home/'.var/app/com.valvesoftware.Steam/.local/share/Steam']
        if os.environ.get('XDG_DATA_HOME'): roots.append(Path(os.environ['XDG_DATA_HOME'])/'Steam')
        libraries = []
        for root in roots:
            root = root.resolve()
            if root.is_dir() and root not in libraries: libraries.append(root)
            vdf = root/'steamapps/libraryfolders.vdf'
            if vdf.is_file():
                data = parse_vdf(vdf.read_text(encoding='utf-8-sig'))
                for k, v in data.get('libraryfolders', data).items():
                    p = v.get('path') if isinstance(v, dict) else v if k.isdigit() else None
                    if p:
                        lib = Path(p).expanduser().resolve()
                        if lib.is_dir() and lib not in libraries: libraries.append(lib)
        games = []
        for lib in libraries:
            acf = lib/('steamapps/appmanifest_' + APP + '.acf')
            if not acf.is_file(): continue
            app = parse_vdf(acf.read_text(encoding='utf-8-sig')).get('AppState', {})
            name = app.get('installdir', '')
            require(app.get('appid') == APP and name and name not in ('.', '..') and not any(c in name for c in '/\\:'), 'Invalid Steam app manifest')
            p = (lib/'steamapps/common'/name).resolve()
            if p.is_dir() and p not in games: games.append(p)
        if len(games) == 1: game = games[0]
        else:
            for i, p in enumerate(games, 1): print('  {}. {}'.format(i, p))
            require(sys.stdin.isatty(), 'Specify the game folder as an argument.')
            answer = input('Game folder path or list number: ').strip().strip('"\'')
            game = games[int(answer)-1] if answer.isdigit() and 1 <= int(answer) <= len(games) else Path(answer).expanduser().resolve()
    require((game/'LaMulana2.exe').is_file(), 'Windows game not found. Force Proton in Steam, download the Windows build, and start it once before installation.')
    return game

def check_running(game):
    if sys.platform != 'linux': return
    for p in Path('/proc').iterdir():
        if not p.name.isdigit(): continue
        try:
            args = (p/'cmdline').read_bytes().lower().replace(b'\\', b'/').split(b'\0')
            if any(a.endswith(b'/lamulana2.exe') or a == b'lamulana2.exe' for a in args):
                if (p/'cwd').resolve() == game or any(str(game).lower().encode() in a for a in args):
                    raise ValueError('Close La-Mulana 2 before continuing (PID {}).'.format(p.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError): pass

@contextlib.contextmanager
def lock(game):
    if sys.platform != 'linux':
        yield; return
    import fcntl
    name = hashlib.sha256(str(game).encode()).hexdigest()
    with open(str(Path(tempfile.gettempdir())/('lm2chs-'+name+'.lock')), 'a+b') as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another patch operation is running.')
        yield

def exact(stream, n):
    require(n >= 0, 'Invalid delta length')
    data = stream.read(n)
    require(len(data) == n, 'Truncated delta')
    return data

def apply_delta(patch, output, sources):
    streams = [p.open('rb') for p in sources]
    try:
        with gzip.open(patch, 'rb') as src, output.open('wb') as out:
            require(exact(src, 8) == b'L2DELTA1', 'Invalid delta header')
            size = struct.unpack('<q', exact(src, 8))[0]
            while True:
                op = exact(src, 1)[0]
                if op == 255: break
                if op == 0:
                    n = struct.unpack('<i', exact(src, 4))[0]
                    require(n >= 0, 'Invalid literal length')
                    while n:
                        block = exact(src, min(n, 65536)); out.write(block); n -= len(block)
                elif op in (1, 2):
                    idx, offset, n = struct.unpack('<Bqi', exact(src, 13))
                    require(idx < len(streams) and offset >= 0 and n >= 0, 'Invalid delta source')
                    inp = streams[idx]; inp.seek(offset)
                    while n:
                        count = min(n, 65536); block = exact(inp, count)
                        if op == 2: block = bytes(a ^ b for a, b in zip(block, exact(src, count)))
                        out.write(block); n -= count
                else: raise ValueError('Invalid delta operation')
            require(out.tell() == size, 'Delta output length mismatch')
            out.flush(); os.fsync(out.fileno())
    finally:
        for stream in streams: stream.close()

def recover(game, state):
    require(not (state/'transaction.json').exists(), 'A Windows installation was interrupted. Run the Windows installer to recover it first.')
    journal = state/'linux-transaction.json'
    if journal.exists():
        txn = read_json(journal)
        for row in txn['files']:
            rollback = state/'rollback-linux'/row['name']
            require(digest(rollback) == row['hash'], 'Rollback backup changed: ' + str(rollback))
        for row in txn['files']:
            atomic_bytes(target(game, row['path']), (state/'rollback-linux'/row['name']).read_bytes())
        if txn['had_record']:
            atomic_bytes(state/'installed.json', (state/'rollback-linux'/'installed.json').read_bytes())
        elif (state/'installed.json').exists():
            (state/'installed.json').unlink()
        journal.unlink()
        print('Recovered the interrupted operation to the previous files.')

def operate(mode, game, support):
    state = game/STATE
    with lock(game):
        check_running(game)
        recover(game, state)
        installed_path = state/'installed.json'
        installed = read_json(installed_path) if installed_path.exists() else None
        manifest = installed if mode == 'restore' else read_json(support/'Data/manifest.json')
        require(manifest and manifest.get('app_id') == 835430, 'No compatible patch record found.')
        files = manifest['files']
        if mode == 'check':
            for row in files:
                h = digest(target(game, row['path']))
                require(h in (row['base_hash'], row['target_hash']), 'Unrecognized game file: ' + row['path'])
                print(('PATCHED: ' if h == row['target_hash'] else 'ORIGINAL: ') + row['path'])
            print('Check complete.'); return
        state.mkdir(exist_ok=True)
        original = state/'original'; original.mkdir(exist_ok=True)
        stage = state/'staging-linux'; stage.mkdir(exist_ok=True)
        rollback = state/'rollback-linux'; rollback.mkdir(exist_ok=True)
        sources = [target(game, p) for p in manifest['sources']]
        old = {f['path']: f for f in installed['files']} if installed else {}
        for row in files:
            path = target(game, row['path']); h = digest(path)
            allowed = {row['base_hash'], row['target_hash']}
            if row['path'] in old: allowed.add(old[row['path']]['target_hash'])
            require(h in allowed, 'Unsupported or modified game file: ' + row['path'])
            backup = original/Path(row['path']).name
            if not backup.exists():
                require(h == row['base_hash'], 'Original backup is missing: ' + str(backup))
                atomic_bytes(backup, path.read_bytes())
            require(digest(backup) == row['base_hash'], 'Original backup mismatch: ' + str(backup))
            sources[row['source_index']] = backup
        if mode == 'install':
            for seg in manifest['source_segments']:
                with sources[seg['source_index']].open('rb') as inp:
                    inp.seek(seg['offset']); data = exact(inp, seg['length'])
                require(hashlib.sha256(data).hexdigest() == seg['sha256'], 'Original font atlas does not match this game build.')
        txn = []
        for row in files:
            name = Path(row['path']).name; staged = stage/name; path = target(game, row['path'])
            if mode == 'install': apply_delta(support/'Data'/row['patch'], staged, sources)
            else: atomic_bytes(staged, (original/name).read_bytes())
            require(digest(staged) == row['target_hash' if mode == 'install' else 'base_hash'], 'Staged file verification failed: ' + name)
            atomic_bytes(rollback/name, path.read_bytes())
            txn.append({'path': row['path'], 'name': name, 'hash': digest(rollback/name)})
        if installed_path.exists(): atomic_bytes(rollback/'installed.json', installed_path.read_bytes())
        atomic_json(state/'linux-transaction.json', {'files': txn, 'had_record': installed_path.exists()})
        try:
            for row in txn: replace_file(stage/row['name'], target(game, row['path']))
            if mode == 'install':
                # Publish the cross-platform record before removing the journal.
                atomic_json(installed_path, manifest)
                shutil.copyfile(str(support/'Manage.py'), str(state/'Restore.py'))
                atomic_bytes(state/'Restore.sh', b'#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec python3 ./Restore.py restore --game-dir "$(dirname "$PWD")" --standalone\n')
                os.chmod(state/'Restore.sh', 0o755)
            (state/'linux-transaction.json').unlink()
        except BaseException:
            recover(game, state)
            raise
        print('Installed. Select Simplified Chinese in the game.' if mode == 'install' else 'Original game files restored. Saves and settings were kept.')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=('install', 'check', 'restore'))
    p.add_argument('directory', nargs='?')
    p.add_argument('--game-dir')
    p.add_argument('--standalone', action='store_true')
    a = p.parse_args()
    game = find_game(a.game_dir or a.directory)
    operate(a.mode, game, Path(__file__).resolve().parent)

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('ERROR: ' + str(exc), file=sys.stderr); sys.exit(1)
