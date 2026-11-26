# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: on the repository's **Security** tab, choose **Report a vulnerability** (private vulnerability reporting). Don't open a public issue for security problems.

Include what you found, how to reproduce it, and the version (Settings → About). We aim to reply within a week and will credit you in the release notes unless you prefer otherwise.

Supported versions: the latest release.

## What EconPulse does on your computer

**Network.** The app connects only to:

| Destination | When |
|---|---|
| `biquote.io` | Calendar refresh with the default data source: at most every 15 minutes, and then only yesterday to tomorrow, with the full three weeks hourly (about 6 small requests an hour). Two extra checks after a watched release only if you turn on *Fast check after high-impact releases* |
| `nfs.faireconomy.media` | Forex Factory's official weekly export: the fallback, or when selected (at most hourly) |
| `www.financecalendar.com` | Only if you select it and enter your own API key |
| `api.github.com` | Only if you switch on the update notice (once a day; off by default), and when you choose to install an update |
| `github.com` (release downloads) | Only when you choose to install an update: the installer and its checksum file |

All requests use HTTPS and identify the app as `EconPulse/<version> (+project URL)`. Nothing about you or your settings is sent. Responses are capped in size, and every field is length-limited when parsed.

**Local files** live in your data folder (`%APPDATA%\EconPulse` on Windows, `~/Library/Application Support/EconPulse` on macOS, `~/.config/EconPulse` on Linux):

- `settings.json`: preferences. Your optional FinanceCalendar.com API key is encrypted for your user account with Windows DPAPI on Windows; on macOS and Linux it goes to the system keychain (Keychain, Secret Service) when the optional `keyring` package is installed, and otherwise stays in this file. On macOS and Linux the data folder (`0700`) and settings/notes files (`0600`) are restricted to your user account;
- `history.json`: past releases (figures only), so the details window can show an indicator's history;
- `cache-v4.json`, `ff-export-v4.json`: the last calendar data;
- `fired.json`: which alerts were already shown;
- `notes.txt`, `event-notes.json`: your global and per-indicator trading notes (local only, written atomically);
- `next.json`: optional live status snapshot (only written if enabled in Settings);
- `econpulse.log`: errors and warnings (at most about 0.5 MB). It never contains your API key.

There is no telemetry.

**Hardening.** The app never runs anything it downloads:

- All network requests require TLS 1.2+ over HTTPS to public hosts; redirects cannot downgrade to HTTP, cannot target localhost/private networks, and strip `X-API-Key` / `Authorization` headers across origins. Gzip responses enforce a hard decompressed size cap against zip bombs.
- Known limit: the public-host check looks at the address as written. It does not resolve a host name to see whether it points to a private address (DNS rebinding). That is acceptable today: the app only ever requests its own fixed endpoints, and only the optional FinanceCalendar.com request carries a secret. It will be revisited if the app ever follows arbitrary links with credentials.
- Links from calendar data open only if they are plain `https://` URLs to public hosts.
- CSV exports neutralise cells that spreadsheets would run as formulas, and ICS exports sanitise `UID` values and carriage returns.
- Damaged or edited settings fall back to safe defaults.
- **Updates never run anything unverified.** Only a copy installed with the Setup.exe updates itself, and only when you confirm. The installer is downloaded from this repository's own release, must match the release's `SHA256SUMS.txt`, and must have a GitHub build attestation from this repository's release workflow; otherwise it is deleted and nothing runs. It installs per user, without administrator rights.
- Releases are built only by GitHub Actions, from pinned, hash-checked dependencies. Each one ships SHA-256 checksums, a CycloneDX software bill of materials (SBOM) and signed build provenance. Verify a download with `gh attestation verify EconPulse-<version>-Windows.zip --repo Kasra-Sartaee/econpulse`.
- Every change is checked by CodeQL, `bandit` and `pip-audit`, and the parsers for downloaded data are fuzzed with Atheris (`fuzz/`). OpenSSF Scorecard tracks supply-chain practices, and Dependabot proposes dependency and Action updates. Workflows run with read-only tokens by default, and every Action is pinned to a commit hash.
