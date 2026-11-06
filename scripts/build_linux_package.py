"""Package the current game delta with SteamOS/Proton entry points."""
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
release = json.loads((ROOT/'localization/lm2/release.json').read_text(encoding='utf-8'))
version = release['version']
windows = ROOT/('build/releases/LA-MULANA2-CHS-Fixes-{}-Windows'.format(version))
package = ROOT/('build/releases/LA-MULANA2-CHS-Fixes-{}-Linux-Proton'.format(version))
support = package/'Support'
support.mkdir(parents=True, exist_ok=True)
for name in ('Data', 'Licenses'):
    shutil.copytree(windows/'Support'/name, support/name, dirs_exist_ok=True)
shutil.copyfile(windows/'Support/CHANGES.zh-CN.md', support/'CHANGES.zh-CN.md')
shutil.copyfile(ROOT/'tools/lm2/installer/Manage.py', support/'Manage.py')
for name, mode, relative in [('Install.sh','install','Support/Manage.py'), ('Check.sh','check','Manage.py'), ('Restore.sh','restore','Manage.py')]:
    directory = package if name == 'Install.sh' else support
    body = '#!/bin/sh\ncd "$(dirname "$0")" || exit 1\nexec python3 ./{} {} "$@"\n'.format(relative, mode)
    (directory/name).write_bytes(body.encode('utf-8'))
(package/'README.txt').write_text('''LA-MULANA 2 Simplified Chinese Fixes {} — Steam Deck / Linux (Proton)

1. In Steam, open Properties > Compatibility and force a Proton version.
   Let Steam download the Windows version, start it once, then exit.
2. In Desktop Mode extract the entire archive. Open a terminal in this folder:
   bash ./Install.sh
3. Select Simplified Chinese in the game settings. To check the files, run:
   bash ./Support/Check.sh

If automatic detection fails, pass the game folder as an argument:
   bash ./Install.sh "/path/to/steamapps/common/La-Mulana 2"

For upgrades, run the new Install.sh directly. To restore the original files:
   bash ./Support/Restore.sh
After installation, the game folder also contains an independent restore:
   bash ./.lm2chs-fixes/Restore.sh
Keep .lm2chs-fixes: it holds the original backup. Saves and settings are kept.
This patch requires the Windows Steam build 9559015 and Python 3.8 or later.
Steam Deck / Proton game rendering remains to be verified on a Deck.
Translation changes and font attribution are in Support/.
'''.format(version), encoding='utf-8', newline='\n')
archive = Path(str(package)+'.zip')
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for path in sorted(package.rglob('*')):
        if path.is_file():
            info = zipfile.ZipInfo.from_file(path, path.relative_to(package).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if path.suffix == '.sh' else 0o100644) << 16
            z.writestr(info, path.read_bytes())
print(archive)
