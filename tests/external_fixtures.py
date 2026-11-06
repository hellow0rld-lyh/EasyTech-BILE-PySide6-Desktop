"""Helpers for optional, user-supplied game assets used by integration tests."""
from __future__ import annotations

import unittest
from pathlib import Path


def require_files(testcase: unittest.TestCase, *paths: Path, label: str = "external test fixtures") -> None:
    missing = [Path(path).name for path in paths if not Path(path).is_file()]
    if missing:
        testcase.skipTest(f"{label} not attached to this checkout: {', '.join(missing)}")


def require_triplet(testcase: unittest.TestCase, binary: Path, *, label: str = "BILE sample triplet") -> None:
    binary = Path(binary)
    image = next((candidate for candidate in (binary.with_suffix(".webp"), binary.with_suffix(".png")) if candidate.is_file()), None)
    required = [binary, binary.with_suffix(".xml")]
    if image is not None:
        required.append(image)
    else:
        required.append(binary.with_suffix(".webp"))
    require_files(testcase, *required, label=label)
