"""Unit + invariant tests for Week 3a matching pipeline (Stage 1/3/4)。"""
from __future__ import annotations

import pytest

from src.matching.bm25_index import tokenize
from src.matching.rrf import reciprocal_rank_fusion


# ─── tokenize (lightweight) ───────────────────────────────────────

def test_tokenize_japanese_simple():
    tokens = tokenize("[業界] 出版 [skill] 経営・事業企画")
    assert "出版" in tokens
    assert "経営" in tokens
    assert "事業企画" in tokens
    # 角括弧 / 中点 で分割される
    assert "[業界]" not in tokens
    assert "経営・事業企画" not in tokens


def test_tokenize_whitespace_and_brackets():
    tokens = tokenize("a b　c (d) 「e」") # 半角 + 全角 space + 各種 bracket
    assert tokens == ["a", "b", "c", "d", "e"]


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize(" ") == []


# ─── RRF (lightweight、 pure algorithm) ───────────────────────────

def test_rrf_basic_fusion():
    list_a = [("X", 0.9), ("Y", 0.8), ("Z", 0.7)]
    list_b = [("Y", 0.95), ("Z", 0.85), ("X", 0.75)]
    fused = reciprocal_rank_fusion([list_a, list_b], k=60)

    # 両 list で rank 上位 = fused score 最高 のはず
    # X: rank 1 in A (1/61) + rank 3 in B (1/63) = 0.0322
    # Y: rank 2 in A (1/62) + rank 1 in B (1/61) = 0.0325 ← 最高
    # Z: rank 3 in A (1/63) + rank 2 in B (1/62) = 0.0320
    ids = [i for i, _ in fused]
    assert set(ids) == {"X", "Y", "Z"}
    # Y が #1 (両 list で平均最上位)
    assert ids[0] == "Y"


def test_rrf_single_list_passthrough():
    """単一 rank list を fuse すると順序維持。"""
    fused = reciprocal_rank_fusion([[("a", 1), ("b", 2), ("c", 3)]])
    assert [i for i, _ in fused] == ["a", "b", "c"]


def test_rrf_top_k_limit():
    fused = reciprocal_rank_fusion(
        [[("a", 1), ("b", 2), ("c", 3), ("d", 4)]],
        top_k=2,
    )
    assert len(fused) == 2


def test_rrf_disjoint_lists():
    """重複なしの 2 list は全 item が単独 score で fuse される。"""
    fused = reciprocal_rank_fusion([
        [("a", 1), ("b", 2)],
        [("c", 1), ("d", 2)],
    ])
    ids = {i for i, _ in fused}
    assert ids == {"a", "b", "c", "d"}


# ─── Heavy integration (model 必要) ────────────────────────────────

@pytest.mark.slow
def test_bm25_smoke(tmp_path, monkeypatch):
    """BM25 が exact lexical match を捉える smoke (model 不要、 ただし合成 data 生成は重い)。"""
    import json
    from src.data_gen.generate_synthetic_profiles import generate
    from src.matching import bm25_index

    synth_dir = tmp_path / "synthetic"
    paths = generate(profile_count=20, company_count=20, seed=42, out_dir=synth_dir)
    monkeypatch.setattr(bm25_index, "SYNTHETIC_DIR", synth_dir)

    idx = bm25_index.build_companies_bm25()
    # "IT" を含む企業が必ず存在 (合成 data 20 件 / 20 業界 で 1 件は IT 命中見込み)
    results = idx.search("IT 経営経験 投資家ネットワーク", k=5)
    assert len(results) == 5
    # score > 0 が少なくとも 1 件
    assert any(s > 0 for _, s in results)


@pytest.mark.slow
def test_hybrid_pipeline_smoke():
    """4-stage hybrid pipeline e2e (e5-large + cross-encoder DL 必要、 local dogfood 用)。"""
    from src.matching.pipeline import hybrid_search

    results = hybrid_search("IT 経営経験 投資家ネットワーク CEO 希望", side="companies", top_k=5)
    assert len(results) == 5
    # cross-encoder score は実数値 (相対順位重視)
    scores = [s for _, s in results]
    # descending
    assert scores == sorted(scores, reverse=True)
