"""Strict test run: random order, and leaked resources fail the run.

    python tools/run_tests.py              # shuffled with a random seed (printed)
    python tools/run_tests.py --seed 1234  # replay an order that failed

Two things a plain ``python -m unittest discover`` doesn't catch:

- order dependence: tests run in a shuffled order, so one test can't quietly
  rely on state another left behind (the Tk-root cleanup bug was one of these);
- leaks: an unclosed file or socket raises ResourceWarning in a destructor, which
  Python only prints. Here any such warning, or any other exception swallowed in a
  destructor, makes the run fail.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--seed', type=int, default=None)
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1_000_000)
    print(f'test order seed: {seed}  (replay with: python tools/run_tests.py --seed {seed})', flush=True)

    warnings.simplefilter('error', ResourceWarning)
    unraisable: list[str] = []
    sys.unraisablehook = lambda info: unraisable.append(f'{info.exc_type.__name__}: {info.exc_value} ({info.object!r})')

    sys.path.insert(0, str(ROOT / 'tests'))
    loaded = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT / 'tests'))
    # Shuffle whole test classes (their class-level fixtures must stay together), then
    # the tests inside each class.
    classes: dict[str, list[unittest.TestCase]] = {}
    for test in flatten(loaded):
        classes.setdefault(f'{type(test).__module__}.{type(test).__qualname__}', []).append(test)
    rng = random.Random(seed)
    order = list(classes.values())
    rng.shuffle(order)
    suite = unittest.TestSuite()
    for tests in order:
        rng.shuffle(tests)
        suite.addTests(tests)

    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if unraisable:
        print('\nLeaked resources or errors in destructors:', *unraisable, sep='\n  ')
    return 0 if result.wasSuccessful() and not unraisable else 1


if __name__ == '__main__':
    sys.exit(main())
