"""Smoke + invariant tests for embedding pipeline (ADR-006 PII/Op 分離後)."""
from __future__ import annotations

import pytest

from src.embedding.text_builder import company_op_to_text, profile_op_to_text


# 軽量 unit test (model 不要) -------------------------------------------------

def test_profile_op_to_text_field_order():
    profile_op = {
        "profile_id": "PROF-000001",
        "age_band": "50-59",
        "location_pref": "東京都",
        "industries": ["映像制作", "広告"],
        "skills": ["経営", "投資"],
        "executive_years": 15,
        "investor_network": True,
        "preferred_role": "CEO",
        "preferred_capital_size": "中堅 (50-500 億円)",
        "redacted_self_intro": "テスト自己紹介 (PII redact 済)",
    }
    text = profile_op_to_text(profile_op)
    assert "映像制作・広告" in text
    assert "CEO" in text
    assert "経営・投資" in text
    assert "15 年" in text
    assert "投資家ネットワーク保有" in text
    assert "50-59" in text
    assert "テスト自己紹介" in text
    # field 順序固定
    assert text.index("[業界]") < text.index("[役職希望]")
    assert text.index("[役職希望]") < text.index("[経営経験年数]")


def test_profile_op_no_investor_network():
    profile_op = {
        "industries": ["IT"], "skills": ["経営"], "investor_network": False,
        "age_band": "40-49", "location_pref": "大阪府", "executive_years": 5,
        "preferred_role": "COO", "preferred_capital_size": "中堅", "redacted_self_intro": "",
    }
    text = profile_op_to_text(profile_op)
    assert "投資家ネットワーク保有" not in text


def test_company_op_to_text_field_order():
    company_op = {
        "company_id": "COMP-00001",
        "industry": "出版",
        "revenue_band": "10-30 億円",
        "employee_count": 45,
        "location_pref": "大阪府",
        "founder_age_band": "70-79",
        "successor_requirements": ["経営経験", "出版業界知見"],
        "technical_assets": ["著者ネットワーク", "編集ノウハウ"],
        "financial_health": "黒字",
        "redacted_description": "テスト企業概要 (PII redact 済)",
    }
    text = company_op_to_text(company_op)
    assert "出版" in text
    assert "経営経験・出版業界知見" in text
    assert "著者ネットワーク・編集ノウハウ" in text
    assert "45 名" in text
    assert "70-79" in text
    assert text.index("[業界]") < text.index("[後継要件]")
    assert text.index("[後継要件]") < text.index("[売上規模]")


def test_text_builder_never_takes_pii():
    """text_builder は PII field 名 (name, email, phone, address_full) を一切受け付けない."""
    # PII を渡しても出力に出ない (= operational schema 専用) を smoke
    op_with_pii_keys_ignored = {
        "profile_id": "PROF-X",
        "name_kana": "シークレット",  # この field は profile_op_to_text が見ない
        "email": "secret@example.com",
        "industries": ["IT"], "skills": ["s"], "investor_network": False,
        "age_band": "50-59", "location_pref": "東京都", "executive_years": 10,
        "preferred_role": "CEO", "preferred_capital_size": "中堅", "redacted_self_intro": "ok",
    }
    text = profile_op_to_text(op_with_pii_keys_ignored)
    assert "シークレット" not in text
    assert "secret@example.com" not in text


# Heavy integration test (sentence-transformers model 必要) ------------------

@pytest.mark.slow
def test_encoder_smoke():
    from src.embedding.encoder import encode_queries, encode_documents
    import numpy as np

    query_vec = encode_queries(["テスト query"])
    doc_vec = encode_documents(["テスト passage"])

    assert query_vec.shape[0] == 1
    assert doc_vec.shape[0] == 1
    assert query_vec.shape[1] == doc_vec.shape[1]
    np.testing.assert_allclose(np.linalg.norm(query_vec, axis=1), 1.0, atol=1e-5)
    np.testing.assert_allclose(np.linalg.norm(doc_vec, axis=1), 1.0, atol=1e-5)


@pytest.mark.slow
def test_build_and_query_e2e(tmp_path, monkeypatch):
    import json
    from src.embedding import build_index, query_index

    data_dir = tmp_path
    synth_dir = data_dir / "synthetic"
    cache_dir = data_dir / "cache"
    synth_dir.mkdir()
    cache_dir.mkdir()

    profiles_op = [
        {
            "profile_id": "PROF-000001",
            "age_band": "50-59", "location_pref": "東京都",
            "industries": ["出版"], "skills": ["経営", "事業企画"],
            "executive_years": 18, "investor_network": True,
            "preferred_role": "CEO", "preferred_capital_size": "中堅 (10-50 億円)",
            "redacted_self_intro": "出版業界 18 年、 経営経験豊富、 投資家ネットワーク保有。",
        },
    ]
    companies_op = [
        {
            "company_id": "COMP-00001", "industry": "出版", "revenue_band": "10-30 億円",
            "employee_count": 45, "location_pref": "東京都", "founder_age_band": "70-79",
            "successor_requirements": ["経営経験", "出版業界知見"],
            "technical_assets": ["著者ネットワーク"], "financial_health": "黒字",
            "redacted_description": "出版業、 後継未定。 経営経験者求む。",
        },
        {
            "company_id": "COMP-00002", "industry": "建設", "revenue_band": "50-100 億円",
            "employee_count": 200, "location_pref": "北海道", "founder_age_band": "70-79",
            "successor_requirements": ["経営経験", "建設業界知見"],
            "technical_assets": ["施工実績"], "financial_health": "黒字",
            "redacted_description": "建設業、 北海道、 大規模工事専門。",
        },
    ]

    (synth_dir / "profiles_op_synthetic.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in profiles_op), encoding="utf-8"
    )
    (synth_dir / "companies_op_synthetic.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in companies_op), encoding="utf-8"
    )

    monkeypatch.setattr(build_index, "SYNTHETIC_DIR", synth_dir)
    monkeypatch.setattr(build_index, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(query_index, "SYNTHETIC_DIR", synth_dir)
    monkeypatch.setattr(query_index, "CACHE_DIR", cache_dir)

    build_index.build_all()

    results = query_index.search(profile_op_to_text(profiles_op[0]), side="companies", k=2)
    assert results[0][0] == "COMP-00001"
    assert results[0][1] > results[1][1]
