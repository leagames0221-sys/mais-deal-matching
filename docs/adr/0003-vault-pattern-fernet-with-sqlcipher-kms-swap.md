# ADR-0003: Vault Pattern — Fernet AES-128-CBC PoC with SQLCipher / KMS production swap path

## Status

Accepted (2026-05-22)

## Context

Japan's 2026 amended Personal Information Protection Act (APPI) introduces a breach-reporting exemption: **if PII is both encrypted at rest and pseudonymized at access time, the breach reporting obligation is waived**. The [README "Compliance angle"](../../README.md#compliance-angle) anchors the repo's pitch on demonstrating *the shape* of this exemption from day one.

Four constraints frame the vault design:

1. **PoC must run on a consumer laptop with no managed KMS** — see [Selected under](../../README.md#selected-under) zero-credit-card default. AWS KMS / Azure Key Vault / GCP KMS all require credit-card-backed accounts.
2. **Production deployment will use a managed KMS** — customer engagements operate under audit perimeters that require a real key-management story, not Fernet-on-disk.
3. **Module boundary must be enforceable** — the matching pipeline (`src/matching/`) must read pseudonymized fields only; it must not be possible to accidentally import `src/vault/*` from matching code.
4. **Vault read must be audit-logged** — every PII decryption is an append-only record (timestamp + actor + purpose), so post-hoc audit can reconstruct who saw which PII when.

## Decision

A two-store architecture with a documented swap surface:

| Store | Contents | PoC implementation | Production swap target |
| --- | --- | --- | --- |
| **Vault** | name / contact / DoB / detailed address / raw narrative text | Fernet (AES-128-CBC + HMAC-SHA256) over JSONL files | SQLCipher (AES-256) or PostgreSQL + envelope key via KMS |
| **Operational DB** | age band / region / industry / skills / Presidio-redacted text | JSONL files (no encryption — pseudonymized fields only) | PostgreSQL pseudonymized table |

Concrete commitments:

1. **Fernet over JSONL** ([src/vault/store.py](../../src/vault/store.py)) is the PoC implementation. Fernet provides authenticated symmetric encryption (`AES-128-CBC + HMAC-SHA256`) per [`cryptography.io`](https://cryptography.io/en/latest/fernet/).
2. **Swap path is literal in the same file** ([src/vault/store.py:L2-L4](../../src/vault/store.py)) — the SQLCipher / PostgreSQL + KMS migration target is documented in the module header.
3. **Audit log is append-only** with timestamp + actor + purpose per vault read.
4. **Module boundary is enforced at code-review time** — matching code never imports from `src/vault/*`; tests verify this.

## Why Fernet (and not the alternatives) for the PoC

### Fernet matches the consumer-laptop / zero-CC constraint

Fernet is a single Python dependency (`cryptography`), runs offline, requires no managed service, and produces authenticated ciphertext that a customer-side audit can verify with the same library. AES-128-CBC + HMAC-SHA256 is well within current security guidance for at-rest PII (NIST SP 800-131A revision 2 still lists AES-128 as approved through at least 2030).

### Fernet is small enough that the swap point is checkable

The Fernet interface (`Fernet(key).encrypt(b'...')` / `Fernet(key).decrypt(b'...')`) is ~10 LOC of glue. The swap to SQLCipher or `pgcrypto`-backed PostgreSQL is a single module rewrite, not a refactor. The customer engineer can read `src/vault/store.py` end-to-end before signing the migration plan.

## Alternatives considered

### Plaintext JSONL (no vault at all) (rejected)

- **Pros**: simplest; no key management.
- **Cons**: cannot demonstrate the 2026 APPI exemption shape; PII at rest is in plaintext; no audit trail; defeats the portfolio's pitch.
- **Why rejected**: misses the entire compliance claim.

### Direct SQLCipher in the PoC (rejected)

- **Pros**: production-grade encryption from day one.
- **Cons**: SQLCipher requires a `pysqlcipher3` build that pulls a C-extension compile step on the user's machine; on Windows in particular this is fragile (needs Visual C++ Build Tools); zero-CC reviewers experience install friction; the demo video cannot run on a fresh Windows laptop in <60 seconds.
- **Why rejected for PoC**: install friction breaks the consumer-laptop constraint. **Documented as the production swap target.**

### AWS KMS / Azure Key Vault / GCP KMS (rejected for PoC)

- **Pros**: production-grade KMS with envelope encryption.
- **Cons**: requires credit-card-backed cloud accounts; violates [Selected under](../../README.md#selected-under).
- **Why rejected for PoC**: cost constraint. **Documented as the production swap target** via the SQLCipher / PostgreSQL + KMS path.

### age / sodium (NaCl) (rejected)

- **Pros**: modern AEAD primitives; `age` is age-encryption.org's elegant CLI tool.
- **Cons**: `age` is a CLI-first tool, not a Python library with the same ergonomics; `pynacl` (libsodium binding) works but offers no advantage over Fernet for the PoC; the customer-side audit surface is less standardized than Fernet's.
- **Why rejected**: Fernet's `cryptography.io` provenance (Python Cryptographic Authority) gives stronger trust signal for the audit conversation.

### Tink (Google) (rejected)

- **Pros**: Google's recommended high-level crypto library.
- **Cons**: heavier dependency tree; Tink's Python binding is less mature than `cryptography`; less ergonomic for the simple at-rest case.
- **Why rejected**: surface mismatch with the simple-vault need.

## Module boundary enforcement

The 2026 APPI exemption shape requires that *embedding / matching code never sees raw PII*. This is enforced by:

1. **Code-review discipline** — matching modules (`src/matching/*.py`) must not contain `from ..vault import ...` or `from src.vault import ...`. Static check planned via `import-linter` or equivalent at customer-deployment hardening.
2. **Operational DB is the pseudonymized read surface** — matching reads `age_band` / `region` / `industry` / `skills` / Presidio-redacted narrative; the vault is read only by the introduction-request flow, which is a different code path with audit logging.
3. **Audit log replay** can prove no matching-side actor read raw PII over any window.

## Consequences

### Positive

- PoC demonstrates the 2026 APPI exemption shape on a consumer laptop with zero credit card.
- Swap path is a single module rewrite, not a refactor; customer migration plan is concrete and reviewable.
- Module boundary makes the compliance claim machine-checkable rather than prose-only.
- Audit log gives post-hoc accountability for every vault read.

### Negative

- Fernet uses AES-128, not AES-256. NIST guidance through 2030 accepts AES-128 for at-rest PII, but customer engagements with stricter internal policies may require AES-256 at PoC time — answered by the SQLCipher swap, but the migration is not trivial for those customers who insist on AES-256 in PoC.
- Audit log is JSONL append-only; not tamper-evident without an additional hash-chain step. Documented as a production hardening item.
- The module boundary is enforced at code-review time, not statically; a static check via `import-linter` is a planned hardening step.

### Reversibility

The vault interface (`store(record_id, plaintext) -> ciphertext` / `read(record_id, actor, purpose) -> plaintext`) is the surface; the encryption primitive behind it is swappable. The interface is what callers depend on; the primitive is implementation detail.

## References

- [Japan's amended Personal Information Protection Act — 個人情報の保護に関する法律 (PPC overview)](https://www.ppc.go.jp/personalinfo/legal/) — 2024 amendment + 2026 amendment regulatory text
- [Fernet specification](https://github.com/fernet/spec/blob/master/Spec.md)
- [`cryptography.io` Fernet documentation](https://cryptography.io/en/latest/fernet/)
- [NIST SP 800-131A revision 2 — Transitions: Recommendation for Transitioning the Use of Cryptographic Algorithms and Key Lengths](https://csrc.nist.gov/pubs/sp/800/131/a/r2/final)
- [SQLCipher documentation](https://www.zetetic.net/sqlcipher/documentation/) — production swap target
- [Microsoft Presidio documentation](https://microsoft.github.io/presidio/) — used for the pseudonymization surface
- Code: [src/vault/store.py](../../src/vault/store.py), [README — Compliance angle](../../README.md#compliance-angle)
