"""Per-collection ``sources.md``: standing notes about which material to trust.

Lives at ``AURUM_DATA_DIR/corpus_sources/<collection_id>/sources.md`` -- next to the
documents themselves, so the folder is the whole story for a collection.

It is markdown because a person edits it. The parser is deliberately forgiving: unknown
sections and unknown ``key: value`` lines are preserved in ``extra`` and written back out, so
hand edits survive a round trip.

The defaults are citation-priority settings relevant to law material. Note the asymmetry:
``sources.md`` is written *by the user* and is a legitimate instruction source about
which material to trust. Document text pulled into the corpus is not. The two never mix --
nothing in this file is rendered through ``sanitize.render_for_context``, and nothing
ingested ever lands here.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..core.config import Settings
from .store import collection_sources_dir

FILENAME = "sources.md"

SCALARS = ("jurisdiction", "language", "source_priority")
LISTS = {
    "trusted": "Trusted sources",
    "banned": "Banned sources",
    "preferred_authorities": "Preferred authorities",
}

_HEADING = re.compile(r"^#{1,6}\s+(.*\S)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
_KV = re.compile(r"^\s*(?:[-*+]\s+)?\*{0,2}([A-Za-z][A-Za-z _-]*?)\*{0,2}\s*:\s*(.*\S)\s*$")

_SECTION_ALIASES = {
    "trusted": "trusted",
    "trusted sources": "trusted",
    "banned": "banned",
    "banned sources": "banned",
    "preferred authorities": "preferred_authorities",
    "authorities": "preferred_authorities",
    "preferences": "_preferences",
    "notes": "_notes",
}


@dataclass
class SourcesSpec:
    """The parsed ``sources.md`` for one collection."""

    collection_id: str = ""
    jurisdiction: str = ""
    language: str = ""
    source_priority: str = ""
    trusted: list[str] = field(default_factory=list)
    banned: list[str] = field(default_factory=list)
    preferred_authorities: list[str] = field(default_factory=list)
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_banned(self, candidate: str) -> bool:
        needle = (candidate or "").lower()
        return any(entry.lower() in needle or needle in entry.lower() for entry in self.banned)


def path_for(collection_id: str, cfg: Settings | None = None) -> Path:
    return collection_sources_dir(collection_id, cfg) / FILENAME


def _normalise_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def parse(text: str, *, collection_id: str = "") -> SourcesSpec:
    spec = SourcesSpec(collection_id=collection_id)
    section: str | None = None
    notes: list[str] = []

    for line in (text or "").splitlines():
        heading = _HEADING.match(line)
        if heading:
            title = heading.group(1).strip()
            lowered = title.lower()
            section = _SECTION_ALIASES.get(lowered)
            if section is None:
                for alias, target in _SECTION_ALIASES.items():
                    if alias in lowered:
                        section = target
                        break
            if section is None and not spec.collection_id and lowered.startswith("sources"):
                section = "_preferences"
            continue

        bullet = _BULLET.match(line)
        payload = bullet.group(1) if bullet else line

        kv = _KV.match(payload if bullet else line)
        if kv and (section in (None, "_preferences") or _normalise_key(kv.group(1)) in SCALARS):
            key = _normalise_key(kv.group(1))
            value = kv.group(2).strip()
            if key in SCALARS:
                setattr(spec, key, value)
            elif key in LISTS:
                getattr(spec, key).extend(
                    part.strip() for part in value.split(";") if part.strip()
                )
            else:
                spec.extra[key] = value
            continue

        if bullet and section in LISTS:
            getattr(spec, section).append(bullet.group(1).strip())
            continue

        if section == "_notes" and line.strip():
            notes.append(line.rstrip())

    spec.notes = "\n".join(notes).strip()
    return spec


def render(spec: SourcesSpec) -> str:
    lines: list[str] = [f"# Sources — {spec.collection_id or 'collection'}", ""]
    lines.append("## Preferences")
    lines.append("")
    for key in SCALARS:
        lines.append(f"- {key}: {getattr(spec, key) or ''}")
    for key, value in sorted(spec.extra.items()):
        lines.append(f"- {key}: {value}")
    lines.append("")
    for attribute, title in LISTS.items():
        lines.append(f"## {title}")
        lines.append("")
        entries = getattr(spec, attribute)
        if entries:
            lines.extend(f"- {entry}" for entry in entries)
        else:
            lines.append("- (none yet)")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(spec.notes or "(none)")
    lines.append("")
    return "\n".join(lines)


def default_spec(collection_id: str) -> SourcesSpec:
    return SourcesSpec(
        collection_id=collection_id,
        jurisdiction="mx" if collection_id.startswith("mx") else "",
        language="es" if collection_id.startswith("mx") else "en",
        source_priority="primary",
    )


def load(collection_id: str, cfg: Settings | None = None) -> SourcesSpec:
    """Read the collection's ``sources.md``, or the defaults if it does not exist yet."""

    path = path_for(collection_id, cfg)
    if not path.exists():
        return default_spec(collection_id)
    return parse(path.read_text(encoding="utf-8"), collection_id=collection_id)


def save(collection_id: str, spec: SourcesSpec, cfg: Settings | None = None) -> Path:
    path = path_for(collection_id, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    spec.collection_id = spec.collection_id or collection_id
    path.write_text(render(spec), encoding="utf-8")
    return path


def save_text(collection_id: str, text: str, cfg: Settings | None = None) -> SourcesSpec:
    """Write raw markdown the user supplied, then return what the parser makes of it."""

    path = path_for(collection_id, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return parse(text, collection_id=collection_id)


def update(
    collection_id: str, changes: dict[str, Any], cfg: Settings | None = None
) -> SourcesSpec:
    spec = load(collection_id, cfg)
    for key, value in (changes or {}).items():
        key = _normalise_key(str(key))
        if key in SCALARS:
            setattr(spec, key, str(value))
        elif key in LISTS:
            items = value if isinstance(value, list) else [value]
            setattr(spec, key, [str(item) for item in items])
        elif key == "notes":
            spec.notes = str(value)
        else:
            spec.extra[key] = str(value)
    save(collection_id, spec, cfg)
    return spec
