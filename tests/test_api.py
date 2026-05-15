"""FastAPI TestClient unit test (light、 model 不要)。

ML model を必要としない endpoint (/health, /, /audit-log, mock-signin flow)
を中心にテスト。 /match は 5-stage pipeline 動かすため slow marker。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """test 用 isolated client: tmp DATA_DIR + synth + vault init。"""
    # env 設定 (vault key + session)
    monkeypatch.setenv("VAULT_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-32bytes-1234")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # 合成データ最小生成
    from src.data_gen.generate_synthetic_profiles import generate
    generate(profile_count=5, company_count=3, seed=42, out_dir=tmp_path / "synthetic")

    # module-level path 変数を tmp に reset (load_dotenv より後の literal 上書き)
    from src.vault import store as vault_store
    monkeypatch.setattr(vault_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(vault_store, "VAULT_DIR", tmp_path / "vault")
    monkeypatch.setattr(vault_store, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(vault_store, "AUDIT_LOG_PATH", tmp_path / "audit" / "access_log.jsonl")
    from src.operational import store as op_store
    monkeypatch.setattr(op_store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(op_store, "OP_DIR", tmp_path / "synthetic")

    # vault 初期化
    vault_store.init_vault_from_synthetic()

    # client 起動
    from src.api.app import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_landing(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MAIS" in r.text # rebrand 2026-05-12
    assert "PROF-" in r.text # 合成 profile 一覧表示


def test_mypage_requires_signin(client):
    r = client.get("/mypage")
    assert r.status_code == 401


def test_match_requires_signin(client):
    r = client.get("/match")
    assert r.status_code == 401


def test_mock_signin_unknown_profile(client):
    r = client.post("/mock-signin", data={"profile_id": "PROF-NOT-EXIST"})
    assert r.status_code == 404


def test_mock_signin_flow(client):
    """signin → mypage → vault PII access → audit literal 記録の e2e (model 不要 path)。"""
    # signin
    r = client.post("/mock-signin", data={"profile_id": "PROF-000001"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/mypage"

    # mypage (Op fields default) — rebrand 後の copy
    r = client.get("/mypage", follow_redirects=False)
    assert r.status_code == 200
    assert "公開情報 (仮名加工)" in r.text
    # PII fields は default 非表示
    assert "個人情報 vault (暗号化保管中)" in r.text

    # mypage with show_pii (vault decrypt)
    r = client.get("/mypage?show_pii=1", follow_redirects=False)
    assert r.status_code == 200
    assert "個人情報 vault (一時表示中)" in r.text

    # audit log 取得 (SIGNIN + GET 記録されている)
    r = client.get("/audit-log", follow_redirects=False)
    assert r.status_code == 200
    assert "SIGNIN" in r.text
    assert "PROF-000001" in r.text


def test_intro_endpoint_vault_join(client):
    """intro endpoint で vault PII join + audit 記録。"""
    client.post("/mock-signin", data={"profile_id": "PROF-000001"}, follow_redirects=False)
    r = client.post("/intro/COMP-00001", follow_redirects=False)
    assert r.status_code == 200
    assert "個人情報 vault への access が発生しました" in r.text # rebrand 後の copy
    # PII vault fields 表示確認 (synthetic data)
    assert "社名" in r.text


def test_signout(client):
    client.post("/mock-signin", data={"profile_id": "PROF-000001"}, follow_redirects=False)
    r = client.post("/signout", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # 再度 mypage は 401
    r = client.get("/mypage", follow_redirects=False)
    assert r.status_code == 401


# ─── 企業 (company) side テスト ──────────

def test_landing_shows_both_sides(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "PROF-" in r.text # 後継候補 sample
    assert "COMP-" in r.text # 企業 sample
    assert "後継候補として登録" in r.text
    assert "企業として登録" in r.text


def test_company_mypage_requires_signin(client):
    r = client.get("/company/mypage")
    assert r.status_code == 401


def test_company_match_requires_signin(client):
    r = client.get("/company/match")
    assert r.status_code == 401


def test_mock_signin_company_unknown(client):
    r = client.post("/mock-signin-company", data={"company_id": "COMP-NOT-EXIST"})
    assert r.status_code == 404


def test_company_signin_flow(client):
    """企業 signin → 企業マイページ → vault PII access → audit literal 記録の e2e。"""
    # signin (企業側)
    r = client.post("/mock-signin-company", data={"company_id": "COMP-00001"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/company/mypage"

    # 企業マイページ (Op fields default)
    r = client.get("/company/mypage", follow_redirects=False)
    assert r.status_code == 200
    assert "公開情報 (仮名加工)" in r.text
    assert "機密情報 vault (暗号化保管中)" in r.text # default 非表示
    # nav は企業マイページ用に切り替わる
    assert "企業マイページ" in r.text
    assert "候補者マッチング" in r.text

    # マイページ with show_pii (vault decrypt)
    r = client.get("/company/mypage?show_pii=1", follow_redirects=False)
    assert r.status_code == 200
    assert "機密情報 vault (一時表示中)" in r.text

    # audit log (企業 SIGNIN + GET 記録されている)
    r = client.get("/audit-log", follow_redirects=False)
    assert r.status_code == 200
    assert "SIGNIN" in r.text
    assert "COMP-00001" in r.text


def test_company_intro_endpoint_vault_join(client):
    """企業 → 後継候補 intro endpoint で vault PII join + audit literal 記録。"""
    client.post("/mock-signin-company", data={"company_id": "COMP-00001"}, follow_redirects=False)
    r = client.post("/company/intro/PROF-000001", follow_redirects=False)
    assert r.status_code == 200
    assert "候補者の個人情報 vault への access が発生しました" in r.text
    # 後継候補 PII vault fields 表示確認
    assert "氏名 (カナ)" in r.text


def test_signin_clears_other_side_session(client):
    """profile signin → company signin で profile session が clear される (一人 = 一 account 前提)。"""
    # profile signin
    client.post("/mock-signin", data={"profile_id": "PROF-000001"}, follow_redirects=False)
    r = client.get("/mypage", follow_redirects=False)
    assert r.status_code == 200

    # company signin (profile session 自動 clear 期待)
    client.post("/mock-signin-company", data={"company_id": "COMP-00001"}, follow_redirects=False)

    # profile mypage は 401 (clear 済)
    r = client.get("/mypage", follow_redirects=False)
    assert r.status_code == 401
    # company mypage は 200
    r = client.get("/company/mypage", follow_redirects=False)
    assert r.status_code == 200
