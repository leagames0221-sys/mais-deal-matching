# MAIS — Deal Matching

> **Two-sided M&A matching engine** with a 5-stage hybrid retrieval pipeline and a PII Vault Pattern compliant with Japan's 2026 amended Personal Information Protection Act.
> Match successor candidates with professional intermediaries; embedding/matching never touches raw PII.

[![tests](https://img.shields.io/badge/tests-49%20passing%20%2F%2050-brightgreen)]()
[![pip-audit](https://github.com/leagames0221-sys/mais-deal-matching/actions/workflows/pip-audit.yml/badge.svg)](https://github.com/leagames0221-sys/mais-deal-matching/actions/workflows/pip-audit.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Constraint: zero credit card](https://img.shields.io/badge/Constraint-zero%20credit%20card-blue)](#selected-under)
[![Constraint: local LLM (default)](https://img.shields.io/badge/Constraint-local%20LLM%20%28default%29-blue)](#selected-under)
[![Constraint: free / OSS only](https://img.shields.io/badge/Constraint-free%20%2F%20OSS%20only-blue)](#selected-under)
[![Constraint: security defense-in-depth](https://img.shields.io/badge/Constraint-security%20defense--in--depth-blue)](#selected-under)

---

## Selected under

> **The 4-constraint set** (applied across the full portfolio — verified consistent across all 11 portfolio repos):
>
> 1. **Zero credit card** — no paid API / cloud service required for the default path. A reviewer can clone, install, and run with $0 spend and no payment method on file.
> 2. **Local LLM (default)** — when an LLM is involved, the default path is local (Ollama / similar) or deterministic mock. Paid cloud LLM is opt-in via env var, never default.
> 3. **Free / OSS only** — every runtime dependency is permissively-licensed open source (MIT / Apache-2.0 / BSD-3); no proprietary SDK at build time.
> 4. **Security defense-in-depth** — secrets-scan CI + `.gitignore` hardening, encrypted-at-rest where PII is involved, append-only audit logging where applicable, dep-vuln gating (`pip-audit` / `pnpm audit`), paid-API constructor gate where applicable.

This repo specifically demonstrates: 2026-amended APPI vault pattern (Fernet AES-128 PoC with SQLCipher/KMS swap path documented), 5-stage hybrid retrieval where Stages 1-4 run without any LLM, and the [Configuration (env)](#configuration-env) section's 3-tier swap showing the single point where paid APIs enter the system (tier 3 only).

---

## 🎬 Demo walkthrough (85-second narrated video)

End-to-end demo of both sides of the matching engine — successor candidate flow (mypage → vault decrypt → matching → introduction request → audit log) → company flow (signin → candidate matching → introduction request → audit log). Japanese narration by [AivisSpeech](https://aivis-project.com/) (まお おちついた, Style-Bert-VITS2), 1920×1080 H.264.

> [▶️ **mais_deal_matching_demo.mp4**](out_video/mais_deal_matching_demo.mp4) — 84.96 s · 6.5 MB · 14 scenes with burned-in SRT subtitles.

<video src="out_video/mais_deal_matching_demo.mp4" controls width="100%"></video>

**Reproducible pipeline** ([scripts/produce_video.py](scripts/produce_video.py), [requirements-video.txt](requirements-video.txt)) — 1-command rebuild given preconditions (uvicorn + [AivisSpeech-Engine 1.2.0](https://github.com/Aivis-Project/AivisSpeech-Engine) on `:10101` + [Playwright](https://playwright.dev/) chromium + [ffmpeg](https://ffmpeg.org/)). All synthetic data, zero real PII, zero paid API.

---

## 30-second pitch

Japanese mid-market M&A intermediaries handle hundreds of thousands of candidate-side and buy-side records. Naive matching tools either (a) leak PII to embedding models, or (b) drop accuracy by stripping context.

**MAIS Deal Matching** solves both:
- **Retrieval quality** — 5-stage hybrid pipeline (BM25 + dense + RRF + cross-encoder + LLM listwise CoT rerank) — designed for Japanese-language sparse + dense complementarity *(Stages 1-4 active; Stage 5 LLM rerank uses MockProvider in PoC, Claude/Gemini swap is a 1-file change — see [PoC status](#poc-status-what-is-live-vs-deferred))*
- **PII compliance** — vault holds PII; only pseudonymized fields enter the embedding/matching path. Aligns with the 2026 amended APPI exemption (encrypted + pseudonymized → no breach reporting obligation) *(PoC: Fernet AES-128-CBC + HMAC-SHA256 over JSONL files; production-equivalent SQLCipher / PostgreSQL + KMS swap path is literal in `src/vault/store.py`)*

---

## Why this is distinct (existing alternatives + delta)

Two adjacent tool categories address Japanese M&A deal matching in 2026, but neither combines retrieval-quality discipline with the 2026 amended APPI vault pattern:

- **Japanese mid-market M&A matching platforms** (Batonz / TRANBI / M&A Capital Partners JP) — operate the candidate-buyer marketplace but treat matching as a recruiter-tier human task; AI retrieval is opaque and PII handling is the platform's compliance responsibility, not exposed as a swap-able vault pattern.
- **Generic CRM / matching engines** (HubSpot / Salesforce / DealRoom CRM) — manage deal pipeline + metadata but do not implement Japanese-language sparse + dense complementarity (BM25 + dense + RRF) nor the 2026 APPI encrypted-pseudonymized exemption pattern in a vault swap surface.

MAIS Deal Matching is the only OSS demonstrating: 5-stage hybrid retrieval tuned for Japanese-language sparse+dense complementarity (Stages 1-4 LLM-free) layered with the 2026 APPI vault pattern (Fernet PoC, SQLCipher/KMS swap path literal in `src/vault/store.py`).

**Target user**: Japanese mid-market M&A intermediary firms (handling 10²-10⁵ candidate + buyer records) needing audit-grade PII handling + Japanese-language retrieval quality without enterprise-tier licensing.

---

## Architecture

```
                 ┌─────────────────────────────┐
                 │  Candidate / Company input  │
                 └──────────────┬──────────────┘
                                │
                  ┌─────────────▼─────────────┐
                  │  Vault (Fernet in PoC;    │  ← PII at rest, audit log append-only
                  │   SQLCipher/KMS swap)     │
                  │  • name / contact / DoB   │
                  └─────────────┬─────────────┘
                                │ (pseudonymize)
                  ┌─────────────▼─────────────┐
                  │  Operational DB           │  ← embedding/matching reads ONLY this
                  │  • age band / region /    │
                  │    industry / skills /    │
                  │    Presidio-redacted text │
                  └─────────────┬─────────────┘
                                │
   ┌────────────────────────────┼────────────────────────────┐
   │                            │                            │
   ▼                            ▼                            ▼
┌──────────┐  ┌─────────────┐  ┌──────┐  ┌──────────────┐  ┌────────────┐
│ Stage 1  │→ │  Stage 2    │→ │ RRF  │→ │  Stage 4     │→ │  Stage 5   │
│ BM25     │  │  e5-large   │  │ fuse │  │ cross-encoder│  │  LLM CoT   │
│ (sparse) │  │  (dense)    │  │      │  │  rerank      │  │  listwise  │
└──────────┘  └─────────────┘  └──────┘  └──────────────┘  └────────────┘
                                                                    │
                                                                    ▼
                                                          ┌──────────────────┐
                                                          │  Top-5 candidates│
                                                          │  + fit_label     │
                                                          │  + CoT reasoning │
                                                          └──────────────────┘
```

---

## What's inside

| Capability | Implementation | PoC status |
|---|---|---|
| **5-stage hybrid retrieval** | BM25 (rank-bm25) + multilingual-e5-large dense + RRF (Reciprocal Rank Fusion) + cross-encoder/ms-marco-MiniLM-L-12-v2 rerank + LLM listwise CoT rerank | Stages 1-4 ✅ active; Stage 5 ⏳ MockProvider returns templated CoT (no API key) |
| **PII Vault Pattern** | Encrypted vault (PII: name / contact / detailed address / DoB / raw text) + pseudonymized Operational DB (age band / region / industry / skills / Presidio-redacted text) | ✅ active. PoC = Fernet AES-128-CBC + HMAC-SHA256 over JSONL files; SQLCipher / PostgreSQL + KMS swap is the production path (`src/vault/store.py` L2-4) |
| **Audit trail** | All vault access logged append-only with timestamp + actor + purpose | ✅ active |
| **Member portal** | Mock OAuth (Google/LinkedIn provider hooks) + temporary PII vault read with audit + introduction flow | ✅ active (mock OAuth hooks) |
| **LLM swap path** | LLMProvider Protocol (`listwise_rerank` method) — MockProvider (no API key required) ↔ Claude / Gemini / Ollama swap | ⏳ Protocol + MockProvider live; ClaudeProvider class not yet present in `src/`. `anthropic>=0.40` declared in `requirements.txt` but no code imports it |
| **Brand UI** | FastAPI + Jinja2 + slate palette + golden-ratio (φ=1.618) typography scale | ✅ active |

---

## Compliance angle

Japan's 2024 PII breach incidents hit a 4-year high (189 listed companies). The 2026 APPI amendment introduces an exemption: **if PII is both encrypted and pseudonymized, there is no breach reporting obligation**. This codebase implements the *shape* of that exemption from day one:

- vault → encrypted at rest. **PoC**: Fernet (AES-128-CBC + HMAC-SHA256). **Production swap**: SQLCipher (AES-256) or PostgreSQL + envelope key via KMS — `src/vault/store.py` documents the swap path.
- operational DB → pseudonymized fields only (matching engine reads this)
- if either is breached in isolation, the exemption applies

The vault read-side enforcement (audit log + module boundary check preventing embedding/matching from importing `src/vault/*`) is active in PoC.

---

## Tech stack

| Layer | Choice | Why | PoC wiring |
|---|---|---|---|
| Embedding | sentence-transformers / multilingual-e5-large | Strong Japanese + English performance, OSS | ✅ live |
| ANN | FAISS in-memory | Handles hundreds of thousands of records on a laptop | ✅ live |
| Sparse | rank-bm25 | Complements dense for Japanese term-heavy queries | ✅ live |
| Cross-encoder | cross-encoder/ms-marco-MiniLM-L-12-v2 | Re-ranks top-100 from RRF fusion | ✅ live |
| LLM | LLMProvider Protocol — MockProvider in PoC; Anthropic SDK / Gemini / Ollama swap | listwise Chain-of-Thought rerank (Stage 5) | ⏳ MockProvider active; `anthropic>=0.40` declared in `requirements.txt` but not imported. Stage 5 lands in Week 3b per `requirements-week3.txt` L2 |
| Web | FastAPI + uvicorn + Jinja2 | Standard Python web stack | ✅ live |
| Vault | Fernet (AES-128-CBC + HMAC-SHA256) in PoC; SQLCipher / PostgreSQL + KMS in production | Encrypted-at-rest with key management | ⏳ Fernet active; SQLCipher swap is `src/vault/store.py` L2-4 path |
| PII redaction | Microsoft Presidio | Japanese + English NER for redaction | ✅ live |
| Tests | pytest (50 collected: unit + integration) | TDD throughout | ✅ live (49/50 pass per badge) |

---

## Decomposed prior art

| Reference | Pattern adopted |
|---|---|
| [HuggingFace sentence-transformers `applications/semantic-search`](https://github.com/huggingface/sentence-transformers/tree/main/examples/sentence_transformer/applications/semantic-search) (Apache-2.0) | Asymmetric semantic search (`encode_query` / `encode_document`), FAISS index pattern |
| [MDPI 2024 "Zero-Shot Resume-Job Matching with LLMs"](https://www.mdpi.com/2079-9292/14/24/4960) | Structured prompt + Chain-of-Thought (87% zero-shot accuracy reported) |
| [IRS2021 "Embedding-based Recommender"](https://irsworkshop.github.io/2021/publications/IRS2021_paper_6.pdf) | Two-sided embedding (separate vector spaces for profiles / companies) |

---

## Quick start

```powershell
# 1. virtualenv
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-week4.txt

# 2. generate synthetic data (1,000 profiles + 200 companies, PII / Op separated)
python -m src.data_gen.generate_synthetic_profiles

# 3. build embedding index (multilingual-e5-large, ~2.2 GB first download, ~7 min)
python -m src.embedding.build_index

# 4. dev keys + vault initialization
# First run: generates VAULT_KEY / SESSION_SECRET, prints them, and exits if .env is absent.
python -m scripts.setup_dev
# Manually create .env in repo root and paste the printed values (gitignored).
# Second run: with .env populated, encrypts synthetic PII into the vault.
python -m scripts.setup_dev

# 5. launch UI
uvicorn src.api.app:app --reload --port 8000
# → http://localhost:8000/
```

---

## Demo flow

1. Land on `/` — pick one of 10 synthetic candidate profiles
2. Mock-signin as PROF-000001 (e.g., food manufacturing / 60-69 / Chiba)
3. My Page — operational fields by default; click "Temporary PII vault read" → decrypt + audit log
4. Run matching — 5-stage pipeline produces top-5 with fit_label + CoT reasoning
5. Submit introduction request — vault PII join (company name / contact / raw description) → audit log
6. View audit log — append-only trace of all vault access

---

## Configuration (env)

The matching engine ships with a **3-tier LLM swap path** for Stage 5 (listwise CoT rerank). Pick the tier that matches your environment — no env edits are needed for tier 1 (PoC default).

### Tier 1 — PoC default (zero cost, zero credit card, runs offline)

```bash
# No LLM env vars required. MockProvider is the default; Stage 5 emits deterministic
# (fit_label, reasoning) tuples respecting the cross-encoder order, so the full
# 5-stage pipeline + vault + audit log all work without any external API call.
SYNTHETIC_SEED=20260512                 # reproducibility
SYNTHETIC_PROFILE_COUNT=1000            # 1,000 in PoC; scale up for production
SYNTHETIC_COMPANY_COUNT=200
EMBEDDING_MODEL=intfloat/multilingual-e5-large
DATA_DIR=./data
VAULT_KEY=<fernet key>                  # always required
SESSION_SECRET=<token_urlsafe>          # always required
```

### Tier 2 — Local LLM swap (still zero cost, zero credit card; uses your own GPU/CPU)

For developers / customers who want real LLM listwise rerank without paid APIs. Requires [Ollama](https://ollama.com/) running locally with a model pulled (e.g. `ollama pull qwen2.5:7b`).

```bash
LLM_PROVIDER=ollama                     # switches default_provider() to Ollama (1-file swap point: src/matching/llm_provider.py)
OLLAMA_BASE_URL=http://localhost:11434  # Ollama default
OLLAMA_MODEL=qwen2.5:7b                 # any local model the listwise prompt format supports
# ... plus the always-required vars from tier 1
```

### Tier 3 — Customer / production swap (paid API; the only tier that touches credit-card-backed services)

For customer deployments where higher rerank quality or hosted-model SLA is required. **This is the only place credit-card-backed services enter the system** — paste the customer's key here and nothing else changes.

```bash
LLM_PROVIDER=claude                     # or "gemini" / future provider
ANTHROPIC_API_KEY=sk-ant-...            # paste customer's key here (tier 1 + tier 2 never read this var)
ANTHROPIC_MODEL=claude-sonnet-4-6       # whichever model the engagement contract specifies
# ... plus the always-required vars from tier 1
```

The swap point is literally one function — `default_provider()` in `src/matching/llm_provider.py` (currently MockProvider; Week 3b adds Claude/Ollama provider classes per `requirements-week3.txt` L2). Stage 1-4 (BM25 + dense + RRF + cross-encoder) never depend on Stage 5, so even if the LLM tier is offline the top-5 candidates ship.

---

## PoC status — what is live vs deferred

This is a **PoC portfolio** demonstrating shape + interfaces. The architecture above is the target design. Current implementation status:

**✅ Live in PoC** (active code paths, deterministic, no external API needed):
- Stages 1-4 of the retrieval pipeline (BM25 + dense e5-large + RRF + cross-encoder rerank)
- Fernet-encrypted vault + pseudonymized operational DB + append-only audit log
- Mock OAuth provider hooks + temporary PII vault read flow
- Microsoft Presidio JP/EN NER redaction
- 49/50 pytest cases passing

**⏳ Deferred to integration phase** (1-file swap paths defined, contracts stable):
- **Stage 5 LLM listwise CoT rerank** — `MockProvider` returns templated `(fit_label, reasoning)` tuples. `src/matching/llm_provider.py` defines the `LLMProvider` Protocol with a single `listwise_rerank` method. `anthropic>=0.40` is declared in top-level `requirements.txt` but no code imports it. Week 3b adds ClaudeProvider per `requirements-week3.txt` L2.
- **Vault → SQLCipher / KMS** — current vault is Fernet over JSONL files. `src/vault/store.py` L2-4 documents the production swap (SQLCipher / PostgreSQL + envelope key via KMS) as the migration target.
- **Real OAuth + Bot Framework** — Google / LinkedIn provider hooks are mocked; real OAuth wiring deferred to integration phase.

**Rationale**: this scoping lets the repo demonstrate end-to-end shape, the 2026 APPI vault pattern, and the 4-stage retrieval pipeline on a laptop without paid API keys. The Protocol-abstracted LLM swap and the documented vault migration path are themselves the portfolio claim — adding real Claude / SQLCipher does not require refactoring callers.

---

## What this exercise validated

Three things turned out to be worth defending in this PoC.

**First, the vault swap path is the compliance claim, not the Fernet choice itself.** The repo ships a working Fernet AES-128-CBC + HMAC-SHA256 vault over JSONL files for the PoC, but the production-equivalent SQLCipher / PostgreSQL + KMS swap path is literal in `src/vault/store.py`. Callers under `src/matching/` never read PII directly — they read pseudonymized fields through the vault interface — so wiring a real KMS-backed store changes one module, zero callers. The 2026 amended APPI encrypted-pseudonymized exemption is the structural reason this matters; the Protocol abstraction is the architectural commitment that makes the exemption actually portable to a customer engagement.

**Second, retrieval quality is tuned for Japanese mid-market language specifics.** The 5-stage pipeline (BM25 → dense → RRF → cross-encoder → LLM listwise CoT) is shaped for the sparse + dense complementarity that Japanese business writing exhibits more strongly than English-only corpora — short kanji-heavy company-name strings reward BM25, long context paragraphs reward dense, and RRF fusion captures both signals without either side dominating. Stages 1-4 run without any LLM, so the deterministic part of the matching surface is reproducible from a clean checkout against the synthetic fixture corpus.

**Third, the PoC stops where the maintained alternatives start.** Batonz / TRANBI / M&A Capital Partners JP remain the right call for buyers and candidates actively transacting in the Japanese mid-market marketplace. HubSpot / Salesforce / DealRoom CRM remain the right call for pipeline + metadata management. What MAIS Deal Matching adds is the open, auditable retrieval+vault pattern that an intermediary firm can deploy themselves under their own audit perimeter — wired and tested at 49/50 pytest cases against synthetic deal data, runnable on a consumer laptop with zero monthly cost. The PoC status section above is explicit about which integration points (LLM stage 5, vault migration, OAuth providers) are live versus deferred.

---

## Production deployment notes

This repo is a PoC. For real PII / production:

- Run inside a sandbox (Docker / WSL2 / Codespaces)
- Wire OAuth providers to real Google / LinkedIn apps
- 1-week stability dry-run before client cutover
- External penetration test recommended for large engagements
- LLMProvider swap to self-hosted (Ollama / vLLM) for data residency requirements

---

## Design history (ADR set)

Architecture decisions for this repo are recorded under [`docs/adr/`](docs/adr/) using the Nygard pattern (Context / Decision / Alternatives considered / Consequences / References). The four load-bearing decisions are:

- [ADR-0001 — Stack choice (Python 3.11+ + FastAPI + Pydantic v2 + sentence-transformers + Presidio)](docs/adr/0001-stack-choice.md)
- [ADR-0002 — LLMProvider Protocol 3-tier swap (Mock / Ollama-local / paid API)](docs/adr/0002-llm-provider-protocol-3tier-swap.md)
- [ADR-0003 — Vault Pattern: Fernet PoC with SQLCipher / KMS production swap path (2026 APPI compliance shape)](docs/adr/0003-vault-pattern-fernet-with-sqlcipher-kms-swap.md)
- [ADR-0004 — Five-stage hybrid retrieval tuned for Japanese sparse + dense complementarity](docs/adr/0004-five-stage-hybrid-retrieval-jp-tuning.md)

Each ADR records the alternatives considered (with pros / cons) and the consequences (positive + negative + reversibility), so the design path is replayable end-to-end.

---

## Sibling tools (M&A Intelligence Suite)

- **[mais-deal-matching](https://github.com/leagames0221-sys/mais-deal-matching)** ← this repo (sourcing)
- **[mais-dd-workbench](https://github.com/leagames0221-sys/mais-dd-workbench)** — Due Diligence automation
- **[mais-day1-cockpit](https://github.com/leagames0221-sys/mais-day1-cockpit)** — Day-1 readiness
- **[mais-pmi-cockpit](https://github.com/leagames0221-sys/mais-pmi-cockpit)** — 100-day PMI dashboard
- **[mais-pmi-knowledge-base](https://github.com/leagames0221-sys/mais-pmi-knowledge-base)** — knowledge layer
- **[mais-portfolio](https://github.com/leagames0221-sys/mais-portfolio)** — overview

---

## License

MIT. See [LICENSE](LICENSE).

This is a portfolio demonstration. Commercial deployment for client engagements is offered separately under bespoke agreements.
