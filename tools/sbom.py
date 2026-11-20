"""Write a CycloneDX software bill of materials for a release.

Lists every pinned package that goes into the Windows build (from
requirements-build.lock), with versions, licences and hashes:

    python tools/sbom.py            -> dist/EconPulse-<version>-SBOM.cdx.json

Needs the dev tools: pip install --require-hashes -r requirements-dev.lock
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse import APP_NAME, REPO_URL, __version__


def main() -> None:
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / 'sbom.json'
        subprocess.run(
            [
                sys.executable,
                '-m',
                'cyclonedx_py',
                'requirements',
                '--pyproject',
                str(ROOT / 'pyproject.toml'),
                '--mc-type',
                'application',
                '--output-reproducible',
                '--validate',
                '-o',
                str(raw),
                str(ROOT / 'requirements-build.lock'),
            ],
            check=True,
            cwd=ROOT,
        )
        bom = json.loads(raw.read_text(encoding='utf-8'))
    # The version is dynamic in pyproject.toml, so the generator can't see it.
    component = bom['metadata']['component']
    component['name'] = APP_NAME
    component['version'] = __version__
    component['externalReferences'] = [{'type': 'vcs', 'url': REPO_URL}]
    out = dist / f'{APP_NAME}-{__version__}-SBOM.cdx.json'
    out.write_text(json.dumps(bom, indent=2) + '\n', encoding='utf-8')
    names = ', '.join(f'{c["name"]} {c["version"]}' for c in bom.get('components', []))
    print(f'{out.relative_to(ROOT)}: {len(bom.get("components", []))} components ({names})')


if __name__ == '__main__':
    main()
