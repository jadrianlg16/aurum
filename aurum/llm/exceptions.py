"""Exceptions for aurum.llm."""

from __future__ import annotations


class CloudNotAllowed(RuntimeError):
    """Raised when a call would be routed to a cloud provider without explicit opt-in.

    Aurum's privacy rule: prompts built from the user's data (ledger digests, payee
    lists, research questions, raw bank statements or invoices) stay on a local model
    unless the operator has explicitly opted in to sending data to a cloud provider by
    setting ``AURUM_CLOUD_OPT_IN=1`` (see :func:`aurum.core.config.settings`).
    """


class ProviderResponseError(ValueError):
    """A provider answered, but not with usable text.

    A ``ValueError`` on purpose: callers that already fall back on a bad provider response
    (the research endpoint's extractive answer, for one) handle these the same way.
    """


class ProviderRefused(ProviderResponseError):
    """The model declined to answer (Claude ``stop_reason == "refusal"``)."""


class ProviderTruncated(ProviderResponseError):
    """The answer hit the output-token limit (Claude ``stop_reason == "max_tokens"``)."""
