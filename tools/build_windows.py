"""Build the Windows app folder, the release zip and SHA-256 checksums.

    python tools/build_windows.py              # app folder + zip
    python tools/build_windows.py --installer  # also the Setup.exe (needs Inno Setup 6)

Used by BUILD_WINDOWS.bat and by the release workflow, so local and published
builds are made the same way. Output (in dist/):

    EconPulse/EconPulse.exe (+ _internal/)   the app; keep the folder together
    EconPulse-<version>-Windows.zip          the portable app, to share or attach to a release
    EconPulse-<version>-Setup.exe            the installer (with --installer)
    SHA256SUMS.txt                           checksums of the zip and the installer
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse import __version__

BUILD, DIST = ROOT / 'build', ROOT / 'dist'
APP = DIST / 'EconPulse'

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'EconPulse contributors'),
      StringStruct('FileDescription', 'EconPulse economic calendar'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'EconPulse'),
      StringStruct('LegalCopyright', 'MIT licence. Aref Hosseini, Kasra Sartaee and contributors'),
      StringStruct('OriginalFilename', 'EconPulse.exe'),
      StringStruct('ProductName', 'EconPulse'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def version_file() -> Path:
    parts = [int(p) for p in __version__.split('.')[:3]]
    numbers = tuple(parts + [0] * (4 - len(parts)))
    path = BUILD / 'version_info.txt'
    BUILD.mkdir(exist_ok=True)
    path.write_text(VERSION_INFO.format(t=numbers, v=__version__), encoding='utf-8')
    return path


def pyinstaller():
    import PyInstaller.__main__

    assets = ROOT / 'econpulse' / 'assets'
    PyInstaller.__main__.run(
        [
            str(ROOT / 'main.py'),
            '--noconfirm',
            '--clean',
            '--onedir',
            '--windowed',
            '--name',
            'EconPulse',
            '--specpath',
            str(BUILD),
            '--workpath',
            str(BUILD),
            '--distpath',
            str(DIST),
            '--icon',
            str(assets / 'econpulse.ico'),
            '--add-data',
            f'{assets}{os.pathsep}econpulse/assets',
            '--hidden-import',
            'pystray._win32',
            '--hidden-import',
            'tzdata',
            '--exclude-module',
            'unittest',
            '--exclude-module',
            'pydoc',
            '--exclude-module',
            'doctest',
            '--exclude-module',
            'pdb',
            '--exclude-module',
            'sqlite3',
            '--exclude-module',
            'xmlrpc',
            '--exclude-module',
            'ftplib',
            '--exclude-module',
            'imaplib',
            '--exclude-module',
            'smtplib',
            '--exclude-module',
            'tkinter.tix',
            '--exclude-module',
            'test',
            '--version-file',
            str(version_file()),
        ]
    )


def make_zip() -> Path:
    target = DIST / f'EconPulse-{__version__}-Windows.zip'
    target.unlink(missing_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(APP.rglob('*')):
            if path.is_file():
                archive.write(path, Path('EconPulse') / path.relative_to(APP))
    return target


def find_iscc() -> Path:
    """Inno Setup's command-line compiler: $ISCC, PATH, or the standard install folders."""
    candidates = [os.environ.get('ISCC', ''), shutil.which('iscc') or '']
    for variable in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            candidates.append(str(Path(base) / 'Inno Setup 6' / 'ISCC.exe'))
            candidates.append(str(Path(base) / 'Programs' / 'Inno Setup 6' / 'ISCC.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit('--installer needs Inno Setup 6 (https://jrsoftware.org/isinfo.php); or set ISCC to ISCC.exe')


def make_installer() -> Path:
    script = ROOT / 'installer' / 'EconPulse.iss'
    subprocess.run([str(find_iscc()), f'/DAppVersion={__version__}', '/Q', str(script)], check=True)
    return DIST / f'EconPulse-{__version__}-Setup.exe'


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--installer', action='store_true', help='also build the Setup.exe with Inno Setup 6')
    args = parser.parse_args()
    if APP.exists():
        shutil.rmtree(APP)
    pyinstaller()
    bundled = {p.name.lower() for p in (APP / '_internal').iterdir()}
    if 'bs4' in bundled:
        raise SystemExit('unexpected: BeautifulSoup was bundled')
    outputs = [make_zip()]
    if args.installer:
        outputs.append(make_installer())
    sums = ''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n' for path in outputs)
    (DIST / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8')
    print(f'\nREADY  {APP / "EconPulse.exe"}')
    for path in outputs:
        print(f'SHARE  {path}')
    print(sums, end='')


if __name__ == '__main__':
    main()
