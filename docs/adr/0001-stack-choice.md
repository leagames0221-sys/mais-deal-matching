# ADR-0001: Stack choice — Python 3.11+ + FastAPI + Pydantic v2 + sentence-transformers + Microsoft Presidio

## Status

Accepted (2026-05-22)

## Context

`mais-deal-matching` is the sourcing-stage member of the MAIS suite — a two-sided matching engine that surfaces top-K candidate ↔ company pairings for Japanese mid-market M&A intermediaries. Five constraints frame the stack:

1. **Japanese + English bilingual retrieval** — embeddings, BM25 tokenization, and PII redaction must all handle JP text natively.
2. **PII-discipline boundary** — the matching path must read only pseudonymized fields; raw PII lives in a vault (see [ADR-0003](0003-vault-pattern-fernet-with-sqlcipher-kms-swap.md)). The stack must support clean module-boundary enforcement.
3. **Type-safe schema chain** — outputs (`Profile`, `CompanyMatch`, `CitationArray`) flow downstream to `mais-dd-workbench` per the [portfolio schema chain](https://github.com/leagames0221-sys/mais-portfolio/blob/main/docs/adr/0002-pydantic-schema-chain-handoff-contract.md).
4. **Free + no-credit-card default** — see [Selected under](../../README.md#selected-under).
5. **Consumer-laptop runtime** — 1,000 profiles + 200 companies + faiss-cpu index must fit in 16 GB RAM.

## Decision

| Layer | Selection | Free + no-CC verified |
| --- | --- | --- |
| Language | Python 3.11+ | ✅ |
| Web framework | FastAPI (MIT) | ✅ |
| ASGI server | uvicorn (BSD-3) | ✅ |
| Templating | Jinja2 (BSD-3) | ✅ |
| Schema | Pydantic v2 (MIT) | ✅ |
| Sparse retrieval | rank-bm25 (Apache-2.0) — see [ADR-0004](0004-five-stage-hybrid-retrieval-jp-tuning.md) | ✅ |
| Dense embedding | `intfloat/multilingual-e5-large` via sentence-transformers (MIT) — see [ADR-0004](0004-five-stage-hybrid-retrieval-jp-tuning.md) | ✅ |
| Cross-encoder | `cross-encoder/ms-marco-MiniLM-L-12-v2` (Apache-2.0) | ✅ |
| ANN | faiss-cpu (MIT) | ✅ |
| LLM provider | `LLMProvider` Protocol (3-tier swap) — see [ADR-0002](0002-llm-provider-protocol-3tier-swap.md) | ✅ |
| Vault crypto | cryptography Fernet (Apache-2.0) PoC; SQLCipher swap target — see [ADR-0003](0003-vault-pattern-fernet-with-sqlcipher-kms-swap.md) | ✅ |
| PII redaction | Microsoft Presidio (MIT) | ✅ |
| Tests | pytest (50 collected, 49 passing) | ✅ |

## Rationale

The ecosystem fit argument is the same as in the sibling repos. Deal-matching-specific drivers:

- **sentence-transformers + `multilingual-e5-large`** is the strongest OSS bilingual encoder for the JP / EN domain at this scope; no language other than Python ships it as a first-class library.
- **Microsoft Presidio** provides Japanese NER for PII redaction with active maintenance and a permissive license; no comparable mature library outside Python.
- **Pydantic v2 immutable boundary contracts** are what carry `Profile` / `CompanyMatch` / `CitationArray` downstream to `mais-dd-workbench` without copying or re-deriving — see [`mais-portfolio` ADR-0002](https://github.com/leagames0221-sys/mais-portfolio/blob/main/docs/adr/0002-pydantic-schema-chain-handoff-contract.md).

## Alternatives considered

### Node.js / TypeScript (rejected)

- **Pros**: shared stack with security-tool sibling repos.
- **Cons**: no first-class binding for sentence-transformers (multilingual-e5-large), Presidio, or faiss. Each would need FFI or subprocess wrap.
- **Why rejected**: rebinding cost exceeds value of stack uniformity.

### Go (rejected)

- **Pros**: single-binary deploy.
- **Cons**: nearly the entire bilingual retrieval + PII redaction stack would need reimplementation.
- **Why rejected**: same ecosystem-fit argument, more severe.

### Python without FastAPI (rejected)

- **Pros**: Flask is simpler.
- **Cons**: FastAPI's Pydantic-native request/response model removes a serialization layer; the matching surface is JSON in / JSON out.
- **Why rejected**: FastAPI strictly dominates given the Pydantic v2 boundary contract.

## Consequences

### Positive

- All retrieval + PII primitives used as-published; no FFI / subprocess overhead.
- Pydantic v2 schemas flow from HTTP request through the matching pipeline to the downstream schema chain.
- Module-boundary discipline (matching never imports `src/vault/*`) is enforceable in Python via static check.

### Negative

- Not single-binary distribution; customer deploy uses containers.
- Cold start loads e5-large (~2.2 GB on first index build); amortized by long-running uvicorn.

### Reversibility

The Pydantic schemas are language-agnostic in shape; a language pivot would require rebinding sentence-transformers + Presidio + faiss, which is the original cost argument.

## References

- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/)
- [sentence-transformers](https://www.sbert.net/)
- [Microsoft Presidio](https://microsoft.github.io/presidio/)
- [`mais-portfolio` ADR-0002 — schema chain contract](https://github.com/leagames0221-sys/mais-portfolio/blob/main/docs/adr/0002-pydantic-schema-chain-handoff-contract.md)
- [README — Tech stack](../../README.md#tech-stack)
