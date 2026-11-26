# Governance

EconPulse is maintained by **Aref Hosseini** and **Kasra Sartaee**, who share final say on what goes in and when it's released.

## How changes get in

- Every change goes through a pull request, including the maintainers' own.
- A pull request needs **one approving review from a maintainer other than its author**, and every CI check passing.
- Changes to the data sources, network code or security-sensitive files (`econpulse/providers/`, `econpulse/storage.py`, `econpulse/system.py`, `.github/`) get an extra careful review. [CODEOWNERS](.github/CODEOWNERS) requests a maintainer's review on every pull request automatically.
- When the two maintainers disagree, the change waits until they agree. Nothing is merged over an objection.

## Data sources

A new or changed data source needs its terms of use checked first, and the result is written down in its pull request ([docs/PROVIDERS.md](docs/PROVIDERS.md)). EconPulse never reads a website in a way its terms forbid.

## Becoming a maintainer

Anyone who has made several good contributions over a few months, and reviewed others' pull requests, can be invited by both maintainers.

## Security reports

Reports go to the maintainers privately, as described in [SECURITY.md](SECURITY.md). Either maintainer may publish a fix without waiting for the other.

## Code of conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
