# MAIS — Deal Matching

> **Two-sided M&A matching engine** with a 5-stage hybrid retrieval pipeline and a PII Vault Pattern compliant with Japan's 2026 amended Personal Information Protection Act.
> Match successor candidates with professional intermediaries; embedding/matching never touches raw PII.

[![tests](https://img.shields.io/badge/tests-49%20passing%20%2F%2050-brightgreen)]()
[![pip-audit](https://github.com/leagames0221-sys/mais-deal-matching/actions/workflows/pip-audit.yml/badge.svg)](https://github.com/leagames0221-sys/mais-deal-matching/actions/workflows/pip-audit.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 30-second pitch

Japanese mid-market M&A intermediaries handle hundreds of thousands of candidate-side and buy-side records. Naive matching tools either (a) leak PII to embedding models, or (b) drop accuracy by stripping context.

**MAIS Deal Matching** solves both:
- **Retrieval quality** — 5-stage hybrid pipeline (BM25 + dense + RRF + cross-encoder + LLM listwise CoT rerank) — designed for Japanese-language sparse + dense complementarity *(Stages 1-4 active; Stage 5 LLM rerank uses MockProvider in PoC, Claude/Gemini swap is a 1-file change — see [PoC status](#poc-status-what-is-live-vs-deferred))*
- **PII compliance** — vault holds PII; only pseudonymized fields enter the embedding/matching path. Aligns with the 2026 amended APPI exemption (encrypted + pseudonymized → no breach reporting obligation) *(PoC: Fernet AES-128-CBC + HMAC-SHA256 over JSONL files; production-equivalent SQLCipher / PostgreSQL + KMS swap path is literal in `src/vault/store.py`)*

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

```bash
ANTHROPIC_API_KEY=sk-ant-...           # required from Stage 5 onward
SYNTHETIC_SEED=20260512                 # reproducibility
SYNTHETIC_PROFILE_COUNT=1000            # 1,000 in PoC; scale up for production
SYNTHETIC_COMPANY_COUNT=200
EMBEDDING_MODEL=intfloat/multilingual-e5-large
DATA_DIR=./data
VAULT_KEY=<fernet key>
SESSION_SECRET=<token_urlsafe>
```

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

## Production deployment notes

This repo is a PoC. For real PII / production:

- Run inside a sandbox (Docker / WSL2 / Codespaces)
- Wire OAuth providers to real Google / LinkedIn apps
- 1-week stability dry-run before client cutover
- External penetration test recommended for large engagements
- LLMProvider swap to self-hosted (Ollama / vLLM) for data residency requirements

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
