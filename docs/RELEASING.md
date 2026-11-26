# Releasing EconPulse

For maintainers. A release is a tag. GitHub Actions builds everything; a person checks it and presses *Publish*.

## Cadence

A minor release (3.4, 3.5…) about every six weeks when there's something worth shipping, and a patch release (3.4.1) whenever a bug fix can't wait. Versions follow [Semantic Versioning](https://semver.org/).

## Before tagging

1. **CI is green on `main`**, including the lint job's type check and the Windows strict-order test run.
2. **Check the things CI can't**, on a real Windows machine, with the build from the CI run's *Windows build* artifact:
   - Enter and Space on the custom buttons and switches, with a real keyboard (the tests use synthetic key events);
   - the floating widget and the compact bar on a second monitor, including drag-to-edge snapping;
   - a desktop notification and its sound, then the same with Focus Assist on (no sound);
   - Windows' own contrast theme switches EconPulse to high contrast; 130 % text fits everywhere;
   - Persian: the whole layout mirrors, and the widget resizes from its left corner;
   - the compact bar docked at the top and at the bottom: maximised windows make room, and it steps back for a full-screen video;
   - Ctrl+Alt+E brings the widget up from another app (with the setting on).
3. **The visual check is green**, or its changes are intended and the new reference images are in `tests/visual/`.
4. **Write the changelogs.** Move *Unreleased* in `CHANGELOG.md` to `## [x.y.z] - YYYY-MM-DD` and update the link references at the bottom. Add the matching section to `CHANGELOG_FA.md` (a test fails until you do).
5. **Bump the version** in `econpulse/__init__.py` and `CITATION.cff` (`version` and `date-released`). A test checks that they agree.

## Tag and build

```sh
git tag v3.4.0
git push origin v3.4.0
```

The [release workflow](../.github/workflows/release.yml) refuses a tag that doesn't match the version. It runs the tests and builds the Windows zip from hash-checked tools. It installs Inno Setup (pinned by SHA-256) and builds the installer too. It then opens a **draft** release with the Setup.exe, the zip, a CycloneDX SBOM, `SHA256SUMS.txt` and a signed build-provenance bundle covering all three. Installed copies update from this release, so the Setup.exe must be attached and attested: the updater refuses anything else.

## Check the draft, then publish

Download the installer from the draft and verify it:

```sh
gh attestation verify EconPulse-3.4.0-Setup.exe --repo Kasra-Sartaee/econpulse
```

Install it once over the previous version (settings and notes must survive), then press **Publish release**. Publishing also starts the [PyPI workflow](../.github/workflows/publish.yml).

## PyPI (one-time setup)

The PyPI workflow uses [trusted publishing](https://docs.pypi.org/trusted-publishers/), so there's no token to store or leak. Before the first release:

1. On pypi.org, sign in and open **Your projects → Publishing → Add a new pending publisher**: project `econpulse`, owner `Kasra-Sartaee`, repository `econpulse`, workflow `publish.yml`, environment `pypi`.
2. On GitHub, **Settings → Environments → New environment** named `pypi`. Adding yourself as a required reviewer makes every upload wait for a click.

After that, each published release appears on PyPI within a few minutes, and `pipx install econpulse` installs it.

## winget (after publishing)

```sh
python tools/winget_manifest.py 3.4.0 --sums SHA256SUMS.txt   # the file from the release
winget validate --manifest dist/winget/3.4.0
```

Fork [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs), copy the three files to `manifests/k/KasraSartaee/EconPulse/3.4.0/`, and open a pull request. Microsoft's bots check it, usually within a day. Until the Windows build is code-signed, expect SmartScreen to be mentioned in review.

## Afterwards

- Post a short *What's new* in [Discussions](https://github.com/Kasra-Sartaee/econpulse/discussions), in English and Persian.
- Run the OpenSSF Scorecard workflow by hand, so the badge reflects the release.
