# BILE Workbench — Product Governance

- Policy-ID: BILE-WORKBENCH-PRODUCT-001
- Status: Active
- Product-ID: bile-workbench
- Product name: BILE Workbench
- Repository: hellow0rld-lyh/EasyTech-BILE-PySide6-Desktop
- Product class: Independent desktop developer tool
- License: MIT
- Current release: v0.1.0-rc.1 (public pre-release, 2026-11-06)

## 1. Product identity and boundary

BILE Workbench is an independently maintained Windows/Python/PySide6 desktop workbench for inspecting, previewing, diagnosing and conservatively editing EasyTech-style BILE animation resources. It also contains version-qualified, read-only Spine 3.8/4.1 analysis and preview capabilities where documented.

This repository is its own product boundary. It is not a WC4 repository or SO Variant, is not part of the EasyTech sibling-title repository's shared BTLX product, and is not a GOG3 project. Similar game or file-format subject matter does not create a source, binary, package, runtime or build dependency between those projects.

## 2. Product scope

The product may own:

- BILE BIN/XML/atlas parsing, structural validation and offline preview;
- version-qualified BILE v2/v3/v4 handling, respecting documented read-only/editable boundaries;
- conservative field editing, undo/redo and JSON interchange;
- reference-only Project Model and ordered Edit Set workflows;
- existing-BILE overlay compilation and canonical candidate validation;
- candidate comparison, diagnostics, experiment packaging and traceability;
- theme plugins and the documented desktop UI;
- documented read-only Spine evidence and preview paths.

The product does not claim unrestricted BILE reconstruction. New element creation, arbitrary frame insertion/deletion, string-table reordering, unsupported fields and other explicitly experimental operations remain unavailable or NoGo until separately qualified. Spine support must be described according to its actual read-only/static/preview scope; do not market it as a general Spine editor.

## 3. Data, licensing and third-party boundaries

- Source code and project-authored documentation are distributed under the repository's MIT license.
- Original game BIN/XML/atlas/image assets, APK/SO/DEX files, private fixtures, user projects and generated candidate resources are not included in public source or release assets.
- The Project Model is reference-only: it references external assets rather than silently copying or redistributing them.
- Do not bundle game assets merely to make a demo or test pass.
- Preserve author attribution and all applicable third-party license notices.
- EasyTech, Spine and other third-party names/marks belong to their respective owners. The project is an unofficial community tool and does not imply endorsement.
- Do not claim legal permission to redistribute game resources. Users remain responsible for rights to resources they supply or distribute.

## 4. Versioning

The canonical application version must match in both:

- pyproject.toml ([project].version, PEP 440);
- src/bile_workbench/__init__.py (__version__).

Git tags use a leading v and SemVer-style prerelease identifiers: stable vX.Y.Z; alpha vX.Y.Z-alpha.N; beta vX.Y.Z-beta.N; release candidate vX.Y.Z-rc.N. Map prerelease tags to PEP 440 versions (v0.1.0-rc.1 ↔ 0.1.0rc1). Published tags are immutable and must never be reused or moved. Breaking changes to file semantics or Project Model contracts require migration notes.

## 5. Release gates and evidence states

The following states are independent:

1. Research / format evidence;
2. Implementation;
3. Static validation and automated tests;
4. Windows package build and bundle-content checks;
5. Real desktop launch and interactive acceptance;
6. Target-game runtime acceptance for claims that depend on game behavior.

A successful test suite does not prove desktop interaction. A successful Windows build does not prove the app launches on a user's machine. Offline candidate validation does not prove a game accepts or displays the candidate correctly.

### Public pre-release minimum

- Release commit is reachable from main and has a clean, auditable source state.
- Canonical version fields and release notes agree.
- Windows CI passes the supported Python matrix (3.11–3.13).
- Windows x64 one-folder package is built and its executable and required bundled theme resources are checked.
- Release ZIP and SHA-256 checksum are generated from that same CI run.
- License/provenance review confirms no private or original game assets are included.
- Notes explicitly state unsigned status, desktop-acceptance status and game-runtime-acceptance limits.

A pre-release may be published before manual desktop/game acceptance only when those limits are plainly disclosed and no unsupported compatibility claim is made.

### Stable release minimum

In addition to the pre-release gates:

- A human records real desktop launch and core interaction acceptance against the release candidate.
- Known blockers are resolved or documented with an explicit NoGo.
- Any game-compatibility claim has separate, version-qualified target-game evidence.

Game acceptance is not implied by the general desktop release.

## 6. Current baseline

The first public pre-release v0.1.0-rc.1 was published on 2026-11-06. The tagged CI run passed the supported Python 3.11, 3.12 and 3.13 jobs and produced the unsigned Windows x64 one-folder package, ZIP and SHA-256 checksum.

The release establishes public automated-test and packaging evidence only. Real desktop launch/interaction acceptance and target-game runtime acceptance remain pending unless separately recorded in a later acceptance report. The 103 private-fixture-dependent tests skipped in each CI Python job are not counted as passes.
