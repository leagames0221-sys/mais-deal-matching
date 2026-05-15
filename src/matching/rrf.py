"""Stage 3: Reciprocal Rank Fusion (RRF)。

BM25 (Stage 1、 lexical) と dense embedding (Stage 2、 semantic) の
2 rank list を 1 つに統合。 各 list の rank r (1-based) に対し
score = sum(1 / (k + r))、 k = 60 が業界 default (Cormack et al. 2009)。

Reference: original proposal + slavadubrov 2026-02 blog の standard 実装。
"""
from __future__ import annotations

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rank_lists: list[list[tuple[str, float]]],
    k: int = DEFAULT_RRF_K,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """複数 rank list を fuse、 RRF score 降順の (id, score) を返す。

    各 rank_list = [(id, raw_score), ...]、 raw_score は無視 (rank のみ使用)。
    """
    rrf_scores: dict[str, float] = {}
    for rank_list in rank_lists:
        for rank, (item_id, _) in enumerate(rank_list, start=1):
            rrf_scores[item_id] = rrf_scores.get(item_id, 0.0) + 1.0 / (k + rank)

    fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    if top_k is not None:
        fused = fused[:top_k]
    return fused
