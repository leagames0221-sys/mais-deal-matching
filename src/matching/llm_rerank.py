"""Stage 5: LLM listwise rerank with MDPI CoT prompt。

MDPI 2024 paper "Zero-Shot Resume-Job Matching with LLMs via Structured Prompting" の
structured prompt + Chain-of-Thought reasoning pattern を採用、 Gemma で 87% accuracy
literal 報告。 本実装は LLM-agnostic、 LLMProvider interface 経由で plug-in。
"""
from __future__ import annotations

from src.matching.llm_provider import LLMProvider, get_provider


MAIS_COT_PROMPT_TEMPLATE = """以下は事業承継マッチング案件です。 query (片方) に対し candidates (もう片方) の relevance を CoT で評価し、 listwise rerank してください。

[query]
{query}

[candidates]
{candidates_block}

各 candidate について:
1. 業界 / skill / 地域 / 規模 等の axis ごとに query との整合を analyze (CoT)
2. fit_label を high / medium / low で判定
3. 1-2 文の reasoning を日本語で記述

最後に top_k = {top_k} を relevance 降順で返してください。"""


def listwise_rerank(
    query: str,
    candidates: list[tuple[str, str]],
    top_k: int = 5,
    provider: LLMProvider | None = None,
) -> list[tuple[str, str, str]]:
    """Stage 5 LLM listwise rerank entry point。

    Args:
        query: text query (profile_op_to_text / company_op_to_text / 自由 text)
        candidates: [(id, doc_text), ...] - Stage 4 cross-encoder 後の top-N
        top_k: 最終返却件数
        provider: LLMProvider 実装 (None なら env 経由で default = mock)

    Returns:
        [(id, fit_label, reasoning), ...] descending by relevance
    """
    if provider is None:
        provider = get_provider()
    return provider.listwise_rerank(query, candidates, top_k=top_k)


def build_cot_prompt(query: str, candidates: list[tuple[str, str]], top_k: int = 5) -> str:
    """real LLM 投入時に使う MDPI CoT prompt を構築 (mock は内部 heuristic で短絡)。"""
    block = "\n".join(
        f" {i+1}. [{cid}] {doc[:300]}..." for i, (cid, doc) in enumerate(candidates)
    )
    return MAIS_COT_PROMPT_TEMPLATE.format(
        query=query, candidates_block=block, top_k=top_k
    )
