"""Print one version's section of CHANGELOG.md (used for GitHub release notes).

python tools/release_notes.py 3.3.0
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from econpulse import REPO


def notes(version: str) -> str:
    text = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    match = re.search(rf'^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)', text, re.M | re.S)
    if not match:
        raise SystemExit(f'CHANGELOG.md has no section for {version}')
    return (
        match.group(1).strip() + '\n\nVerify the download: compare its SHA-256 with SHA256SUMS.txt, or run\n'
        f'`gh attestation verify EconPulse-{version}-Windows.zip --repo {REPO}`.\n'
    )


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')  # Windows consoles/pipes default to a legacy code page
    print(notes(sys.argv[1]))
