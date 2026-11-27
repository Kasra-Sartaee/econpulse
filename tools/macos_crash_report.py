"""Print the crashing thread of the newest Python crash report macOS wrote.

CI runs this after a failed macOS test job. Python's faulthandler only shows the Python
line that was running when Tk crashed; macOS's own report shows where inside Tk it happened.
"""

import json
from pathlib import Path
import sys

REPORTS = Path.home() / 'Library' / 'Logs' / 'DiagnosticReports'


def main() -> int:
    reports = sorted(REPORTS.glob('Python*.ips'), key=lambda p: p.stat().st_mtime)
    if not reports:
        print(f'No Python crash report in {REPORTS}.')
        return 0
    path = reports[-1]
    print(f'{path.name}:')
    _header, _, body = path.read_text(encoding='utf-8', errors='replace').partition('\n')
    try:
        report = json.loads(body)
    except ValueError:
        print(body[:8000])
        return 0
    print('exception:', report.get('exception'))
    images = report.get('usedImages', [])
    for thread in report.get('threads', []):
        if thread.get('triggered'):
            for frame in thread.get('frames', [])[:50]:
                index = frame.get('imageIndex')
                image = images[index].get('name', '?') if index is not None and index < len(images) else '?'
                print(f'  {image:32} {frame.get("symbol", "?")}+{frame.get("symbolLocation", 0)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
