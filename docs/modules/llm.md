# aurum.llm

Pluggable LLM provider layer, shared with
the author's learning-tutor project (https://github.com/jadrianlg16/learning-tutor).

## Purpose

Gives the rest of Aurum two calls -- `generate_text` and `generate_structured` --
that work identically regardless of which model backend is configured, plus a
privacy gate that keeps the user's financial data off cloud APIs unless the
operator explicitly opts in (`AURUM_CLOUD_OPT_IN=1`).

Models only classify, rephrase and explain; they never compute a figure (math lives
in code, see [ARCHITECTURE.md](../ARCHITECTURE.md#principles)).

## Layout

- `ai_providers.py` -- `AIProviderInterface` + `AIProviderFactory`, one
  implementation per provider: OpenAI, Claude (Anthropic), Ollama, LM Studio,
  Custom (any OpenAI-compatible HTTP endpoint).
- `config.py` -- `ProviderConfig` and `get_provider_config()`. Provider and model
  are read from `aurum.core.config.settings()` (`AURUM_LLM_PROVIDER` /
  `AURUM_LLM_MODEL`, default `ollama` / `llama3.1:8b`) so there is one source of
  truth for those two values across Aurum. Timeout, temperature, max_tokens, and
  cache TTL are read directly from `AURUM_LLM_*` env vars here, since they have no
  home in `aurum.core.config`.
- `structured.py` -- `generate_text` / `generate_structured`: robust JSON
  extraction (fenced code block, then raw, then a balanced-brace/bracket
  fallback, with trailing-comma repair), Pydantic validation with retries, and an
  on-disk cache under `<AURUM_DATA_DIR>/cache/llm/`.
- `router.py` -- a FastAPI `APIRouter` exposing `/llm/health`, `/llm/generate`,
  `/llm/structured` for callers that want the module over HTTP rather than as a
  Python import.
- `exceptions.py` -- `CloudNotAllowed`, raised by the privacy gate, and
  `ProviderResponseError` (subclasses `ProviderRefused`, `ProviderTruncated`) for a provider that
  answered without usable text. These subclass `ValueError`, so callers that already fall back on a
  bad response (the research endpoint) treat them the same way.

## Env vars

| Var | Default | Notes |
|---|---|---|
| `AURUM_LLM_PROVIDER` | `ollama` | read via `aurum.core.config.settings()` |
| `AURUM_LLM_MODEL` | `llama3.1:8b` | read via `aurum.core.config.settings()` |
| `OLLAMA_URL` | `http://localhost:11434` | read via `aurum.core.config.settings()` |
| `ANTHROPIC_API_KEY` | (empty) | read via `aurum.core.config.settings()` |
| `OPENAI_API_KEY` | (empty) | read directly from the environment |
| `AURUM_LLM_TIMEOUT_S` | `60` | seconds per provider HTTP call |
| `AURUM_LLM_TEMPERATURE` | `0.2` | generation temperature |
| `AURUM_LLM_MAX_TOKENS` | `2048` | generation max tokens |
| `AURUM_LLM_CACHE_TTL_S` | `300` | on-disk structured-generation cache TTL; `0` disables |
| `AURUM_CLOUD_OPT_IN` | `false` | read via `aurum.core.config.settings()`; see privacy gate below |

The default model is `llama3.1:8b`, matching `aurum.core.config.settings().llm_model`. With
`AURUM_LLM_PROVIDER=claude` and `AURUM_LLM_MODEL` unset or still at that local default, the model
becomes `claude-opus-5-5`.

## Claude provider

`ClaudeProvider` calls the Messages API (`POST {base_url}/messages`) with plain `httpx`:

- **No sampling parameters.** `temperature` is accepted by the shared interface but never sent;
  current Claude models reject non-default sampling parameters.
- **16,000 output tokens at least.** Current models think adaptively and the thinking tokens count
  toward `max_tokens`, so the request uses `max(AURUM_LLM_MAX_TOKENS, 16000)`.
- **Stop reasons are checked.** `stop_reason: "refusal"` raises `ProviderRefused` (the research
  endpoint then answers with the extractive fallback); `stop_reason: "max_tokens"` raises
  `ProviderTruncated`; otherwise the first content block whose `type` is `"text"` is returned,
  since thinking blocks can come first.

This path is covered by unit tests with a mocked HTTP response only; no live API call is made in
the test suite.

## Role label

Both public functions accept `role: str = "research"`. In Aurum `role` is purely an
audit-only label carried through to logs/telemetry. It has no effect on provider
selection and enforces nothing.

## Privacy gate

**Every call that resolves to a cloud provider is refused unless `AURUM_CLOUD_OPT_IN=1`.**
`_check_privacy_gate` runs before any HTTP call in both `generate_text` and
`generate_structured`:

- Ollama, LM Studio, and a `custom` provider whose `base_url` host is
  `localhost`/`127.0.0.1` are always allowed (data stays on the machine).
- Anthropic (`claude`) and OpenAI (`openai`) are always treated as cloud and are
  refused with `aurum.llm.exceptions.CloudNotAllowed`, **unless**
  `aurum.core.config.settings().cloud_opt_in` is true (`AURUM_CLOUD_OPT_IN=1`).
- A `custom` provider pointed at a non-localhost host is treated as cloud for
  this check.

`contains_raw_documents: bool = False` is still accepted by both functions but is **audit-only**:
it does not change the decision (a ledger digest, a payee list or a research question is the
user's financial data whether or not it embeds a raw document). With the opt-in set, a call that
carries raw documents logs one INFO line naming the provider. `insights/digest.py`,
`research/router.py` and `updater/triage.py` catch `CloudNotAllowed` and degrade (rule-based
digest / extractive answer from the citations / keyword summary) instead of failing the request.

## Limitations

- A local `llama3.1:8b` sometimes refuses to write tax prose. For research questions the extractive
  fallback (the cited excerpts) is then the useful answer; see
  [research.md](research.md#known-limitation-local-model-refusals) for how the endpoint behaves.

## Testing

`tests/llm/test_llm.py` covers JSON extraction (fenced / raw / balanced-brace /
trailing-comma), provider dispatch (via `AIProviderFactory`, with `httpx.AsyncClient`
monkeypatched so no real network call is made), the privacy gate (local provider
passes; cloud provider without opt-in raises `CloudNotAllowed` before any HTTP call, with **and
without** `contains_raw_documents`; cloud provider with `AURUM_CLOUD_OPT_IN=1` passes), the Claude
response handling (no `temperature` in the payload, text after a thinking block, refusal,
`max_tokens`), and the env-var defaults above.
