"""Write the winget manifests for a published release (so `winget install EconPulse` works).

    python tools/winget_manifest.py 3.4.0 --sha256 <hash of the Windows zip>
    python tools/winget_manifest.py 3.4.0 --sums dist/SHA256SUMS.txt

Writes dist/winget/<version>/ with the three files winget expects. Check them with
`winget validate --manifest dist/winget/<version>`, then submit them as a pull request to
https://github.com/microsoft/winget-pkgs under manifests/k/KasraSartaee/EconPulse/<version>/
(see docs/RELEASING.md). The release zip must already be published: winget downloads it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse import APP_NAME, REPO

PACKAGE = 'KasraSartaee.EconPulse'
SCHEMA = '1.10.0'
HEADER = '# yaml-language-server: $schema=https://aka.ms/winget-manifest.{kind}.{schema}.schema.json\n'


def manifests(version: str, sha256: str) -> dict[str, str]:
    url = f'https://github.com/{REPO}/releases/download/v{version}/{APP_NAME}-{version}-Windows.zip'
    common = f'PackageIdentifier: {PACKAGE}\nPackageVersion: {version}\n'
    return {
        f'{PACKAGE}.yaml': HEADER.format(kind='version', schema=SCHEMA)
        + common
        + f'DefaultLocale: en-US\nManifestType: version\nManifestVersion: {SCHEMA}\n',
        f'{PACKAGE}.installer.yaml': HEADER.format(kind='installer', schema=SCHEMA)
        + common
        + 'InstallerType: zip\n'
        + 'NestedInstallerType: portable\n'
        + 'NestedInstallerFiles:\n'
        + f'  - RelativeFilePath: {APP_NAME}\\{APP_NAME}.exe\n'
        + '    PortableCommandAlias: econpulse\n'
        + 'MinimumOSVersion: 10.0.17763.0\n'
        + 'Installers:\n'
        + '  - Architecture: x64\n'
        + f'    InstallerUrl: {url}\n'
        + f'    InstallerSha256: {sha256.upper()}\n'
        + f'ManifestType: installer\nManifestVersion: {SCHEMA}\n',
        f'{PACKAGE}.locale.en-US.yaml': HEADER.format(kind='defaultLocale', schema=SCHEMA)
        + common
        + 'PackageLocale: en-US\n'
        + 'Publisher: Aref Hosseini and Kasra Sartaee\n'
        + f'PublisherUrl: https://github.com/{REPO.split("/")[0]}\n'
        + f'PackageName: {APP_NAME}\n'
        + f'PackageUrl: https://github.com/{REPO}\n'
        + 'License: MIT\n'
        + f'LicenseUrl: https://github.com/{REPO}/blob/main/LICENSE\n'
        + 'ShortDescription: Economic calendar for your desktop, with countdowns, alerts and'
        + ' Actual/Forecast/Previous values.\n'
        + 'Tags:\n  - economic-calendar\n  - forex\n  - trading\n  - widget\n'
        + f'ReleaseNotesUrl: https://github.com/{REPO}/releases/tag/v{version}\n'
        + f'ManifestType: defaultLocale\nManifestVersion: {SCHEMA}\n',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('version')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--sha256', help='SHA-256 of EconPulse-<version>-Windows.zip')
    group.add_argument('--sums', type=Path, help='a SHA256SUMS.txt from the release')
    args = parser.parse_args()
    sha = args.sha256
    if args.sums:
        name = f'{APP_NAME}-{args.version}-Windows.zip'
        sums = args.sums.read_text(encoding='utf-8')
        match = re.search(rf'(?m)^([0-9a-fA-F]{{64}})\s+\*?{re.escape(name)}\s*$', sums)
        if not match:
            raise SystemExit(f'{args.sums} has no checksum for {name}')
        sha = match.group(1)
    if not re.fullmatch(r'[0-9a-fA-F]{64}', sha or ''):
        raise SystemExit('the SHA-256 must be 64 hex characters')
    out = ROOT / 'dist' / 'winget' / args.version
    out.mkdir(parents=True, exist_ok=True)
    for name, text in manifests(args.version, sha).items():
        (out / name).write_text(text, encoding='utf-8', newline='\n')
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
