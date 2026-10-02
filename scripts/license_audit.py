"""License audit: classify every installed Python distribution's license and, when the
web-ui's npm deps are installed, its licenses too. Writes ``docs/LICENSES.md``.

Classification is a best-effort text match over the distribution's ``License-Expression``
(PEP 639) or ``License`` metadata field and its PyPI classifiers — good enough to flag
GPL/AGPL for a human to double check, not a substitute for a real legal review. Anything that
cannot be classified is ``unknown`` and listed, never silently dropped.

Usage:  uv run python scripts/license_audit.py
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "LICENSES.md"

#: (regex, category) searched in order in the lowercased license text — first match wins.
#: Order matters: the copyleft families come before the permissive ones, and within copyleft
#: the specific families come before plain GPL, because "lgpl-3.0", "lgplv3" and
#: "gnu affero gpl 3.0" all contain "gpl". ``\bgpl`` matches "gpl", "gpl-2.0", "gplv3" and
#: "gpl 3.0" but not the "gpl" inside "lgpl"/"agpl".
_PATTERNS: list[tuple[str, str]] = [
    (r"affero|\bagpl", "strong-copyleft (AGPL)"),
    (r"lesser general public license|library general public license|\blgpl|\blesser gpl",
     "weak-copyleft (LGPL)"),
    (r"general public license|\bgpl", "strong-copyleft (GPL)"),
    (r"mozilla public license|mpl-2", "weak-copyleft (MPL)"),
    (r"eclipse public license|epl-", "weak-copyleft (EPL)"),
    (r"mit license", "permissive (MIT)"),
    (r"mit", "permissive (MIT)"),
    (r"bsd", "permissive (BSD)"),
    (r"apache software license", "permissive (Apache-2.0)"),
    (r"apache license", "permissive (Apache-2.0)"),
    (r"apache-2\.0", "permissive (Apache-2.0)"),
    (r"apache2", "permissive (Apache-2.0)"),
    (r"apache 2\.0", "permissive (Apache-2.0)"),
    (r"isc license|\bisc\b", "permissive (ISC)"),
    (r"python software foundation", "permissive (PSF)"),
    (r"psf", "permissive (PSF)"),
    (r"public domain", "permissive (public domain)"),
    (r"unlicense", "permissive (public domain)"),
    (r"zope public license", "permissive (ZPL)"),
]

FLAGGED_CATEGORIES = {"strong-copyleft (GPL)", "strong-copyleft (AGPL)"}

POSTURE_NOTE = (
    "Beancount (GPL-2.0) is used unmodified as an external command-line/library engine, "
    "invoked via its published API — it is not linked into a distributed derivative work of "
    "Aurum and is never modified. PyMuPDF (AGPL-3.0, or a commercial license from Artifex) is "
    "likewise used unmodified, as a library through its published Python API, to extract text "
    "from PDFs (law-corpus ingest and credit-report parsing). Both are installed from PyPI under "
    "their own licenses. Whether this use creates obligations for Aurum's own code (including the "
    "AGPL's network-use clause) is a legal question this script does not settle: re-verify it with "
    "counsel before any relicensing or distribution decision; this script is not legal advice."
)


@dataclass
class Entry:
    name: str
    version: str
    license_text: str
    category: str


_MAX_LICENSE_TEXT_LEN = 80


def _shorten(text: str) -> str:
    """Some packages (beangulp, ...) put the *entire* GPL text in the License field.

    Keep only the first line and cap the length, so the table stays a table.
    """
    first_line = text.strip().splitlines()[0].strip() if text.strip() else ""
    if len(first_line) > _MAX_LICENSE_TEXT_LEN:
        first_line = first_line[:_MAX_LICENSE_TEXT_LEN].rstrip() + "..."
    return first_line


def _license_text(dist: metadata.Distribution) -> str:
    # PEP 639: an SPDX ``License-Expression`` is authoritative when present (newer wheels often
    # declare only this field and leave ``License`` empty).
    expression = dist.metadata.get("License-Expression") or ""
    if expression.strip():
        return _shorten(expression)
    raw = dist.metadata.get("License") or ""
    if raw and raw.strip() and raw.strip().upper() != "UNKNOWN":
        return _shorten(raw)
    classifiers = dist.metadata.get_all("Classifier") or []
    license_classifiers = [c for c in classifiers if c.startswith("License ::")]
    if license_classifiers:
        return "; ".join(c.split("::")[-1].strip() for c in license_classifiers)
    return ""


def classify(license_text: str) -> str:
    lowered = license_text.lower()
    if not lowered:
        return "unknown"
    for pattern, category in _PATTERNS:
        if re.search(pattern, lowered):
            return category
    return "unknown"


def collect_python_entries() -> list[Entry]:
    entries: list[Entry] = []
    seen: set[str] = set()
    for dist in metadata.distributions():
        name = dist.metadata.get("Name") or dist.metadata.get("Summary") or "?"
        if name in seen:
            continue
        seen.add(name)
        version = dist.version or "?"
        license_text = _license_text(dist)
        entries.append(Entry(name, version, license_text or "(none declared)", classify(license_text)))
    entries.sort(key=lambda e: e.name.lower())
    return entries


def collect_npm_entries() -> tuple[list[Entry], str | None]:
    """Returns (entries, note). ``note`` explains why the list is empty, if it is."""
    web_ui = ROOT / "web-ui"
    node_modules = web_ui / "node_modules"
    if not node_modules.exists():
        return [], (
            "web-ui/node_modules is not installed in this environment. Run "
            "`cd web-ui && npm install && npm ls --json --omit=dev` and re-run this script "
            "to include npm dependency licenses."
        )
    # On Windows npm is a .cmd shim, which subprocess only finds through its full path.
    npm = shutil.which("npm") or "npm"
    try:
        proc = subprocess.run(
            [npm, "ls", "--json", "--omit=dev", "--all", "--long"],  # --long adds each package's license
            cwd=web_ui,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"`npm ls` failed to run: {exc}"

    try:
        tree = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [], "`npm ls --json` did not return parseable JSON."

    entries: list[Entry] = []
    seen: set[str] = set()

    def walk(deps: dict) -> None:
        for pkg_name, info in (deps or {}).items():
            if "version" not in info:  # an optional dependency that is not installed (other platforms)
                continue
            version = info["version"]
            key = f"{pkg_name}@{version}"
            if key not in seen:
                seen.add(key)
                license_text = info.get("license") or "(none declared)"
                entries.append(Entry(pkg_name, version, str(license_text), classify(str(license_text))))
            walk(info.get("dependencies") or {})

    walk(tree.get("dependencies") or {})
    entries.sort(key=lambda e: e.name.lower())
    return entries, None


def _table(entries: list[Entry]) -> str:
    lines = ["| Package | Version | License | Category |", "|---|---|---|---|"]
    for e in entries:
        safe_license = e.license_text.replace("|", "/").replace("\n", " ")
        lines.append(f"| {e.name} | {e.version} | {safe_license} | {e.category} |")
    return "\n".join(lines)


def _summary(entries: list[Entry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.category] = counts.get(e.category, 0) + 1
    return counts


def render(python_entries: list[Entry], npm_entries: list[Entry], npm_note: str | None) -> str:
    py_summary = _summary(python_entries)
    npm_summary = _summary(npm_entries)
    py_flagged = [e for e in python_entries if e.category in FLAGGED_CATEGORIES]
    npm_flagged = [e for e in npm_entries if e.category in FLAGGED_CATEGORIES]

    lines = [
        "# Third-party licenses",
        "",
        "Generated by `scripts/license_audit.py` (`uv run python scripts/license_audit.py`). "
        "Classification is a best-effort match on each package's declared `License-Expression` / "
        "`License` metadata / PyPI classifiers (npm: its `license` field) — not a legal opinion. "
        "Anything unmatched is `unknown` and listed rather than dropped.",
        "",
        "## Summary",
        "",
        "### Python (uv/pip environment)",
        "",
        f"Total packages: **{len(python_entries)}**",
        "",
    ]
    for category, count in sorted(py_summary.items()):
        lines.append(f"- {category}: {count}")
    lines += ["", "### web-ui (npm)", ""]
    if npm_note:
        lines.append(f"*{npm_note}*")
    else:
        lines.append(f"Total packages: **{len(npm_entries)}**")
        lines.append("")
        for category, count in sorted(npm_summary.items()):
            lines.append(f"- {category}: {count}")

    lines += ["", "## GPL/AGPL flags", ""]
    if not py_flagged and not npm_flagged:
        lines.append("None found.")
    else:
        if py_flagged:
            lines.append("**Python:**")
            for e in py_flagged:
                lines.append(f"- `{e.name}=={e.version}` — {e.category} ({e.license_text})")
        if npm_flagged:
            lines.append("**npm:**")
            for e in npm_flagged:
                lines.append(f"- `{e.name}@{e.version}` — {e.category} ({e.license_text})")
        lines.append("")
        lines.append(f"**Project posture:** {POSTURE_NOTE}")

    lines += [
        "",
        "## Python packages",
        "",
        _table(python_entries),
        "",
        "## web-ui (npm) packages",
        "",
    ]
    if npm_note:
        lines.append(f"*{npm_note}*")
    else:
        lines.append(_table(npm_entries))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    python_entries = collect_python_entries()
    npm_entries, npm_note = collect_npm_entries()
    doc = render(python_entries, npm_entries, npm_note)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(doc, encoding="utf-8")

    py_flagged = [e for e in python_entries if e.category in FLAGGED_CATEGORIES]
    print(f"Python packages: {len(python_entries)}")
    for category, count in sorted(_summary(python_entries).items()):
        print(f"  {category}: {count}")
    if npm_note:
        print(f"npm: {npm_note}")
    else:
        print(f"npm packages: {len(npm_entries)}")
        for category, count in sorted(_summary(npm_entries).items()):
            print(f"  {category}: {count}")
    if py_flagged:
        print("GPL/AGPL flagged (Python):", ", ".join(f"{e.name}=={e.version}" for e in py_flagged))
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
