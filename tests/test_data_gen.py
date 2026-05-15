"""Smoke + invariant tests for synthetic data generator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.data_gen.generate_synthetic_profiles import generate


@pytest.fixture
def tmp_out_dir(tmp_path: Path) -> Path:
    return tmp_path / "synthetic"


def test_generate_smoke(tmp_out_dir: Path) -> None:
    paths = generate(profile_count=50, company_count=10, seed=42, out_dir=tmp_out_dir)

    for key in ("profiles_pii", "profiles_op", "companies_pii", "companies_op"):
        assert paths[key].exists(), f"missing: {key}"

    n_pii = len(paths["profiles_pii"].read_text(encoding="utf-8").splitlines())
    n_op = len(paths["profiles_op"].read_text(encoding="utf-8").splitlines())
    assert n_pii == n_op == 50

    n_c_pii = len(paths["companies_pii"].read_text(encoding="utf-8").splitlines())
    n_c_op = len(paths["companies_op"].read_text(encoding="utf-8").splitlines())
    assert n_c_pii == n_c_op == 10


def test_profile_pii_schema(tmp_out_dir: Path) -> None:
    paths = generate(profile_count=5, company_count=1, seed=42, out_dir=tmp_out_dir)
    pii = json.loads(paths["profiles_pii"].read_text(encoding="utf-8").splitlines()[0])

    required_pii_fields = {
        "profile_id", "name_kana", "name_full", "email", "phone",
        "address_full", "dob_exact", "raw_self_intro",
    }
    assert required_pii_fields.issubset(pii.keys())
    assert pii["profile_id"].startswith("PROF-")
    # PII layer は exact 値を保持
    assert "@" in pii["email"]
    assert len(pii["dob_exact"]) == 10 # YYYY-MM-DD


def test_profile_op_schema(tmp_out_dir: Path) -> None:
    paths = generate(profile_count=5, company_count=1, seed=42, out_dir=tmp_out_dir)
    op = json.loads(paths["profiles_op"].read_text(encoding="utf-8").splitlines()[0])

    required_op_fields = {
        "profile_id", "age_band", "location_pref", "industries", "skills",
        "executive_years", "investor_network", "preferred_role",
        "preferred_capital_size", "redacted_self_intro",
    }
    assert required_op_fields.issubset(op.keys())
    assert op["profile_id"].startswith("PROF-")
    # Op 側 = 仮名加工情報、 exact 年齢 / 連絡先 / 詳細住所 が含まれない
    assert "-" in op["age_band"] # "50-59" 形式
    assert "name_kana" not in op
    assert "email" not in op
    assert "phone" not in op
    assert "address_full" not in op
    assert "dob_exact" not in op


def test_company_pii_schema(tmp_out_dir: Path) -> None:
    paths = generate(profile_count=1, company_count=5, seed=42, out_dir=tmp_out_dir)
    pii = json.loads(paths["companies_pii"].read_text(encoding="utf-8").splitlines()[0])

    required_fields = {
        "company_id", "company_name", "address_full",
        "contact_person", "contact_email", "contact_phone", "raw_description",
    }
    assert required_fields.issubset(pii.keys())
    assert pii["company_id"].startswith("COMP-")
    assert "@" in pii["contact_email"]


def test_company_op_schema(tmp_out_dir: Path) -> None:
    paths = generate(profile_count=1, company_count=5, seed=42, out_dir=tmp_out_dir)
    op = json.loads(paths["companies_op"].read_text(encoding="utf-8").splitlines()[0])

    required_fields = {
        "company_id", "industry", "revenue_band", "employee_count",
        "location_pref", "founder_age_band", "successor_requirements",
        "technical_assets", "financial_health", "redacted_description",
    }
    assert required_fields.issubset(op.keys())
    assert op["company_id"].startswith("COMP-")
    # 仮名加工情報、 詳細住所 / 連絡先 が含まれない
    assert "-" in op["founder_age_band"]
    assert "company_name" not in op
    assert "address_full" not in op
    assert "contact_email" not in op
    assert "contact_phone" not in op


def test_pii_op_link_by_id(tmp_out_dir: Path) -> None:
    """PII / Op が profile_id / company_id で literal link する。"""
    paths = generate(profile_count=10, company_count=3, seed=42, out_dir=tmp_out_dir)

    pii_ids = [json.loads(line)["profile_id"]
               for line in paths["profiles_pii"].read_text(encoding="utf-8").splitlines()]
    op_ids = [json.loads(line)["profile_id"]
              for line in paths["profiles_op"].read_text(encoding="utf-8").splitlines()]
    assert pii_ids == op_ids

    c_pii_ids = [json.loads(line)["company_id"]
                 for line in paths["companies_pii"].read_text(encoding="utf-8").splitlines()]
    c_op_ids = [json.loads(line)["company_id"]
                for line in paths["companies_op"].read_text(encoding="utf-8").splitlines()]
    assert c_pii_ids == c_op_ids


def test_op_self_intro_redaction(tmp_out_dir: Path) -> None:
    """ProfileOp.redacted_self_intro に氏名 / 電話 / email / 詳細住所が含まれない。"""
    paths = generate(profile_count=20, company_count=5, seed=42, out_dir=tmp_out_dir)
    pii_list = [json.loads(l) for l in paths["profiles_pii"].read_text(encoding="utf-8").splitlines()]
    op_list = [json.loads(l) for l in paths["profiles_op"].read_text(encoding="utf-8").splitlines()]

    for pii, op in zip(pii_list, op_list):
        intro = op["redacted_self_intro"]
        assert pii["name_kana"] not in intro, f"PII leak: name_kana in op[{op['profile_id']}]"
        assert pii["email"] not in intro, f"PII leak: email in op[{op['profile_id']}]"
        assert pii["phone"] not in intro, f"PII leak: phone in op[{op['profile_id']}]"
        assert pii["address_full"] not in intro, f"PII leak: address_full in op[{op['profile_id']}]"


def test_seed_reproducibility(tmp_path: Path) -> None:
    """同 seed = 同出力 (doctrine: verify-priority automation test)。"""
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    paths_a = generate(profile_count=10, company_count=3, seed=12345, out_dir=out_a)
    paths_b = generate(profile_count=10, company_count=3, seed=12345, out_dir=out_b)

    for key in paths_a:
        assert paths_a[key].read_text(encoding="utf-8") == paths_b[key].read_text(encoding="utf-8"), \
            f"reproducibility broken: {key}"
