# Changelog

All notable changes to EconPulse. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/). Persian notes: [CHANGELOG_FA.md](CHANGELOG_FA.md).

## [Unreleased]

### Added
- **Compact ticker-bar widget mode**: toggleable single-line floating bar (`Ctrl+M`, widget header button, or tray menu) showing the next high-impact release, forecast, and live countdown, plus magnetic edge-snapping and a quick Always-on-Top pin toggle.
- **Starred watchlist & per-event release notes**: star any indicator in Release Details to highlight it in lists and receive alerts even for medium/low-impact releases, and attach private notes (`event-notes.json`) that persist across recurring releases.
- **"Result published" alerts**: one notification when Actual values arrive for watched releases (skipped for releases more than 30 minutes old, e.g. after a laptop wake). Clicking a notification opens that release's details.
- **Fast check after high-impact releases** (opt-in, off by default): one refresh 45 s and one 3 min after each watched release *time* still missing its Actual, however many releases share that minute. Never while the source is failing or backing off, and never on a schedule-only source.
- **Revision tracking**: shows `Previous revised from …` in Release Details when a provider supplies `revisedPrevious`.
- **Expanded trading time zones** (18 global financial centres) and **Preferences controls** for widget opacity, refresh interval, compact bar, Actual alerts, burst polling, and an opt-in live `next.json` status file for OBS / Stream Deck / scripts.
- **Keyboard accessibility & shortcuts**: `Tab` focus rings and `Space`/`Enter` activation on custom canvas controls, plus `Ctrl+1..5` (views), `Ctrl+,` (Preferences), `Ctrl+E` (Export), `Ctrl+N` (Notes), `Ctrl+W` (Widget), and `Ctrl+M` (Compact bar).
- **Windows Focus Assist / Fullscreen awareness**: alert sounds respect Windows Do-Not-Disturb / presentation / fullscreen state (`SHQueryUserNotificationState`).

### Changed
- **Faster, lighter networking & idle loop**: gzip responses with a hard zip-bomb cap, conditional `ETag` / `If-Modified-Since` (`304 Not Modified`) support, concurrent weekly fetches for biquote, adaptive idle polling, skipping offscreen per-minute renders when hidden in the tray, binary-search sticky headers, and bounded LRU text/image caches.
- **Pure-Python state module** (`econpulse/state.py`) and unified `Event.to_record()` serialization.
- **Complete locale-driven i18n**: removed hardcoded Persian strings from core UI code, translated dialog titles/warnings, and made the system-tray menu update live when switching languages.
- **Trimmed Windows PyInstaller bundle** by excluding unused stdlib modules.

### Security
- **Hardened HTTP redirects**: refuse non-HTTPS or non-public/localhost redirect targets, enforce TLS 1.2+, and strip `X-API-Key` / `Authorization` / `Cookie` headers on cross-origin redirects.
- **Encrypted API key on Windows (DPAPI)** and private `0700`/`0600` file permissions on POSIX, plus atomic writes (with Windows lock retries) for settings, caches, and trading notes.
- **Sanitised `Event.uid` & `time_label`**, hardened ICS carriage-return escaping (with fuzz assertions), tightened CSV formula neutralisation against leading whitespace/newlines/pipes, blocked localhost/non-public targets in `safe_open()`. Provider ids with unusual characters are replaced by a hash, so two different ids can never merge into one release.
- `RUN_WINDOWS.bat` installs the hash-locked packages into a private `.venv` (reinstalled when `requirements.lock` changes) instead of changing the system Python.

### Fixed
- Summary bar counts (`render_stats`) now respect `other_currencies` consistently with the calendar table.
- Switching data sources while a refresh is in flight now supersedes and discards stale responses instead of dropping the switch.
- A transient failure writing `fired.json` no longer suppresses alert notifications, and corrupted `fired.json` files no longer crash startup.
- Right-to-left (Persian) widget resizing from the bottom-left corner now anchors the right edge and uses the matching diagonal cursor.
- Multi-monitor tooltips, dropdowns, and saved widget positions now clamp to the active monitor (including monitors left of or above primary).
- Preserved non-major currencies in `settings.json` when toggling filter chips or saving Preferences.
- Fixed literal `<version>` and `<owner>` placeholders in `tools/release_notes.py`.
- Pruning the stored alert history (above 4,000 entries) no longer deletes every entry for provider ids that contain `:` (all biquote ids), which could repeat alerts.

## [3.3.0] - 2026-11-20

First open-source release.

### Changed
- **New data sources.** The default is [biquote](https://biquote.io/): free, no key, with Actual, Forecast and Previous values for about 50 countries. Forex Factory's official weekly export (schedule, no Actual values) is the automatic fallback. Data from official agencies is available through [FinanceCalendar.com](https://www.financecalendar.com/api/) with your own API key. EconPulse no longer reads forexfactory.com web pages, and the app identifies itself honestly in every request.
- When the selected source fails, a recent saved copy with Actual values is shown first, before the schedule-only fallback.
- The Actual value is no longer coloured better/worse when a source doesn't say which it is.
- By default, only the nine major currencies are shown. A new setting adds the others (ZAR, TRY, MXN...).
- Faster start: the Windows app is a folder (`EconPulse.exe` + `_internal`) and opens in about 0.25 s instead of 1.7 s.
- The code is now an `econpulse` package (`python -m econpulse`), with an installable `pyproject.toml`.
- Running from source now needs Python 3.11 or newer (3.10 reached end of life in October 2026, and Pillow 13's security fixes need 3.11). The Windows download includes its own Python.

### Added
- **Polite polling**: automatic backoff after failures (30 → 60 → 120 min), respect for a source's `Retry-After`, and the next attempt time shown in the status line.
- **Settings → Data source**, **Updates** and **About** sections. About has *Project page*, *Report an issue*, *Open data folder* and *Copy diagnostics* (privacy-safe text for bug reports).
- Opt-in update notice that checks GitHub once a day. It is off by default.
- Start at login on Linux (XDG autostart) and macOS (LaunchAgent), and a single-instance lock on both. Linux and macOS support is experimental.
- Keyboard scrolling in lists (arrows, Page Up/Down, Home, End).
- Language registry and translation guide (`docs/TRANSLATING.md`), with a test that every interface string is translated.
- Guide for adding data sources (`docs/PROVIDERS.md`) and an architecture guide with diagrams (`docs/ARCHITECTURE.md`).
- Project website (GitHub Pages), a demo animation, and tools that regenerate the screenshots and artwork from the real app.
- CI on Windows, macOS and Linux with a test-coverage floor (84% today), and a downloadable Windows build for every change. Release and CI workflows, CodeQL and OpenSSF Scorecard.
- Fuzzing of every parser for downloaded data (Atheris in CI, plus a quick deterministic version in the test suite).
- End-to-end UI tests for every window, and checks that versions agree, documentation links resolve and every dependency stays pinned.

### Security
- Links from calendar data open only if they are plain `https://` URLs. The button shows the destination.
- CSV exports neutralise cells that spreadsheets would run as formulas.
- Settings are validated on load, so a damaged settings file falls back to defaults.
- Every text field from a data source is length-capped.
- Release builds use pinned, hash-checked dependencies. Each release ships SHA-256 checksums, a CycloneDX software bill of materials and signed build provenance.
- Pillow upgraded to 13.0 (fixes known vulnerabilities in 12.x).
- CI runs `bandit` and `pip-audit`, and a test rejects hidden bidirectional control characters in source code ("Trojan Source").

### Fixed
- Search-box listeners piling up after theme or language changes.
- Settings defaults could be changed by mistake through a shared list.
- Timers firing during exit.
- Quitting while an alert pop-up was on screen could leave EconPulse running with no window.
- Found by fuzzing: a release dated near the year 1 or 9999 broke drawing in every time zone (now ignored), and unusual figures from biquote (huge numbers, odd units or decimal places) could stop a refresh. Unexpected data from any source now falls back to saved data or the Forex Factory export instead of failing.

### Removed
- Reading forexfactory.com pages, the BeautifulSoup dependency, and leftover 3.1 compatibility code.

## [3.2.0] - 2026-11-12

### Added
- Complete visual redesign: graphite palettes, Windows 11 typography and icons, anti-aliased shapes, native rounded corners, signal-bar impact markers, sticky day headings, and a "next high-impact release" countdown in the widget.
- Persian with a fully mirrored right-to-left layout, Solar Hijri dates and Persian digits.
- Full HiDPI support.

### Changed
- Virtualised lists (only visible rows are drawn), debounced search, and per-second updates limited to changed items.
- Single-instance guard, error log, RFC 5545-compliant ICS export.

## [3.1.0] - 2026-11-11

### Added
- Compact header and summary bar with Hide summary; day sections and a sticky day heading in the weekly widget; tray menu with "Open last view".

## [3.0.0] - 2026-11-11

### Added
- Forex Factory as the data source, with Actual/Forecast/Previous values, bank holidays, Today/Week widget views and countdowns.

[Unreleased]: https://github.com/Kasra-Sartaee/econpulse/compare/v3.3.0...HEAD
[3.3.0]: https://github.com/Kasra-Sartaee/econpulse/releases/tag/v3.3.0
