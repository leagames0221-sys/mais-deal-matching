"""5-stage hybrid matching pipeline。

Pipeline:
  Stage 1: BM25 sparse retrieval (top-N、 lexical 重み)
  Stage 2: dense embedding (e5-large + FAISS、 top-N、 semantic 重み) — Week 2 既存
  Stage 3: Reciprocal Rank Fusion (RRF、 1 と 2 を fuse → top-M)
  Stage 4: cross-encoder rerank (top-K candidate、 pair-wise)
  Stage 5: LLM listwise rerank with CoT prompt + fit_label + reasoning (top_k final)

Stage 5 は LLMProvider interface 経由 pluggable (mock / Gemini / Ollama / Claude 等)、
default = MockProvider (template-based)、 LLM_PROVIDER env で切替。

Usage:
  python -m src.matching.pipeline --side companies --profile-id PROF-000001 -k 5
  python -m src.matching.pipeline --side companies --text "出版 後継 関西" -k 5

 読込、 vault touched しない。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from src.embedding.query_index import search as dense_search
from src.embedding.text_builder import company_op_to_text, profile_op_to_text
from src.matching.bm25_index import (
    BM25Side,
    get_companies_bm25,
    get_profiles_bm25,
)
from src.matching.cross_encoder_rerank import rerank as cross_encoder_rerank
from src.matching.llm_rerank import listwise_rerank as llm_listwise_rerank
from src.matching.rrf import reciprocal_rank_fusion

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"

# Stage 1/2 candidate width (rrf は recall 重視で広めに、 cross-encoder の input 量を吸収)
DEFAULT_CANDIDATE_N = 50
DEFAULT_RRF_TOP = 25


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _items_by_id(side: str) -> tuple[dict[str, dict], callable]:
    if side == "companies":
        path = SYNTHETIC_DIR / "companies_op_synthetic.jsonl"
        id_key = "company_id"
        text_fn = company_op_to_text
    elif side == "profiles":
        path = SYNTHETIC_DIR / "profiles_op_synthetic.jsonl"
        id_key = "profile_id"
        text_fn = profile_op_to_text
    else:
        raise ValueError(f"side must be 'companies' or 'profiles', got {side!r}")

    items = _load_jsonl(path)
    return {it[id_key]: it for it in items}, text_fn


def hybrid_search(
    query: str,
    side: str,
    top_k: int = 10,
    candidate_n: int = DEFAULT_CANDIDATE_N,
    rrf_top: int = DEFAULT_RRF_TOP,
    bm25_index: BM25Side | None = None,
) -> list[tuple[str, float]]:
    """4-stage hybrid search、 final = [(id, cross_encoder_score), ...] descending。

    Stage 5 LLM rerank は別関数 `hybrid_search_with_reasoning` (CoT fit 理由付き)。
    """
    items_by_id, text_fn = _items_by_id(side)

    # Stage 1: BM25 sparse retrieval (module-level cache、 起動時 1 回 build / query は cache hit)
    if bm25_index is None:
        bm25_index = get_companies_bm25() if side == "companies" else get_profiles_bm25()
    bm25_results = bm25_index.search(query, k=candidate_n)

    # Stage 2: dense embedding (Week 2 既存 query_index.search)
    dense_results = dense_search(query, side=side, k=candidate_n)

    # Stage 3: RRF fusion
    fused = reciprocal_rank_fusion([bm25_results, dense_results], top_k=rrf_top)

    # Stage 4: cross-encoder rerank
    candidates_for_rerank = [
        (item_id, text_fn(items_by_id[item_id]))
        for item_id, _ in fused
        if item_id in items_by_id
    ]
    final = cross_encoder_rerank(query, candidates_for_rerank, top_k=top_k)
    return final


def hybrid_search_with_reasoning(
    query: str,
    side: str,
    top_k: int = 5,
    candidate_n: int = DEFAULT_CANDIDATE_N,
    rrf_top: int = DEFAULT_RRF_TOP,
    cross_encoder_top: int = 15,
) -> list[tuple[str, str, str]]:
    """5-stage full pipeline、 LLM rerank + fit_label + reasoning 付き final。

    Returns:
        [(id, fit_label "high"|"medium"|"low", reasoning), ...] descending
    """
    items_by_id, text_fn = _items_by_id(side)

    bm25_index = get_companies_bm25() if side == "companies" else get_profiles_bm25()
    bm25_results = bm25_index.search(query, k=candidate_n)
    dense_results = dense_search(query, side=side, k=candidate_n)
    fused = reciprocal_rank_fusion([bm25_results, dense_results], top_k=rrf_top)

    # Stage 4: cross-encoder → cross_encoder_top (LLM の input)
    candidates_for_ce = [
        (item_id, text_fn(items_by_id[item_id]))
        for item_id, _ in fused
        if item_id in items_by_id
    ]
    ce_ranked = cross_encoder_rerank(query, candidates_for_ce, top_k=cross_encoder_top)

    # Stage 5: LLM listwise rerank with CoT + fit_label
    llm_input = [
        (item_id, text_fn(items_by_id[item_id]))
        for item_id, _ in ce_ranked
        if item_id in items_by_id
    ]
    return llm_listwise_rerank(query, llm_input, top_k=top_k)


def _resolve_query_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text

    if args.profile_id:
        profiles = _load_jsonl(SYNTHETIC_DIR / "profiles_op_synthetic.jsonl")
        for p in profiles:
            if p["profile_id"] == args.profile_id:
                return profile_op_to_text(p)
        raise ValueError(f"profile_id 不在: {args.profile_id}")

    if args.company_id:
        companies = _load_jsonl(SYNTHETIC_DIR / "companies_op_synthetic.jsonl")
        for c in companies:
            if c["company_id"] == args.company_id:
                return company_op_to_text(c)
        raise ValueError(f"company_id 不在: {args.company_id}")

    raise ValueError("--text / --profile-id / --company-id のいずれかを指定")


def _print_results(results: list[tuple[str, float]], side: str) -> None:
    items_by_id, _ = _items_by_id(side)
    print(f"\n[top-{len(results)} {side} matches — 4-stage hybrid (BM25 + dense + RRF + cross-encoder)]\n")
    for rank, (item_id, score) in enumerate(results, 1):
        item = items_by_id.get(item_id, {})
        if side == "companies":
            tagline = f"{item.get('industry', '?')} / {item.get('revenue_band', '?')} / {item.get('location_pref', '?')} / 創業者 {item.get('founder_age_band', '?')}"
        else:
            inds = "・".join(item.get("industries", []))
            tagline = f"{inds} / {item.get('age_band', '?')} / {item.get('location_pref', '?')} / 経営 {item.get('executive_years', '?')} 年"
        print(f" {rank:2d}. {item_id} score={score:+.4f} {tagline}")


def main() -> None:
    parser = argparse.ArgumentParser(description="4-stage hybrid matching")
    parser.add_argument("--side", choices=["companies", "profiles"], required=True)
    parser.add_argument("--text", type=str, help="自由 text query")
    parser.add_argument("--profile-id", type=str)
    parser.add_argument("--company-id", type=str)
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    query_text = _resolve_query_text(args)
    results = hybrid_search(query_text, args.side, top_k=args.k)
    _print_results(results, args.side)


if __name__ == "__main__":
    main()
