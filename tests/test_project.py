"""Repository health: versions agree, links resolve, the supply chain stays pinned."""

from pathlib import Path
import re
import unittest
from urllib.parse import unquote

from helpers import ROOT

from econpulse import REPO, __version__

DOCS = [
    'README.md',
    'README_FA.md',
    'CONTRIBUTING.md',
    'SECURITY.md',
    'SUPPORT.md',
    'CHANGELOG.md',
    'docs/ARCHITECTURE.md',
    'docs/PROVIDERS.md',
    'docs/TRANSLATING.md',
    'docs/OBS.md',
    'docs/RELEASING.md',
    'GOVERNANCE.md',
    'tests/visual/README.md',
]
LINK = re.compile(r'\]\(([^)\s]+)\)|(?:src|href|srcset)="([^"]+)"')


def local_targets(path: Path):
    """Relative links and images in a Markdown or HTML file (not web URLs or anchors)."""
    text = path.read_text(encoding='utf-8')
    text = re.sub(r'```.*?```', '', text, flags=re.S)  # ignore code samples
    for match in LINK.finditer(text):
        target = match.group(1) or match.group(2)
        if re.match(r'^(https?:|mailto:|#)', target) or '{{' in target:
            continue
        yield unquote(target.split('#', 1)[0])


class ProjectTests(unittest.TestCase):
    def test_version_is_the_same_everywhere(self):
        citation = (ROOT / 'CITATION.cff').read_text(encoding='utf-8')
        self.assertRegex(citation, rf'(?m)^version: {re.escape(__version__)}$')
        changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        self.assertIn(f'## [{__version__}] - ', changelog)

    def test_repository_is_configured(self):
        self.assertFalse(REPO.startswith('OWNER/'), 'set REPO in econpulse/__init__.py')
        for name in [*DOCS, 'pyproject.toml', 'CITATION.cff', 'site/index.html']:
            self.assertNotIn('OWNER/', (ROOT / name).read_text(encoding='utf-8'), name)

    def test_relative_links_and_images_exist(self):
        for name in DOCS:
            path = ROOT / name
            for target in local_targets(path):
                self.assertTrue((path.parent / target).exists(), f'{name} links to missing {target}')

    def test_website_assets_exist(self):
        # The Pages workflow copies docs/assets -> assets/ and docs/screenshots -> screenshots/.
        mapping = {'assets/': ROOT / 'docs' / 'assets', 'screenshots/': ROOT / 'docs' / 'screenshots'}
        for target in local_targets(ROOT / 'site' / 'index.html'):
            if target == 'assets/icon.png':
                self.assertTrue((ROOT / 'econpulse' / 'assets' / 'econpulse.png').exists())
                continue
            prefix = next(p for p in mapping if target.startswith(p))
            self.assertTrue((mapping[prefix] / target[len(prefix) :]).exists(), target)

    def test_every_action_is_pinned_to_a_commit(self):
        uses = re.compile(r'^\s*(?:-\s*)?uses:\s*(\S+)', re.M)
        for workflow in sorted((ROOT / '.github' / 'workflows').glob('*.yml')):
            for action in uses.findall(workflow.read_text(encoding='utf-8')):
                self.assertRegex(action, r'@[0-9a-f]{40}$', f'{workflow.name}: {action} is not pinned to a SHA')

    def test_locked_requirements_have_hashes(self):
        for lock in sorted(p.name for p in ROOT.glob('requirements*.lock')):
            text = (ROOT / lock).read_text(encoding='utf-8')
            packages = re.findall(r'(?m)^([A-Za-z0-9_.-]+)==', text)
            self.assertTrue(packages, lock)
            for block in re.split(r'(?m)^(?=[A-Za-z0-9_.-]+==)', text)[1:]:
                self.assertIn('--hash=sha256:', block, f'{lock}: {block.splitlines()[0]} has no hash')

    def test_automated_installs_are_hash_checked(self):
        # CI, run.sh and RUN_WINDOWS.bat install only from hash-locked files (OpenSSF Scorecard: Pinned-Dependencies).
        scripts = [ROOT / 'run.sh', ROOT / 'RUN_WINDOWS.bat', *sorted((ROOT / '.github' / 'workflows').glob('*.yml'))]
        for script in scripts:
            for line in script.read_text(encoding='utf-8').splitlines():
                if re.search(r'\bpip install\b', line):
                    hashed = r'--require-hashes -r requirements[\w-]*\.lock'
                    self.assertRegex(line, hashed, f'{script.name}: {line.strip()}')

    def test_every_release_is_in_the_persian_changelog_too(self):
        english = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
        persian = (ROOT / 'CHANGELOG_FA.md').read_text(encoding='utf-8')
        to_fa = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')
        for major, minor in re.findall(r'(?m)^## \[(\d+)\.(\d+)\.\d+\]', english):
            heading = f'# تغییرات نسخه {major}.{minor}'.translate(to_fa)
            self.assertIn(heading, persian, f'CHANGELOG_FA.md has no section for {major}.{minor}')

    def test_release_notes_interpolate_version_and_repo(self):
        import sys

        sys.path.insert(0, str(ROOT / 'tools'))
        import release_notes

        body = release_notes.notes(__version__)
        self.assertNotIn('<owner>', body)
        self.assertNotIn('<version>', body)
        self.assertIn(f'EconPulse-{__version__}-Windows.zip', body)
        self.assertIn(REPO, body)

    def test_pypi_readme_has_no_relative_links(self):
        import re
        import sys

        sys.path.insert(0, str(ROOT / 'tools'))
        import pypi_readme

        sample = (
            '<img src="docs/a.png"> <source srcset="docs/b.png"> <a href="LICENSE">x</a> '
            '[guide](docs/OBS.md#setup) [web](https://example.org/x.png) [top](#install) '
            '<img src="https://img.shields.io/badge/x">'
        )
        out = pypi_readme.absolute(sample, REPO, 'v9.9.9')
        raw, blob = f'https://raw.githubusercontent.com/{REPO}/v9.9.9/', f'https://github.com/{REPO}/blob/v9.9.9/'
        self.assertIn(f'src="{raw}docs/a.png"', out)
        self.assertIn(f'srcset="{raw}docs/b.png"', out)
        self.assertIn(f'href="{blob}LICENSE"', out)
        self.assertIn(f']({blob}docs/OBS.md#setup)', out)
        self.assertIn('](https://example.org/x.png)', out)
        self.assertIn('](#install)', out)
        self.assertIn('src="https://img.shields.io/badge/x"', out)

        readme = pypi_readme.absolute((ROOT / 'README.md').read_text(encoding='utf-8'), REPO, 'v1')
        relative = re.findall(r'(?:\]\(|(?:src|srcset|href)=")(?!https?://|mailto:|#)[^)"\s]+', readme)
        self.assertEqual(relative, [])


if __name__ == '__main__':
    unittest.main()
