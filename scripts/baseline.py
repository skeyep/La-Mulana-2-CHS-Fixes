"""Prepare build inputs from the retained originals, never from an installed patch."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
GAME=Path('D:/SteamLibrary/steamapps/common/La-Mulana 2')
BASE=ROOT/'build/lm2-original-baseline'

def prepare():
    manifest=json.loads((ROOT/'localization/lm2/releases/0.1.0/manifest.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        original=GAME/'.lm2chs-fixes/original'/Path(row['path']).name
        if not original.exists(): original=GAME/row['path']
        assert hashlib.sha256(original.read_bytes()).hexdigest()==row['base_hash'], original
        target=BASE/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target)
    stream=BASE/manifest['sources'][2]
    if not stream.exists():
        try: stream.hardlink_to(GAME/manifest['sources'][2])
        except OSError: shutil.copyfile(GAME/manifest['sources'][2],stream)
    return BASE

if __name__=='__main__':print(prepare())
