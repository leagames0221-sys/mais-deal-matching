"""Unit tests for Stage 5 LLM listwise rerank (MockProvider)。"""
from __future__ import annotations

from src.matching.llm_provider import MockProvider, get_provider
from src.matching.llm_rerank import build_cot_prompt, listwise_rerank


def test_mock_provider_basic():
    provider = MockProvider()
    candidates = [
        ("A", "[業界] 出版 [skill] 経営・事業企画 [地域] 京都府"),
        ("B", "[業界] IT [skill] DX 推進 [地域] 東京都"),
    ]
    query = "[業界] 出版 [skill] 経営 [地域] 関西"
    results = provider.listwise_rerank(query, candidates, top_k=2)

    assert len(results) == 2
    # 戻り値の shape = (id, fit_label, reasoning)
    for cid, label, reasoning in results:
        assert cid in {"A", "B"}
        assert label in {"high", "medium", "low"}
        assert isinstance(reasoning, str) and len(reasoning) > 0


def test_mock_provider_fit_label_logic():
    """overlap 多 = high、 少 = medium / low (heuristic)。"""
    provider = MockProvider()
    # query と全 keyword 一致 → high
    candidates = [("X", "[業界] 出版 [skill] 経営 [地域] 京都府")]
    results = provider.listwise_rerank("[業界] 出版 [skill] 経営 [地域] 京都府", candidates, top_k=1)
    assert results[0][1] == "high"

    # 全く一致なし → low
    candidates = [("Y", "[業界] 建設 [skill] 施工管理 [地域] 北海道")]
    results = provider.listwise_rerank("[業界] 出版 [skill] 経営 [地域] 京都府", candidates, top_k=1)
    assert results[0][1] == "low"


def test_get_provider_default_mock():
    provider = get_provider("mock")
    assert isinstance(provider, MockProvider)


def test_get_provider_unknown_raises():
    """未実装 provider = NotImplementedError、 framework は ready 表明。"""
    import pytest
    with pytest.raises(NotImplementedError, match="未実装"):
        get_provider("gemini")


def test_listwise_rerank_entry_point():
    candidates = [
        ("A", "[業界] 出版 [skill] 経営"),
        ("B", "[業界] IT [skill] 投資家ネットワーク"),
    ]
    results = listwise_rerank("出版 経営", candidates, top_k=2)
    assert len(results) == 2


def test_build_cot_prompt():
    prompt = build_cot_prompt(
        "出版 後継 経営経験",
        [("A", "[業界] 出版"), ("B", "[業界] 建設")],
        top_k=2,
    )
    assert "事業承継マッチング" in prompt
    assert "出版 後継 経営経験" in prompt
    assert "[A]" in prompt
    assert "[B]" in prompt
    assert "Chain-of-Thought" in prompt or "CoT" in prompt
