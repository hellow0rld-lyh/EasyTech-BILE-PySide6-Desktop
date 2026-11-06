# Changelog

Notable user-facing changes are recorded here. Versioned sections describe the corresponding tagged source; documentation-only changes made after a tag are listed under Unreleased.

## [Unreleased]

- Reworked the project README around installation, first use, supported workflows and explicit safety boundaries.
- Added a categorized documentation index and removed links to research files that are not present in the public repository.
- Clarified the published pre-release baseline and separated automated, desktop and in-game acceptance states.
- Marked dated delivery and increment reports as historical snapshots.

## [0.1.0-rc.1] — 2026-11-06

Initial public pre-release candidate.

- Productized the reference-only Project Model and ordered Edit Set workflow.
- Added the existing-BILE overlay compiler with intermediate validation and atomic candidate publication.
- Added canonical candidate validation that independently replays edits and compares the candidate byte-for-byte.
- Integrated Project Workflow Service into the desktop UI while preserving the existing preview/edit-session boundary.
- Added Windows x64 one-folder packaging and CI for Python 3.11, 3.12 and 3.13.
- Retained the documented conservative editing boundary: full structural reconstruction remains experimental.
- Release acceptance is limited to automated public tests and Windows packaging. Real desktop interaction and target-game acceptance remain pending.
