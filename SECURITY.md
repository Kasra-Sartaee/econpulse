# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: on the repository's **Security** tab, choose **Report a vulnerability** (private vulnerability reporting). Don't open a public issue for security problems.

Include what you found, how to reproduce it, and the version (Settings → About). We aim to reply within a week and will credit you in the release notes unless you prefer otherwise.

Supported versions: the latest release.

## What EconPulse does on your computer

**Network.** The app connects only to:

| Destination | When |
|---|---|
| `biquote.io` | Calendar refresh with the default data source (at most every 15 minutes) |
| `nfs.faireconomy.media` | Forex Factory's official weekly export: the fallback, or when selected (at most hourly) |
| `www.financecalendar.com` | Only if you select it and enter your own API key |
| `api.github.com` | Only if you switch on the update notice (once a day; off by default) |

All requests use HTTPS and identify the app as `EconPulse/<version> (+project URL)`. Nothing about you or your settings is sent. Responses are capped in size, and every field is length-limited when parsed.

**Local files** live in your data folder (`%APPDATA%\EconPulse` on Windows, `~/Library/Application Support/EconPulse` on macOS, `~/.config/EconPulse` on Linux):

- `settings.json`: preferences, including your FinanceCalendar.com API key if you entered one (plain text, readable by your user account);
- `cache-v4.json`, `ff-export-v4.json`: the last calendar data;
- `fired.json`: which alerts were already shown;
- `notes.txt`: your trading notes (plain text);
- `econpulse.log`: errors and warnings (at most about 0.5 MB). It never contains your API key.

There is no telemetry.

**Hardening.** The app never runs anything it downloads:

- Links from calendar data open only if they are plain `https://` URLs.
- CSV exports neutralise cells that spreadsheets would run as formulas.
- Damaged or edited settings fall back to safe defaults.
- Releases are built only by GitHub Actions, from pinned, hash-checked dependencies. Each one ships SHA-256 checksums, a CycloneDX software bill of materials (SBOM) and signed build provenance. Verify a download with `gh attestation verify EconPulse-<version>-Windows.zip --repo Kasra-Sartaee/econpulse`.
- Every change is checked by CodeQL, `bandit` and `pip-audit`. OpenSSF Scorecard tracks supply-chain practices, and Dependabot proposes dependency and Action updates. Workflows run with read-only tokens by default, and every Action is pinned to a commit hash.
