# BILE Workbench — Release Process

## Before tagging

1. Start from a clean `main` worktree and verify the full HEAD.
2. Read `PRODUCT_GOVERNANCE.md`.
3. Update `pyproject.toml` and `src/bile_workbench/__init__.py` to the same PEP 440 version.
4. Add a changelog entry and `release-notes/vX.Y.Z-<channel>.N.md` for a pre-release.
5. Verify that the release contains no original game resources, private fixtures, credentials, generated candidates or signing material.
6. Run the local checks available in the development environment:

```powershell
python -m compileall -q src tests
python -m pip check
python -m unittest discover -s tests -v
git diff --check
```

Local test results must identify the actual Python version. The canonical supported matrix is Windows Python 3.11, 3.12 and 3.13 in GitHub Actions.

## CI and publication

A push of a version tag runs the Windows CI workflow: unit tests on Python 3.11/3.12/3.13; Windows x64 one-folder PyInstaller build on Python 3.11; executable and required theme-resource checks; and, for prerelease tags only, download of the build artifact from that exact workflow run, ZIP creation, SHA-256 generation, draft GitHub pre-release creation, asset upload and publication.

The workflow validates the tag format and requires a matching release note at `release-notes/<tag>.md`. Published assets:

- `BILEWorkbench-Windows-x64.zip` — complete one-folder bundle;
- `BILEWorkbench-Windows-x64.zip.sha256` — SHA-256 checksum.

If asset creation/upload fails, the workflow must not publish a partial release. A remaining draft is a recovery item and must be inspected before retrying.

## User installation

The Windows release is a portable one-folder bundle, not an installer:

1. Download the ZIP and its checksum file.
2. Verify the ZIP SHA-256 against the checksum file.
3. Extract the entire directory.
4. Run `BILEWorkbench.exe` from the extracted `BILEWorkbench` directory.

Do not copy the EXE out of its folder; Qt and application resources are bundled alongside it. The build is unsigned. Windows SmartScreen or antivirus may show an unfamiliar-app warning. No automatic updater is provided.

## Release status language

Release notes must distinguish automated tests from tests skipped because private fixtures are unavailable; package build success from real desktop launch/interaction; and offline format/candidate validation from target-game acceptance. Never describe a build-only result as “fully tested”, “game verified” or “stable”. Stable releases require a recorded human desktop acceptance. Game-specific behavior claims require separate target-game acceptance.

## Corrections

Never move or reuse a published tag. For a broken pre-release, publish a new incremented prerelease tag with corrected notes. If a release workflow leaves a draft, inspect its tag and uploaded assets before retrying; do not delete evidence or silently replace assets.
