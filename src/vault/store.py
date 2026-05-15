"""PII Vault: 暗号化 at rest + access audit log。

試作 phase = Fernet (AES-128-CBC + HMAC-SHA256) で JSONL を file 単位暗号化。
移植 phase = SQLCipher / PostgreSQL + KMS で同等 AES + envelope key 化。

Access は src/vault/store.py の関数経由のみ、 全 read を data/audit/access_log.jsonl に
append-only emit。 embedding / matching layer は本 module を literal import 不可
(module boundary check)。
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
VAULT_DIR = DATA_DIR / "vault"
AUDIT_DIR = DATA_DIR / "audit"
AUDIT_LOG_PATH = AUDIT_DIR / "access_log.jsonl"


def _get_key() -> bytes:
    """Vault encryption key を env から取得、 無ければ生成 + .env 追記 hint (試作のみ)。"""
    key_str = os.environ.get("VAULT_KEY")
    if not key_str:
        # 試作: 初回 key 生成、 user に instruction 表示
        key = Fernet.generate_key()
        raise RuntimeError(
            f"VAULT_KEY 未設定。 .env に下記を追記してください:\n"
            f" VAULT_KEY={key.decode()}\n"
            f"(本 key は試作用、 移植時は AWS KMS / Cloud KMS に置換)"
        )
    return key_str.encode()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_audit(action: str, item_id: str, requester: str = "system", reason: str = "") -> None:
    """全 vault access を audit log に append。"""
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": _now_iso(),
        "action": action,
        "item_id": item_id,
        "requester": requester,
        "reason": reason,
    }
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _vault_file(table: str) -> Path:
    """table 名 → vault file path (例: 'profile_pii' → data/vault/profile_pii.enc)。"""
    return VAULT_DIR / f"{table}.enc"


def _load_vault(table: str) -> dict[str, dict[str, Any]]:
    """暗号化 file を復号 → id-keyed dict 返す。"""
    path = _vault_file(table)
    if not path.exists():
        return {}
    key = _get_key()
    f = Fernet(key)
    try:
        plaintext = f.decrypt(path.read_bytes()).decode("utf-8")
    except InvalidToken:
        raise RuntimeError(f"VAULT_KEY 不一致、 {path} を復号不能 (key rotate?)")
    records = {}
    for line in plaintext.splitlines():
        if line.strip():
            rec = json.loads(line)
            id_field = "profile_id" if "profile_id" in rec else "company_id"
            records[rec[id_field]] = rec
    return records


def _save_vault(table: str, records: dict[str, dict[str, Any]]) -> None:
    """id-keyed dict → 暗号化 file 書込。"""
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    key = _get_key()
    f = Fernet(key)
    plaintext = "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records.values())
    ciphertext = f.encrypt(plaintext.encode("utf-8"))
    _vault_file(table).write_bytes(ciphertext)


# ─── public API (audit log 自動 emit) ──────────────────────────────

def put_profile_pii(record: dict[str, Any], requester: str = "register") -> None:
    """ProfilePII を vault に格納 (会員登録 / マイページ編集経由)。"""
    records = _load_vault("profile_pii")
    records[record["profile_id"]] = record
    _save_vault("profile_pii", records)
    emit_audit("PUT", record["profile_id"], requester, "vault write")


def get_profile_pii(profile_id: str, requester: str, reason: str) -> dict[str, Any] | None:
    """ProfilePII を vault から取得 (intro 承認 flow / 本人マイページ 経由のみ呼出可)。"""
    records = _load_vault("profile_pii")
    rec = records.get(profile_id)
    emit_audit("GET", profile_id, requester, reason)
    return rec


def put_company_pii(record: dict[str, Any], requester: str = "register") -> None:
    records = _load_vault("company_pii")
    records[record["company_id"]] = record
    _save_vault("company_pii", records)
    emit_audit("PUT", record["company_id"], requester, "vault write")


def get_company_pii(company_id: str, requester: str, reason: str) -> dict[str, Any] | None:
    records = _load_vault("company_pii")
    rec = records.get(company_id)
    emit_audit("GET", company_id, requester, reason)
    return rec


def generate_id(prefix: str) -> str:
    """profile_id / company_id 生成 (token、 不可推測)。"""
    return f"{prefix}-{secrets.token_urlsafe(8)}"


def init_vault_from_synthetic() -> None:
    """合成データ profiles_pii_synthetic.jsonl / companies_pii_synthetic.jsonl
    を vault に literal 投入 (PoC demo 用、 移植時には real 会員登録 flow で置換)。"""
    synthetic = DATA_DIR / "synthetic"
    for table, src in [
        ("profile_pii", synthetic / "profiles_pii_synthetic.jsonl"),
        ("company_pii", synthetic / "companies_pii_synthetic.jsonl"),
    ]:
        if not src.exists():
            continue
        records = {}
        for line in src.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                id_field = "profile_id" if "profile_id" in rec else "company_id"
                records[rec[id_field]] = rec
        _save_vault(table, records)
        emit_audit("INIT", table, "init_vault_from_synthetic", f"loaded {len(records)} records")
