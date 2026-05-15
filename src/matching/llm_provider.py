"""LLM provider interface (pluggable、 ADR-005 Stage 5)。

User constraint 「無料 + クレカ不要」 順守 + doctrine: no-design-compromise: framework は full design、
具体 LLM (Claude / Gemini / Ollama / 等) は plug-in 形式。 PoC は MockProvider (template-based)、
本番移植時に GeminiProvider (free tier、 CC 不要) 等に literal swap 可能。
"""
from __future__ import annotations

import os
from typing import Protocol


class LLMProvider(Protocol):
    """LLM listwise rerank の最小 interface。"""

    def listwise_rerank(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        top_k: int = 5,
    ) -> list[tuple[str, str, str]]:
        """candidates = [(id, doc_text), ...] を listwise rerank。

        returns: [(id, fit_score_label, reasoning), ...] descending by relevance
                 fit_score_label = "high" / "medium" / "low" (CoT 由来の literal label)
        """
        ...


class MockProvider:
    """Template-based mock LLM (test / PoC demo 用、 LLM API call なし)。

    fit 理由 = candidate doc 内の field 抽出 + simple heuristic。 構造のみ示し、
    本番では Gemini / Claude / Ollama 等の real LLM に literal swap。
    """

    def listwise_rerank(
        self,
        query: str,
        candidates: list[tuple[str, str]],
        top_k: int = 5,
    ) -> list[tuple[str, str, str]]:
        """candidates の順序を維持 (cross-encoder 上流前提)、 fit_label + reasoning を生成。

        MockProvider は cross-encoder の order を尊重し、 LLM listwise rerank framework の
        「shape」 のみ提供。 本番 LLM では query / candidate を CoT prompt で同時評価し
        order 自体を変動させる (MDPI 2024 paper の structured prompting pattern)。
        """
        results: list[tuple[str, str, str]] = []
        # query から keyword 抽出 (簡易、 角括弧 tag 内側を見る)
        query_keywords = self._extract_keywords(query)

        for rank, (cid, doc) in enumerate(candidates[:top_k], 1):
            doc_keywords = self._extract_keywords(doc)
            overlap = query_keywords & doc_keywords
            # heuristic: overlap 多 = high、 中 = medium、 少 = low
            if len(overlap) >= 3:
                label = "high"
            elif len(overlap) >= 1:
                label = "medium"
            else:
                label = "low"

            reasoning = self._build_reasoning(rank, overlap, doc_keywords)
            results.append((cid, label, reasoning))

        return results

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        """text → keyword 集合 (角括弧 tag 内側 + 業界名 / skill 名 等を抽出、 簡易)。"""
        import re
        # [..] 内側、 中点で分割
        kw: set[str] = set()
        for match in re.findall(r"\[[^\]]+\]\s*([^\[]+)", text):
            for token in re.split(r"[・、,;\s]+", match):
                token = token.strip()
                if 2 <= len(token) <= 20:
                    kw.add(token)
        return kw

    @staticmethod
    def _build_reasoning(rank: int, overlap: set[str], doc_keywords: set[str]) -> str:
        ov_top = list(overlap)[:5]
        if ov_top:
            return f"#{rank}: 一致 keyword = {', '.join(ov_top)} (mock LLM、 cross-encoder 順序 + heuristic)"
        return f"#{rank}: 直接一致 keyword なし、 cross-encoder semantic 類似で上位 (mock LLM)"


def get_provider(name: str | None = None) -> LLMProvider:
    """env 経由で provider 切替 (default = mock)。

    将来 'gemini' / 'claude' / 'ollama' / 'groq' / 'mistral' を追加可能、
    各 provider の API key は .env (gitignore) で別途設定。
    """
    name = name or os.environ.get("LLM_PROVIDER", "mock").lower()
    if name == "mock":
        return MockProvider()
    raise NotImplementedError(
        f"LLMProvider '{name}' は未実装、 mock のみ PoC scope (ADR-005 Stage 5 framework は ready)"
    )
