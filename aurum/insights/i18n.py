"""Thin re-export of :mod:`aurum.core.i18n`.

The ``insights.*`` keys live in ``aurum.core.i18n`` (single source of truth, ``t(key, lang, **kwargs)``);
this module re-exports ``t`` so ``aurum.insights.digest``/``engine``/``telegram`` can import
``from .i18n import t``.
"""

from __future__ import annotations

from ..core.i18n import t

__all__ = ["t"]
