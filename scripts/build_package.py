import os
"""Build a small offline Windows patch from baseline-dependent copy/XOR deltas."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zipfile
import numpy as np
import UnityPy

ROOT=Path(__file__).resolve().parents[2]
GAME=Path(os.environ['LM2_GAME_DIR'])
BUILD=ROOT/'build/lm2-text-patch'
RELEASE=json.loads((ROOT/'localization/lm2/release.json').read_text(encoding='utf-8'))
VERSION=RELEASE['version']
PACKAGE=ROOT/f'build/releases/LA-MULANA2-CHS-Fixes-{VERSION}-Windows'

class Delta:
 def __init__(self,path,length):
  self.f=gzip.GzipFile(filename=str(path),mode='wb',compresslevel=9,mtime=0);self.f.write(b'L2DELTA1'+struct.pack('<q',length));self.ops=0
 def literal(self,b):
  if b:self.f.write(b'\x00'+struct.pack('<i',len(b))+b);self.ops+=1
 def copy(self,source,offset,length):
  self.f.write(b'\x01'+struct.pack('<Bqi',source,offset,length));self.ops+=1
 def xor(self,source,offset,before,after):
  assert len(before)==len(after)
  self.f.write(b'\x02'+struct.pack('<Bqi',source,offset,len(after)))
  self.f.write(np.bitwise_xor(np.frombuffer(before,dtype='uint8'),np.frombuffer(after,dtype='uint8')).tobytes());self.ops+=1
 def close(self):self.f.write(b'\xff');self.f.close()

def sha(data):return hashlib.sha256(data).hexdigest()
def text(path,value):path.write_text(value,encoding='utf-8')
def cmd(path,body):path.write_bytes(('@echo off\r\n'+body+'\r\n').encode('ascii'))

def main():
 support=PACKAGE/'Support';data=support/'Data';data.mkdir(parents=True,exist_ok=True)
 inputs=['LaMulana2_Data/Managed/Assembly-CSharp.dll','LaMulana2_Data/resources.assets','LaMulana2_Data/resources.assets.resS']
 files=[];segments=[]
 for idx,name in [(0,'Assembly-CSharp.dll'),(1,'resources.assets')]:
  base=(GAME/inputs[idx]).read_bytes();target=(BUILD/name).read_bytes();patch=name+'.l2delta.gz';writer=Delta(data/patch,len(target))
  if idx==0:
   padded=base[:len(target)].ljust(len(target),b'\0')
   if len(target)>len(base):
    writer.xor(0,0,base,target[:len(base)]);writer.literal(target[len(base):])
   else:writer.xor(0,0,padded,target)
  else:
   old=UnityPy.load(str(GAME/inputs[idx]));new=UnityPy.load(str(BUILD/name));ob={o.path_id:o for o in old.objects};nb={o.path_id:o for o in new.objects};assert set(ob)==set(nb)
   fonts=json.loads((BUILD/'font-additions.json').read_text(encoding='utf-8'));atlas_ids={x['atlas_path_id'] for x in fonts['fonts']};font_ids={x['font_path_id'] for x in fonts['fonts']};cursor=0
   for o in sorted(nb.values(),key=lambda x:x.byte_start):
    assert o.byte_start>=cursor
    writer.literal(target[cursor:o.byte_start]);raw=o.get_raw_data();prior=ob[o.path_id]
    if o.path_id in atlas_ids:
     a=prior.read();b=o.read();before=a.get_image_data();after=b.get_image_data();at=raw.find(after);assert at>=0
     writer.literal(raw[:at]);writer.xor(2,a.m_StreamData.offset,before,after);writer.literal(raw[at+len(after):])
     segments.append({'source_index':2,'offset':a.m_StreamData.offset,'length':len(before),'sha256':sha(before)})
    elif o.path_id in font_ids:writer.literal(raw)
    else:
     assert prior.get_raw_data()==raw
     writer.copy(1,prior.byte_start,len(raw))
    cursor=o.byte_start+len(raw)
   writer.literal(target[cursor:])
  writer.close()
  files.append({'path':inputs[idx],'source_index':idx,'base_size':len(base),'base_hash':sha(base),'target_size':len(target),'target_hash':sha(target),'patch':patch,'delta_size':(data/patch).stat().st_size,'delta_operations':writer.ops})
 manifest={'game':RELEASE['game'],'app_id':RELEASE['app_id'],'build_id':RELEASE['build_id'],'version':VERSION,'date':RELEASE['date'],'issues':RELEASE['selected_issues'],'chinese_rows':RELEASE['chinese_rows'],'font_characters':RELEASE['font_additions'],'sources':inputs,'source_segments':segments,'files':files}
 text(data/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 for name in ['Manage.ps1','Restore-Standalone.ps1']:shutil.copyfile(ROOT/'tools/lm2/installer'/name,support/name)
 cmd(PACKAGE/'Install.cmd','powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Support\\Manage.ps1" -Mode Install %*\r\nif errorlevel 1 (pause & exit /b 1)\r\npause')
 for mode in ['Check','Restore']:
  cmd(support/f'{mode}.cmd',f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Manage.ps1" -Mode {mode} %*\r\nif errorlevel 1 (pause & exit /b 1)\r\npause')
 cmd(support/'Restore-Standalone.cmd','powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Restore.ps1"\r\nif errorlevel 1 (pause & exit /b 1)\r\npause')
 text(PACKAGE/'README.txt',f'''LA-MULANA 2 Simplified Chinese Fixes {VERSION}
Windows Steam edition - app 835430, build 9559015
Initial test build. Longer text may still need layout adjustments.

Corrects {RELEASE['selected_issues']} translation and naming issues across {RELEASE['chinese_rows']} Chinese text rows.
Includes seven missing Chinese glyphs in the three existing Chinese fonts.
Select Chinese in the game settings after installation.

INSTALL
1. Close the game and extract this entire archive to a writable folder.
2. Double-click Install.cmd. Steam libraries are detected automatically.
3. If prompted, choose the folder containing LaMulana2.exe.

UPGRADE
Run the new Install.cmd directly over an existing supported CHS Fixes version.
Your original backup and saves are kept. An interrupted install is recovered
when you run Install.cmd again. Other mods changing the same files must be
restored first. This patch supports the original Windows Steam game build above.

CHECK AND RESTORE
Run Support\\Check.cmd to check the two patched game files.
Run Support\\Restore.cmd to restore the original game files.
You can also restore without this download: open the game folder, then run
.lm2chs-fixes\\Restore.cmd. Keep .lm2chs-fixes: it contains the original backup.

The handwritten Japanese area-name artwork is retained; translated Chinese
labels are corrected through the game text tables. The patch does not include
the game or third-party walkthroughs. Translation changes are listed in
Support\\CHANGES.zh-CN.md. Font attribution is in Support\\Licenses.
''')
 licenses=support/'Licenses';licenses.mkdir(exist_ok=True)
 for p in (ROOT/'localization/lm2/licenses').glob('*.txt'):shutil.copyfile(p,licenses/p.name)
 review=json.loads((ROOT/'localization/lm2/review/20261106/review.json').read_text(encoding='utf-8'))
 lines=[f'# LA-MULANA 2 官方简中修正 {VERSION}','',f"{RELEASE['selected_issues']}项修正，涉及{RELEASE['chinese_rows']}处文本；以下含谜题线索。",'','保留原作日文手写区域标题，简中地名按同一对象统一。','']
 for issue in review['issues']:
  lines += [f"## {issue['id']} · {issue['title']}",'',issue['reason'],'']
  for entry in issue['entries']:
   lines += [f"`{entry['stable_id']}` · `{entry['native_id']}`",'','原译：','```text',entry['before'],'```','','修正：','```text',entry['after'],'```','']
 text(support/'CHANGES.zh-CN.md','\n'.join(lines)+'\n')
 archive=Path(str(PACKAGE)+'.zip')
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(PACKAGE.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(PACKAGE).as_posix())
 print(json.dumps({'package':str(archive),'bytes':archive.stat().st_size,'files':files},ensure_ascii=False))

if __name__=='__main__':main()
