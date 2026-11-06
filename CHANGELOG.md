# Changelog

Notable changes to BILE Workbench are recorded here.

## [0.1.0-rc.1] — 2026-11-06

Initial public pre-release candidate.

- Productized the reference-only Project Model and ordered Edit Set workflow.
- Added the existing-BILE overlay compiler with intermediate validation and atomic candidate publication.
- Added canonical candidate validation that independently replays edits and compares the candidate byte-for-byte.
- Integrated Project Workflow Service into the desktop UI while preserving the existing preview/edit-session boundary.
- Added Windows x64 one-folder packaging and CI for Python 3.11, 3.12 and 3.13.
- Retained the documented conservative editing boundary: full structural reconstruction remains experimental.
- Release acceptance is limited to automated public tests and Windows packaging. Real desktop interaction and target-game acceptance remain pending.
