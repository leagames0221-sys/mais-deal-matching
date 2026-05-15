"""Stage 4: Cross-encoder pair-wise reranker。

dense (e5、 Stage 2) は bi-encoder = query / corpus 別 embedding の独立計算で
速いが pair-wise の精密 relevance は cross-encoder に劣る。 Stage 3 RRF で
fuse した上位 candidate に対し cross-encoder を適用、 listwise を pair-wise
精度で order し直す。

Reference: HuggingFace 公式 cross-encoder/ms-marco-MiniLM-L-12-v2。
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sentence_transformers import CrossEncoder

load_dotenv()

DEFAULT_MODEL = os.environ.get(
    "CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-12-v2"
)


@lru_cache(maxsize=1)
def _get_model(name: str = DEFAULT_MODEL) -> CrossEncoder:
    return CrossEncoder(name)


def rerank(
    query: str,
    candidates: list[tuple[str, str]],
    top_k: int | None = None,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple[str, float]]:
    """candidates = [(id, doc_text), ...] を cross-encoder で rerank。

    返り値 = [(id, cross_encoder_score), ...] descending。
    """
    if not candidates:
        return []

    model = _get_model(model_name)
    pairs = [(query, doc) for _, doc in candidates]
    scores = model.predict(pairs, show_progress_bar=False)

    ranked = sorted(
        [(cid, float(s)) for (cid, _), s in zip(candidates, scores)],
        key=lambda x: x[1],
        reverse=True,
    )
    if top_k is not None:
        ranked = ranked[:top_k]
    return ranked
