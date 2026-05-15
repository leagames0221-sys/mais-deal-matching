# MAIS — Deal Matching

> **M&A Intelligence Suite (MAIS)** の 1 番目のツール。
> M&A 後継候補 (買い手 / 売り手) と プロフェッショナル仲介者 を
> **5-stage hybrid pipeline + PII Vault Pattern** でマッチングする two-sided platform PoC。

[![tests](https://img.shields.io/badge/tests-43%20passed-brightgreen)]()
[![pip-audit](https://img.shields.io/badge/pip--audit-0%20CVE-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.11+-blue)]()
[![license](https://img.shields.io/badge/license-PoC%20demo-lightgrey)]()

---

## 何ができるか

| 機能 | 内容 |
|---|---|
| **5-stage hybrid pipeline** | BM25 (sparse) + multilingual-e5-large dense + RRF (Reciprocal Rank Fusion) + cross-encoder rerank + LLM listwise CoT rerank |
| **PII Vault Pattern** | PII (氏名 / 連絡先 / 詳細住所 / 生年月日) は SQLCipher 暗号化 vault DB、 embedding/matching が読むのは仮名加工 Operational DB のみ |
| **会員制 two-sided マイページ** | mock OAuth (Google / LinkedIn provider hook) + Vault PII 一時閲覧 + audit log append-only |
| **fit_label + CoT reasoning** | 上位 5 候補 each に LLM 生成の fit 理由 (Chain-of-Thought) を付与 |
| **黒×金 brand UI** | FastAPI + Jinja2 + slate palette + φ typography |
| **vendor lock-in ZERO** | Anthropic API + OSS only、 MockProvider で API key 不要動作可 |

---

## security architecture (PII Vault Pattern)

国内 PII 漏洩事案連発 (2024 = 上場 189 社 4 年連続最多) + 個人情報保護法 2026 改正方針 (暗号化 + 仮名加工で漏洩報告義務 ZERO) に対応:

- **PII vault DB** (暗号化 at rest、 SQLCipher、 access audit): 氏名 / 連絡先 / 詳細住所 / 生年月日 / 生 text
- **Operational DB** (仮名加工情報、 embedding が読む): 年代 band / 都道府県 / 業界 / skill / Presidio redact 済 text
- embedding / matching engine は **operational 側のみ literal 読む**、 vault join は紹介承認 flow のみ
- 漏洩しても Op = 仮名加工情報 = 報告義務 ZERO、 vault は暗号化 + 多層防御

---

## 想定ユースケース

- **M&A 仲介者 / プロフェッショナル firm** が後継候補マッチング platform として deploy
- **事業承継 advisory firm** の候補発掘 + 仲介支援
- **PE / VC** の deal sourcing + portfolio company マッチング

---

## tech stack

| 層 | 採用 |
|---|---|
| Embedding | sentence-transformers (multilingual-e5-large、 日本語強い OSS) |
| ANN search | FAISS (in-memory similarity search、 数十万件まで host PC で扱える) |
| LLM | anthropic SDK (Claude Sonnet 4.6) + MockProvider swap path |
| Web UI | FastAPI + uvicorn + Jinja2 |
| 合成データ | Faker + 自前業種テンプレ (ja_JP locale) |
| Security | SQLCipher (vault) + Presidio (PII redact) + Vault Pattern + Audit log |
| Test | pytest 43 件 (unit + integration、 真 bug 9 件 audit-driven fix) |

---

## 採用ひな形 (decomposed prior art)

| ひな形 | 採用 pattern | license |
|---|---|---|
| [HuggingFace sentence-transformers semantic-search](https://github.com/huggingface/sentence-transformers/tree/main/examples/sentence_transformer/applications/semantic-search) | asymmetric semantic search (`encode_query` / `encode_document`)、 FAISS index pattern | Apache-2.0 |
| [MDPI 2024 "Zero-Shot Resume-Job Matching with LLMs"](https://www.mdpi.com/2079-9292/14/24/4960) | structured prompt + Chain-of-Thought (zero-shot 87% accuracy) | academic open |
| [IRS2021 "Embedding-based Recommender"](https://irsworkshop.github.io/2021/publications/IRS2021_paper_6.pdf) | two-sided embedding (profile / company 別 vector space) | academic open |

---

## verify evidence

- **43 test PASS** (39 fast + 4 slow)
- **真 bug 9 件 audit-driven fix** (literal 検出 + literal 修正)
- **CVE catch + fix 1 件** (CVE-2025-71176 pytest)
- **pip-audit + Dependabot 配線済**

---

## 4-Week roadmap (PoC scope、 全 literal 完遂)

| Week | scope | status |
|---|---|---|
| **Week 1** | PJ scaffold + 合成データ generator (PII / Op 分離) | ✅ |
| **Week 2** | embedding pipeline (multilingual-e5-large、 1,200 件 indexing) | ✅ |
| **Week 3** | 5-stage hybrid pipeline (BM25 + dense + RRF + cross-encoder + LLM listwise rerank) | ✅ |
| **Week 4** | 会員制マイページ UI (mock OAuth + redaction + Vault Pattern) | ✅ |

---

## quick start

```powershell
# 1. Python 仮想環境
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-week4.txt     # full PoC stack

# 2. 合成データ生成 (1,000 profile + 200 company × PII/Op = 4 JSONL)
python -m src.data_gen.generate_synthetic_profiles

# 3. embedding indexing (multilingual-e5-large 初回 DL ~2.2GB、 1,200 件 ~7 分)
python -m src.embedding.build_index

# 4. dev key 生成 + vault 初期化
python -m scripts.setup_dev                # 1 回目: VAULT_KEY/SESSION_SECRET 出力
# 表示された値を .env file に literal copy (gitignore 済)
python -m scripts.setup_dev                # 2 回目: vault に合成 PII 暗号化保管

# 5. UI 起動
.venv/Scripts/python.exe -m uvicorn src.api.app:app --reload --port 8000
# → http://localhost:8000/ で landing
```

## demo flow

1. **landing** (http://localhost:8000/) — 合成 profile 10 件 select
2. **mock-signin** で PROF-000001 (例: 食品製造 / 60-69 / 千葉県) を選択
3. **マイページ** — Op fields default 表示、 「PII vault 一時閲覧」 で暗号化 vault から復号 + audit 記録
4. **マッチング** — 5-stage pipeline 実行、 top-5 全件 業界 fit + fit_label + CoT reasoning
5. **紹介リクエスト** — vault PII join (社名 / 担当者連絡先 / raw description)、 audit literal 記録
6. **監査ログ** — 全 vault access trace を append-only で表示 (透明性 demo)

---

## env 設定

```bash
ANTHROPIC_API_KEY=sk-ant-...           # 必須 (Week 3 から)
SYNTHETIC_SEED=20260512                 # 合成データ seed (再現性確保)
SYNTHETIC_PROFILE_COUNT=1000            # 試作 = 1,000、 移植時 = 拡張
SYNTHETIC_COMPANY_COUNT=200             # 試作 = 200、 移植時 = 拡張
EMBEDDING_MODEL=intfloat/multilingual-e5-large
DATA_DIR=./data
VAULT_KEY=<fernet key>                  # vault PII 暗号化
SESSION_SECRET=<token_urlsafe>          # FastAPI session
```

---

## 制約 (PoC scope)

- **無料 + クレカ不要範囲** (pip OSS + GitHub PRIVATE + Cloudflare quick tunnel)
- **consumer laptop** で完走
- **合成データ only** — 実 PII / 実顧客 DB は一切扱わない (移植時 sandbox 必須)
- **vendor lock-in ZERO**

---

## 移植段階の追加要件

- 実 PII 投入時 = sandbox (Docker / WSL2) + 顧客 sandbox dry-run + 1 週間 stability
- OAuth provider 本実装 (Google / LinkedIn 本契約)
- 大型案件 = external pentesting 推奨

---

## related tools (M&A Intelligence Suite)

- **mais-deal-matching** ← 本リポジトリ (sourcing stage)
- **mais-dd-workbench** — Due Diligence automation
- **mais-day1-cockpit** — Day-1 readiness
- **mais-pmi-cockpit** — 100-day PMI dashboard
- **mais-pmi-knowledge-base** — knowledge layer (全 tool 共通参照)

---

## license

PoC demo — 設計思想 + コード構造を portfolio 公開、 合成データのみ含む。 商用 deploy は別途相談。
