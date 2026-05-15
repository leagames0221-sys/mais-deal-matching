"""Unit tests for vault (Fernet encryption) + operational + redaction."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch):
    """env DATA_DIR を tmp に切替、 module 内 path 変数も差し替え。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("VAULT_KEY", Fernet.generate_key().decode())
    from src.vault import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(store, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(store, "AUDIT_LOG_PATH", tmp_path / "audit" / "access_log.jsonl")
    return tmp_path


def test_vault_roundtrip_profile_pii(isolated_data_dir):
    from src.vault.store import get_profile_pii, put_profile_pii

    rec = {
        "profile_id": "PROF-test001",
        "name_kana": "テスト タロウ",
        "name_full": "テスト 太郎",
        "email": "test@example.com",
        "phone": "090-1111-2222",
        "address_full": "東京都港区テスト 1-2-3",
        "dob_exact": "1975-01-01",
        "raw_self_intro": "テスト self intro",
    }
    put_profile_pii(rec, requester="test_register")

    loaded = get_profile_pii("PROF-test001", requester="self:PROF-test001", reason="test")
    assert loaded == rec


def test_vault_encryption_at_rest(isolated_data_dir):
    """vault file 内容が plaintext で読めない (literal 暗号化されている)。"""
    from src.vault.store import put_profile_pii

    rec = {
        "profile_id": "PROF-test002",
        "name_kana": "シークレット ジョー",
        "name_full": "秘密 譲二",
        "email": "secret@example.com",
        "phone": "080-9999-8888",
        "address_full": "secret address",
        "dob_exact": "1980-01-01",
        "raw_self_intro": "本 raw_self_intro は decrypt なしで literal 読めないべき",
    }
    put_profile_pii(rec)

    vault_file = isolated_data_dir / "vault" / "profile_pii.enc"
    assert vault_file.exists()
    raw_bytes = vault_file.read_bytes()
    # plaintext PII が file bytes に literal 出現しない (encrypted)
    assert b"\xe7\xa7\x98\xe5\xaf\x86" not in raw_bytes # 「秘密」 (UTF-8)
    assert b"secret@example.com" not in raw_bytes
    assert b"080-9999-8888" not in raw_bytes


def test_vault_audit_log_emit(isolated_data_dir):
    """全 vault access が audit log に literal 記録される。"""
    import json
    from src.vault.store import AUDIT_LOG_PATH, get_profile_pii, put_profile_pii

    rec = {"profile_id": "PROF-audit", "name_kana": "オーディット", "name_full": "audit", "email": "a@b.c", "phone": "0", "address_full": "x", "dob_exact": "2000-01-01", "raw_self_intro": "ok"}
    put_profile_pii(rec, requester="audit_test_put")
    get_profile_pii("PROF-audit", requester="audit_test_get", reason="audit verify")

    assert AUDIT_LOG_PATH.exists()
    entries = [json.loads(l) for l in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    actions = [(e["action"], e["requester"]) for e in entries]
    assert ("PUT", "audit_test_put") in actions
    assert ("GET", "audit_test_get") in actions


def test_redaction_basic():
    from src.redaction.redactor import redact

    text = "山田 太郎 (090-1234-5678 / yamada@example.com) は東京都港区赤坂 1-2-3 在住。"
    out = redact(
        text,
        name_full="山田 太郎",
        phone="090-1234-5678",
        email="yamada@example.com",
        address_full="東京都港区赤坂 1-2-3",
    )
    assert "山田 太郎" not in out
    assert "090-1234-5678" not in out
    assert "yamada@example.com" not in out
    assert "東京都港区赤坂" not in out
    assert "[NAME]" in out and "[PHONE]" in out and "[EMAIL]" in out and "[ADDRESS]" in out


def test_redaction_regex_sweep():
    """known PII を渡さなくても regex で 2 次 sweep される。"""
    from src.redaction.redactor import redact
    text = "連絡: 03-1234-5678、 メール foo.bar@hoge.co.jp"
    out = redact(text)
    assert "[PHONE]" in out
    assert "[EMAIL]" in out
    assert "03-1234-5678" not in out
    assert "foo.bar@hoge.co.jp" not in out


def test_age_to_band():
    from src.redaction.redactor import age_to_band
    assert age_to_band(50) == "50-59"
    assert age_to_band(59) == "50-59"
    assert age_to_band(60) == "60-69"
    assert age_to_band(72) == "70-79"
