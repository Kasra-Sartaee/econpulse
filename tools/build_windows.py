"""Build the Windows app folder, the release zip and SHA-256 checksums.

    python tools/build_windows.py

Used by BUILD_WINDOWS.bat and by the release workflow, so local and published
builds are made the same way. Output (in dist/):

    EconPulse/EconPulse.exe (+ _internal/)   the app; keep the folder together
    EconPulse-<version>-Windows.zip          the file to share or attach to a release
    SHA256SUMS.txt                           checksums of the zip
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
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


def main():
    if APP.exists():
        shutil.rmtree(APP)
    pyinstaller()
    bundled = {p.name.lower() for p in (APP / '_internal').iterdir()}
    if 'bs4' in bundled:
        raise SystemExit('unexpected: BeautifulSoup was bundled')
    archive = make_zip()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (DIST / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print(f'\nREADY  {APP / "EconPulse.exe"}\nSHARE  {archive}\nSHA256 {digest}')


if __name__ == '__main__':
    main()
