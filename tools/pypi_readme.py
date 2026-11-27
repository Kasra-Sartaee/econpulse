"""Point the README's relative links at GitHub, for the copy shown on PyPI.

PyPI shows README.md as the project page but cannot resolve paths inside the repository,
so every screenshot and doc link would break. The PyPI workflow runs this on its throwaway
checkout just before building:  python tools/pypi_readme.py v3.4.0
Images load from the tagged files; other links open the file on GitHub at that tag.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
IMAGE = re.compile(r'\.(png|gif|jpe?g|svg|webp)$', re.IGNORECASE)
# Markdown ](path) and HTML src= / srcset= / href= values that are not already absolute or anchors.
LINK = re.compile(r'(\]\(|\b(?:src|srcset|href)=")(?!https?://|mailto:|#)([^)"\s]+)')


def absolute(text: str, repo: str, ref: str) -> str:
    def rewrite(match: re.Match[str]) -> str:
        opener, target = match.groups()
        path, anchor, fragment = target.partition('#')
        path = path.removeprefix('./')
        if IMAGE.search(path):
            url = f'https://raw.githubusercontent.com/{repo}/{ref}/{path}'
        else:
            url = f'https://github.com/{repo}/blob/{ref}/{path}'
        return f'{opener}{url}{anchor}{fragment}'

    return LINK.sub(rewrite, text)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('usage: python tools/pypi_readme.py <git ref, such as v3.4.0>', file=sys.stderr)
        return 2
    sys.path.insert(0, str(ROOT))
    from econpulse import REPO

    readme = ROOT / 'README.md'
    readme.write_text(absolute(readme.read_text(encoding='utf-8'), REPO, argv[1]), encoding='utf-8', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
