"""Summarise a mutmut run, and fail if the mutation score falls below a floor.

    mutmut run
    python tools/mutation_score.py --minimum 80

Score = caught / (caught + survived). Mutants in code no selected test runs ("no tests")
are reported separately: they point at untested code rather than weak assertions.
In CI the summary goes to the run's page ($GITHUB_STEP_SUMMARY), with the survivors per function.
"""

from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import re
import subprocess
import sys

LINE = re.compile(r'^\s*(?P<name>\S+)__mutmut_\d+: (?P<status>.+?)\s*$')


def readable(name: str) -> str:
    """mutmut's mangled names made readable: 'econpulse.core.x_parse_feed' -> 'core.parse_feed',
    and methods 'econpulse.core.xǁEventǁcountdown' -> 'core.Event.countdown'."""
    parts = name.removeprefix('econpulse.').replace('xǁ', '').replace('ǁ', '.').split('.')
    parts[-1] = parts[-1].removeprefix('x_')
    return '.'.join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--minimum', type=float, default=0, help='lowest acceptable score, in percent')
    args = parser.parse_args()
    output = subprocess.run(
        ['mutmut', 'results', '--all', 'true'], capture_output=True, text=True, check=True, encoding='utf-8'
    ).stdout
    statuses: Counter[str] = Counter()
    survivors: Counter[str] = Counter()
    for line in output.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        status = match['status']
        statuses[status] += 1
        if status == 'survived':
            survivors[readable(match['name'])] += 1
    caught = statuses['killed'] + statuses['timeout']
    tested = caught + statuses['survived']
    score = 100 * caught / tested if tested else 0.0
    lines = [
        f'## Mutation score: {score:.1f}% (floor {args.minimum:g}%)',
        '',
        f'{caught} caught, {statuses["survived"]} survived, {statuses["no tests"]} in code no selected test runs.',
        '',
        '| Survivors | Function |',
        '|---:|---|',
        *(f'| {count} | `{name}` |' for name, count in survivors.most_common(15)),
    ]
    report = '\n'.join(lines) + '\n'
    print(report)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as out:
            out.write(report)
    return 0 if score >= args.minimum else 1


if __name__ == '__main__':
    sys.exit(main())
