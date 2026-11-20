# Contributing to EconPulse

Thanks for helping. Bug reports, translations, new data sources, documentation and code are all welcome.

## Reporting a bug

Open an issue using the **Bug report** form. In the app, go to **Settings → About → Copy diagnostics** and paste the result into the form. It lists the version, operating system, data source and recent errors. It never includes your API key or notes, and your home folder is masked. For security problems, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

```sh
git clone https://github.com/Kasra-Sartaee/econpulse.git
cd econpulse
python -m venv .venv
.venv\Scripts\activate          # Windows;  source .venv/bin/activate on macOS/Linux
python -m pip install -r requirements.txt
python -m pip install --require-hashes -r requirements-dev.lock   # ruff, bandit, pip-audit, coverage (pinned)
python -m econpulse --demo      # sample data, no network
```

Optionally, run the checks automatically before every commit:

```sh
python -m pip install pre-commit
pre-commit install
```

## Checks (CI runs the same ones)

```sh
python -m unittest discover -s tests     # on Linux without a display: xvfb-run -a python -m unittest ...
ruff check .
ruff format --check .
bandit -r econpulse -c pyproject.toml
python -m coverage run -m unittest discover -s tests && python -m coverage report
```

Please add or update tests for behaviour you change. Tests that need a window skip themselves where Tk can't open one. CI fails if line coverage (measured on Windows) drops below the floor in `pyproject.toml`; `tests/test_ui.py` shows how to drive whole windows in demo mode without touching real settings.

The parsers for downloaded data are also **fuzzed** (`fuzz/fuzz_calendar_data.py`): a quick deterministic version runs with the tests on every platform, and coverage-guided fuzzing with Atheris runs in CI. If you change a parser, add an example to `fuzz/corpus/` and keep the checks in the fuzz target true.

Each pull request also gets a **Windows build** you can download from the workflow run's *Artifacts* to try the change without installing Python.

## Code map

| Path | What lives there |
|---|---|
| `econpulse/app.py` | Application state, refresh and backoff, rendering, clock and alerts, tray |
| `econpulse/ui_calendar.py`, `ui_widget.py`, `dialogs.py` | The full calendar window, the floating widget, and dialogs (mixins sharing the app's state) |
| `econpulse/event_list.py`, `controls.py` | The virtualised release list and the canvas-drawn controls |
| `econpulse/providers/` | Data sources; see [docs/PROVIDERS.md](docs/PROVIDERS.md) |
| `econpulse/feed.py` | Fetching, fallback and the local cache |
| `econpulse/i18n.py`, `locales/` | Languages; see [docs/TRANSLATING.md](docs/TRANSLATING.md) |
| `econpulse/system.py` | Operating-system integration (start at login, monitors, single instance, safe links) |
| `econpulse/theme.py` | Palettes, fonts, icons, HiDPI scaling |
| `tools/` | Windows build, SBOM, screenshots and demo animation, README artwork, release notes |
| `site/` | The project website, published to GitHub Pages by `.github/workflows/pages.yml` |

For the bigger picture, with diagrams, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Guidelines

- Keep the app dependency-light. The interface is plain Tkinter drawn on canvases.
- Every interface string goes through `tr()` (or the `label`/`btn` helpers, which call it) and needs a Persian translation. `tests/test_translations.py` checks this.
- Never add code that reads web pages from sites whose terms forbid automated access. New data sources must have terms that allow this kind of use; see [docs/PROVIDERS.md](docs/PROVIDERS.md).
- Links opened from data go through `system.safe_open()`, which only opens https URLs.
- Screenshots in `docs/screenshots/` and the demo animation are made with `python tools/screenshots.py --gif` (Windows). It uses demo data and captures only the app's own windows. Then `python tools/brand_assets.py` rebuilds the hero images, the logo and the social-preview card in `docs/assets/`.
- Dependencies are pinned with hashes in `requirements.lock` (the app, for every platform), `requirements-build.lock` and `requirements-dev.lock`. To change one, edit `requirements.txt` or the matching `.in` file and regenerate the lock with the command at the top of the file. CI and `run.sh` only install hash-checked packages, and `tests/test_project.py` enforces it.

## Pull requests

Keep each pull request focused on one change. Describe what changed and how you tested it, and add an entry under **Unreleased** in [CHANGELOG.md](CHANGELOG.md). By contributing you agree that your work is released under the [MIT licence](LICENSE), and to follow the [code of conduct](CODE_OF_CONDUCT.md).

## Releasing (maintainers)

1. Set `__version__` in `econpulse/__init__.py`, and `version` and `date-released` in `CITATION.cff`. Move the **Unreleased** notes in `CHANGELOG.md` (and `CHANGELOG_FA.md`) to a new `## [x.y.z]` section. `tests/test_project.py` checks that these agree.
2. Commit, then tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. The **Release** workflow tests and builds the Windows zip, writes the SBOM and checksums, signs the build provenance, and opens a **draft** release. Check it, then publish it.
