"""scripts/license_audit.py: classification and rendering of the third-party license report."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "license_audit", Path(__file__).resolve().parents[2] / "scripts" / "license_audit.py"
)
license_audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["license_audit"] = license_audit
SPEC.loader.exec_module(license_audit)


def test_classify_gpl_and_agpl():
    assert license_audit.classify("GPL-2.0-only") == "strong-copyleft (GPL)"
    assert license_audit.classify("GNU Affero General Public License v3") == "strong-copyleft (AGPL)"


def test_classify_agpl_spelled_out_as_affero():
    """PyMuPDF declares its license this way; it must land under the GPL/AGPL flags."""
    pymupdf = "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"
    assert license_audit.classify(pymupdf) == "strong-copyleft (AGPL)"
    assert license_audit.classify("AGPL-3.0-or-later") == "strong-copyleft (AGPL)"
    assert license_audit.classify(pymupdf) in license_audit.FLAGGED_CATEGORIES


def test_classify_gpl_variants():
    for text in ("GNU GENERAL PUBLIC LICENSE", "GPL", "GPL v3", "GPLv3+", "GPL-3.0-or-later", "GNU GPL 2.0"):
        assert license_audit.classify(text) == "strong-copyleft (GPL)", text


def test_classify_lgpl_is_not_mistaken_for_gpl():
    """Both "lgpl-3.0" and "lgplv3" contain "gpl-3"/"gplv3": LGPL must be matched before plain GPL."""
    for text in (
        "LGPL-3.0-or-later",
        "LGPLv3",
        "LGPL-2.1",
        "GNU Lesser General Public License v2 or later (LGPLv2+)",
        "GNU Library or Lesser General Public License (LGPL)",
        "GNU Library General Public License v2",
    ):
        assert license_audit.classify(text) == "weak-copyleft (LGPL)", text


def test_classify_permissive():
    assert license_audit.classify("MIT License") == "permissive (MIT)"
    assert license_audit.classify("BSD-3-Clause") == "permissive (BSD)"
    assert license_audit.classify("Apache Software License") == "permissive (Apache-2.0)"
    assert license_audit.classify("Apache License, Version 2.0") == "permissive (Apache-2.0)"
    assert license_audit.classify("ISC") == "permissive (ISC)"


class _FakeDist:
    def __init__(self, fields: dict[str, str], classifiers: list[str] | None = None):
        self._fields = fields
        self._classifiers = classifiers or []
        self.metadata = self

    def get(self, key: str, default=None):
        return self._fields.get(key, default)

    def get_all(self, key: str):
        return self._classifiers if key == "Classifier" else None


def test_license_expression_is_read_before_license_and_classifiers():
    """PEP 639 wheels often declare only ``License-Expression``; it must not read as "(none declared)"."""
    assert license_audit._license_text(_FakeDist({"License-Expression": "MIT"})) == "MIT"
    both = _FakeDist({"License-Expression": "BSD-3-Clause", "License": "see LICENSE file"})
    assert license_audit._license_text(both) == "BSD-3-Clause"
    legacy = _FakeDist({"License": "GPL-2.0-only"})
    assert license_audit._license_text(legacy) == "GPL-2.0-only"
    only_classifier = _FakeDist({}, ["License :: OSI Approved :: MIT License"])
    assert license_audit._license_text(only_classifier) == "MIT License"
    assert license_audit._license_text(_FakeDist({})) == ""


def test_classify_unknown_for_empty_or_unmatched():
    assert license_audit.classify("") == "unknown"
    assert license_audit.classify("Some Bespoke License 1.0") == "unknown"


def test_collect_python_entries_finds_this_projects_own_dependencies():
    entries = license_audit.collect_python_entries()
    names = {e.name.lower() for e in entries}
    assert "fastapi" in names
    assert "beancount" in names


def test_beancount_is_flagged_gpl():
    entries = license_audit.collect_python_entries()
    beancount = next(e for e in entries if e.name.lower() == "beancount")
    assert beancount.category in license_audit.FLAGGED_CATEGORIES


def test_pymupdf_is_flagged_agpl():
    entries = license_audit.collect_python_entries()
    pymupdf = next(e for e in entries if e.name.lower() == "pymupdf")
    assert pymupdf.category == "strong-copyleft (AGPL)"


def test_render_includes_posture_note_when_flagged():
    entries = license_audit.collect_python_entries()
    doc = license_audit.render(entries, [], "npm not installed")
    assert "Beancount" in doc
    assert "PyMuPDF" in doc
    assert "posture" in doc.lower()
    assert "GPL/AGPL flags" in doc


def test_render_is_self_contained():
    """The generated header and posture note must not point at sections of other documents."""
    flagged = license_audit.Entry("beancount", "3.0", "GPL-2.0-only", "strong-copyleft (GPL)")
    doc = license_audit.render([flagged], [], "npm not installed")
    assert "**Project posture:**" in doc
    assert "§" not in doc


def test_shorten_caps_a_multi_line_license_blob():
    blob = "GNU GENERAL PUBLIC LICENSE\nVersion 2, June 1991\n\nCopyright ..."
    assert license_audit._shorten(blob) == "GNU GENERAL PUBLIC LICENSE"
