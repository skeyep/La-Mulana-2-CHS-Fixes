"""Small, game-free regression suite usable on Linux and Windows."""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('manage', Path(__file__).parent/'Manage.py')
if not Path(spec.origin).exists():
    spec = importlib.util.spec_from_file_location('manage', Path(__file__).parent/'installer/Manage.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def sha(b): return hashlib.sha256(b).hexdigest()

class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='lm2 test ')
        self.root = Path(self.tmp.name); self.game=self.root/'game'; self.game.mkdir()
        self.support=self.root/'Support'; (self.support/'Data').mkdir(parents=True)
        (self.game/'LaMulana2.exe').write_bytes(b'fixture')
        shutil.copyfile(m.__file__, self.support/'Manage.py')
        self.manifest={'app_id':835430,'version':'test','sources':['data/a','data/b','data/source'], 'source_segments':[], 'files':[]}
        (self.game/'data').mkdir()
        for i, name in enumerate(('a','b')):
            base=('base '+name).encode(); result=('patched '+name).encode()
            (self.game/'data'/name).write_bytes(base)
            with gzip.open(self.support/'Data'/(name+'.gz'),'wb') as f:
                f.write(b'L2DELTA1'+struct.pack('<q',len(result))+b'\0'+struct.pack('<i',len(result))+result+b'\xff')
            self.manifest['files'].append({'path':'data/'+name,'source_index':i,'base_hash':sha(base),'target_hash':sha(result),'patch':name+'.gz'})
        (self.game/'data/source').write_bytes(b'source')
        (self.support/'Data/manifest.json').write_text(json.dumps(self.manifest),encoding='utf-8')
    def tearDown(self): self.tmp.cleanup()
    def test_lifecycle_and_recovery(self):
        m.operate('install',self.game,self.support)
        self.assertEqual((self.game/'data/a').read_bytes(),b'patched a')
        m.operate('check',self.game,self.support)
        m.operate('install',self.game,self.support)
        state=self.game/m.STATE; rollback=state/'rollback-linux'
        rows=[]
        for row in self.manifest['files']:
            p=self.game/row['path']; shutil.copyfile(p,rollback/p.name)
            rows.append({'path':row['path'],'name':p.name,'hash':m.digest(p)})
        shutil.copyfile(state/'installed.json',rollback/'installed.json')
        (self.game/'data/a').write_bytes(b'base a')
        m.atomic_json(state/'linux-transaction.json',{'files':rows,'had_record':True})
        m.operate('check',self.game,self.support)
        self.assertEqual((self.game/'data/a').read_bytes(),b'patched a')
        m.operate('restore',self.game,state)
        self.assertEqual((self.game/'data/b').read_bytes(),b'base b')
        (self.game/'data/a').write_bytes(b'foreign')
        with self.assertRaises(ValueError): m.operate('install',self.game,self.support)
        self.assertEqual((self.game/'data/a').read_bytes(),b'foreign')
    def test_library_and_manifest(self):
        text='"libraryfolders" { "0" { "path" "/home/deck/Steam" } "1" "/run/media/deck/card" }'
        data=m.parse_vdf(text)['libraryfolders']
        self.assertEqual(data['0']['path'],'/home/deck/Steam')
        self.assertEqual(data['1'],'/run/media/deck/card')
        with self.assertRaises(ValueError): m.target(self.game,'../outside')
    @unittest.skipUnless(os.name == 'posix', 'POSIX only')
    def test_lock(self):
        with m.lock(self.game):
            with self.assertRaises(ValueError):
                with m.lock(self.game): pass

if __name__ == '__main__': unittest.main()

