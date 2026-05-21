# ADR-0002: LLMProvider Protocol — 3-tier swap (Mock / Ollama-local / paid API)

## Status

Accepted (2026-05-22)

## Context

Stage 5 of the [5-stage hybrid retrieval pipeline](0004-five-stage-hybrid-retrieval-jp-tuning.md) is an LLM listwise chain-of-thought rerank. The portfolio's [Selected under](../../README.md#selected-under) constraint set requires:

1. The PoC runs end-to-end with no API key and no internet (zero CC default).
2. A customer can plug in a paid Claude / Gemini key in exactly one place, no refactor.
3. An intermediate operator can run Ollama locally for self-hosted PoC realism.

The swap point shape is the load-bearing architectural decision; if it leaks across callers (e.g., `import anthropic` inside `src/matching/`), the swap claim becomes prose, not code.

## Decision

A single `LLMProvider` Python `Protocol` ([src/matching/llm_provider.py](../../src/matching/llm_provider.py)) carries three concrete implementations behind a single `default_provider()` factory. Callers (`src/matching/`) import only the Protocol — never a concrete SDK.

| Tier | Provider | Env trigger | Cost / surface |
| --- | --- | --- | --- |
| **1 — PoC default** | `MockProvider` (deterministic templated `(fit_label, reasoning)` tuples) | None (default) | Zero cost, zero credit card, runs offline |
| **2 — Local LLM swap** | `OllamaProvider` (e.g. `qwen2.5:7b`) | `LLM_PROVIDER=ollama` + `OLLAMA_BASE_URL` + `OLLAMA_MODEL` | Still zero cost, still no credit card, uses customer's GPU/CPU |
| **3 — Customer / production swap** | `ClaudeProvider` / `GeminiProvider` | `LLM_PROVIDER=claude` + `ANTHROPIC_API_KEY` + `ANTHROPIC_MODEL` | Only tier that touches credit-card-backed services |

The factory contract: `default_provider()` reads `LLM_PROVIDER` (default `mock`) and returns the matching implementation. SDK imports (`import anthropic`, `import ollama`) live inside the concrete provider class — they never leak into `src/matching/`.

The Protocol exposes a single method `listwise_rerank(query, candidates) -> list[RerankedCandidate]` (other methods may exist for token counting / health checks but only `listwise_rerank` is load-bearing).

## Why a Protocol and not an abstract base class

Python 3.8+ `typing.Protocol` is structural — any class with `listwise_rerank(...)` satisfies it without inheritance. Test fixtures use one-off `class _Stub:` declarations rather than ABC subclasses.

## Why Stage 5 alone (and not "all LLM calls go through the Protocol")

The repo only uses an LLM in Stage 5 of retrieval. The earlier stages (BM25, dense e5, RRF, cross-encoder) are deterministic, key-free, and offline-runnable. Scoping the Protocol to the single LLM consumer keeps the surface small (~30 lines total).

## Alternatives considered

### Single hardcoded provider (Anthropic SDK only) (rejected)

- **Pros**: simplest; production-quality output from day one.
- **Cons**: forces PoC reviewers to procure an Anthropic key + register a credit card; violates [Selected under](../../README.md#selected-under) zero-CC default; makes the demo video impossible without a sponsored key.
- **Why rejected**: defeats the portfolio's defining constraint.

### LangChain `BaseChatModel` (rejected)

- **Pros**: industry-standard abstraction; LangGraph integrates natively.
- **Cons**: LangChain 1.0 → 2.0 broke chat-model interfaces; pulls a heavy transitive dependency tree (≥30 packages) for the single `listwise_rerank` call.
- **Why rejected**: surface area exceeds the need.

### `litellm` (rejected)

- **Pros**: unifies 100+ providers behind one API.
- **Cons**: scope mismatch — 100+ providers for a 3-tier need.
- **Why rejected**: over-engineered for a closed set.

### Pluggy / `entry_points` discovery (rejected)

- **Pros**: external providers register without code changes in this repo.
- **Cons**: extension surface unneeded for a closed 3-tier set.
- **Why rejected**: over-engineered.

## Consequences

### Positive

- PoC reviewer flow: `git clone` → `pip install` → `uvicorn ...` works with zero env vars and zero key, exercising the full 5-stage pipeline with templated Stage 5 output.
- Customer flow: paste `ANTHROPIC_API_KEY=...` + set `LLM_PROVIDER=claude`, zero refactor.
- Stages 1–4 produce a complete top-K even if Stage 5 is offline; the LLM tier is incremental, not load-bearing for the core matching surface.

### Negative

- MockProvider's `(fit_label, reasoning)` outputs are deterministic templated — PoC reviewer does not see actual LLM quality without enabling tier 2 / 3. Disclosed in [PoC status](../../README.md#poc-status-what-is-live-vs-deferred).
- Provider feature parity is partial (token counting semantics vary); acceptable since matching does not bill on tokens.

### Reversibility

Adding a fourth tier (e.g., self-hosted vLLM gateway) is one new class + one line in `default_provider()`.

## References

- [PEP 544 — Protocols: Structural subtyping](https://peps.python.org/pep-0544/)
- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [Ollama Python client](https://github.com/ollama/ollama-python)
- [LangChain `BaseChatModel`](https://python.langchain.com/docs/concepts/chat_models/) — heavyweight alternative
- Code: [src/matching/llm_provider.py](../../src/matching/llm_provider.py), [README — Configuration (env)](../../README.md#configuration-env)
