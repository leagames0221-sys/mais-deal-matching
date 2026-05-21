# ADR-0004: Five-stage hybrid retrieval — BM25 + dense e5 + RRF + cross-encoder + LLM listwise CoT, tuned for Japanese sparse + dense complementarity

## Status

Accepted (2026-05-22)

## Context

The matching engine surfaces top-5 candidate ↔ company pairings on a corpus of 1,000 profiles + 200 companies at PoC scale (customer scale: 10² – 10⁵). Four constraints frame the retrieval composition:

1. **Japanese-language sparse + dense complementarity** — Japanese business writing rewards BM25 on short kanji-heavy company-name strings (`株式会社…製作所`) and rewards dense embeddings on long context paragraphs. Either side alone misses signals the other catches; the fusion step is load-bearing.
2. **Stages 1–4 must run without any LLM** — the [Selected under](../../README.md#selected-under) "zero credit card" + "local LLM (default)" constraints require that the core matching surface produces a top-K without any external API call.
3. **Stage 5 is incremental, not load-bearing** — adds calibrated `fit_label` + chain-of-thought reasoning on the top-K from stages 1–4, but its absence does not break the matching surface.
4. **Citation link-back is required** — every surfaced match must point back to a specific candidate / company record ID for the audit trail.

## Decision

A five-stage retrieval pipeline ([src/matching/](../../src/matching/)):

| Stage | Component | License | Role |
| --- | --- | --- | --- |
| 1 — sparse recall | `rank-bm25` | Apache-2.0 | Tokenized BM25; recovers exact-term anchors (company codenames, industry codes, kanji-heavy names). |
| 2 — dense recall | `intfloat/multilingual-e5-large` via sentence-transformers, served from `faiss-cpu` | MIT (model) + MIT (faiss) | Bilingual semantic recall; handles JP ↔ EN paraphrase and synonym variation. |
| 3 — RRF fusion | Reciprocal Rank Fusion (in-tree implementation, ~20 LOC) | self-built | Combines stage 1 + 2 rankings into a unified candidate set without weight tuning. |
| 4 — cross-encoder rerank | `cross-encoder/ms-marco-MiniLM-L-12-v2` | Apache-2.0 | Pairwise (query, candidate) scoring; reorders the RRF output by domain-textual relevance. |
| 5 — LLM listwise CoT rerank | [`LLMProvider` Protocol](0002-llm-provider-protocol-3tier-swap.md) | MIT | Listwise chain-of-thought rerank for the top-K of stage 4; produces calibrated `(fit_label, reasoning)` tuples. |

## Why this composition

### Stage 1 + Stage 2 together (not either alone)

BM25 alone misses paraphrase ("製造業" ↔ "ものづくり産業") and JP ↔ EN cross-language matching (Japanese candidate text against an English company description). Dense alone misses exact-term anchors (company codenames, ISIN-like identifiers, narrow industry codes). The complementarity is stronger in Japanese than English; the fusion step is correspondingly more load-bearing.

### Stage 3 RRF (not weighted fusion)

[Cormack et al., 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) showed RRF outperforms weighted-sum fusion across IR benchmarks without requiring per-domain weight tuning. RRF's parameter (`k`, typically 60) is corpus-insensitive; this is the right property for a portfolio piece that ships against a synthetic fixture but must generalize to customer corpora.

### Stage 4 cross-encoder before Stage 5 LLM

Cross-encoder rerank is ~100× cheaper per (query, candidate) pair than an LLM call; reserving the LLM for listwise over the cross-encoder top-K is the cost / quality balance.

### Stage 5 last, optional

LLM listwise CoT adds `fit_label` + reasoning, but the surface (top-5 candidates) is already produced by stages 1–4. This is what makes the [Selected under](../../README.md#selected-under) local-LLM-default constraint hold without losing the core feature when MockProvider is active.

## Alternatives considered

### Dense only (multilingual-e5 + faiss, no BM25, no rerank) (rejected)

- **Pros**: simplest pipeline.
- **Cons**: misses exact-term anchors common in Japanese business names; dense-only top-K on the synthetic corpus included off-domain candidates that BM25 anchored correctly.
- **Why rejected**: stage 1 BM25 anchor is load-bearing for Japanese.

### BM25 only (rejected)

- **Pros**: deterministic, no model load.
- **Cons**: misses paraphrase + JP ↔ EN cross-language matching.
- **Why rejected**: stage 2 dense recall is load-bearing for the bilingual case.

### Weighted-sum fusion instead of RRF (rejected)

- **Pros**: per-corpus tuning may eke out a few points.
- **Cons**: requires per-deployment weight tuning; brittle when the corpus shifts; defeats the "ship-and-go" property of RRF.
- **Why rejected**: corpus shift is the norm at customer deployment, not the exception.

### Direct LLM scoring (no statistical retrieval) (rejected)

- **Pros**: simplest from a code-structure perspective.
- **Cons**: cost scales linearly with corpus size per query; blows the context window beyond ~100 candidates; no offline / zero-CC path.
- **Why rejected**: violates the zero-CC default.

### Cohere Rerank / paid managed reranker API (rejected)

- **Pros**: high reranking quality with no local model overhead.
- **Cons**: paid managed service violates [Selected under](../../README.md#selected-under).
- **Why rejected**: incompatible with the default path.

### Two-tower contrastive trained from scratch (rejected for PoC)

- **Pros**: matches the "embedding-based recommender" pattern from the [IRS2021 reference](https://irsworkshop.github.io/2021/publications/IRS2021_paper_6.pdf).
- **Cons**: requires labelled "(candidate, company) is-a-match" pairs, which the PoC does not have.
- **Why rejected**: scope. Documented as a customer-deployment evolution path when historical match data arrives.

## Consequences

### Positive

- Stages 1–4 produce a complete top-K with zero LLM call, zero API key, zero credit card — the matching surface ships even in the offline default path.
- RRF makes the fusion step corpus-insensitive; the pipeline ports from the synthetic PoC corpus to a customer corpus without weight retuning.
- Stage 5 is incremental — adding the LLM listwise CoT enriches the surface without altering stages 1–4. PoC reviewers can evaluate the deterministic core separately from the LLM-augmented surface.
- Citation link-back is preserved through every stage; the top-5 result carries source candidate / company record IDs.

### Negative

- Cold start loads two model sets (e5-large + MS-MARCO cross-encoder); amortized by long-running uvicorn process.
- RRF's `k` parameter (60) is hardcoded; corpus shifts of 10× or more may warrant retuning. Mitigated by RRF's known corpus-insensitivity.
- Stage 5 LLM quality is bounded by the chosen `LLMProvider` tier; MockProvider returns templated `(fit_label, reasoning)` tuples respecting the cross-encoder order only.

### Reversibility

Each stage is behind an interface in [src/matching/](../../src/matching/). Component swaps inside a stage are local edits. Adding a sixth stage (e.g., a learned two-tower scoring head once labelled pairs arrive) is additive.

## References

- [Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond"](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)
- [Wang et al., "Multilingual E5 Text Embeddings: A Technical Report"](https://arxiv.org/abs/2402.05672)
- [Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods" (SIGIR 2009)](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
- [MS MARCO Cross-Encoders documentation](https://www.sbert.net/docs/cross_encoder/pretrained_models.html)
- [MDPI 2024 — Zero-Shot Resume-Job Matching with LLMs](https://www.mdpi.com/2079-9292/14/24/4960) — Stage 5 CoT prompt structure reference
- [IRS2021 — Embedding-based Recommender](https://irsworkshop.github.io/2021/publications/IRS2021_paper_6.pdf) — two-sided embedding pattern reference
- [`rank-bm25` project](https://github.com/dorianbrown/rank_bm25)
- [`faiss` project](https://github.com/facebookresearch/faiss)
- Code: [src/matching/](../../src/matching/), [README — Architecture](../../README.md#architecture)
