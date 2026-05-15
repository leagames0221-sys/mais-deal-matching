"""Query FAISS index for top-K similar items (asymmetric search).

Usage examples:
  # Profile (会員) が自分にマッチする Company を探す
  python -m src.embedding.query_index --side companies --profile-id PROF-000001 -k 5

  # 自由 text で companies / profiles 検索
  python -m src.embedding.query_index --side companies --text "出版 後継 関西 50億規模" -k 10
  python -m src.embedding.query_index --side profiles --text "経営経験 20年 投資家 IT" -k 10

 = 会員が自分の Profile / Company を保有、 マイページから検索を起動する想定。
side = "companies" / "profiles" で検索対象 corpus を切替。
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv

from src.embedding.encoder import encode_queries
from src.embedding.text_builder import company_op_to_text, profile_op_to_text

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"
CACHE_DIR = DATA_DIR / "cache"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_index(side: str) -> tuple[faiss.Index, np.ndarray]:
    if side == "companies":
        index_path = CACHE_DIR / "companies.index"
        ids_path = CACHE_DIR / "companies_ids.npy"
    elif side == "profiles":
        index_path = CACHE_DIR / "profiles.index"
        ids_path = CACHE_DIR / "profiles_ids.npy"
    else:
        raise ValueError(f"side must be 'companies' or 'profiles', got {side!r}")

    if not index_path.exists():
        raise FileNotFoundError(f"index 未構築: {index_path}。先に `python -m src.embedding.build_index` を実行")

    index = faiss.read_index(str(index_path))
    ids = np.load(ids_path, allow_pickle=True)
    return index, ids


def _resolve_query_text(args: argparse.Namespace) -> str:
    """--text / --profile-id / --company-id のどれかから query text を構築。"""
    if args.text:
        return args.text

    # : operational only、 PII vault は読まない
    if args.profile_id:
        profiles_op = _load_jsonl(SYNTHETIC_DIR / "profiles_op_synthetic.jsonl")
        for p in profiles_op:
            if p["profile_id"] == args.profile_id:
                return profile_op_to_text(p)
        raise ValueError(f"profile_id 不在: {args.profile_id}")

    if args.company_id:
        companies_op = _load_jsonl(SYNTHETIC_DIR / "companies_op_synthetic.jsonl")
        for c in companies_op:
            if c["company_id"] == args.company_id:
                return company_op_to_text(c)
        raise ValueError(f"company_id 不在: {args.company_id}")

    raise ValueError("--text / --profile-id / --company-id のいずれかを指定")


def search(
    query_text: str,
    side: str,
    k: int = 5,
) -> list[tuple[str, float]]:
    """query_text → top-K 一致候補、 返り値 = [(item_id, cosine_score), ...]。"""
    index, ids = _load_index(side)
    query_vec = encode_queries([query_text])
    scores, indices = index.search(query_vec, k)

    return [
        (str(ids[idx]), float(score))
        for idx, score in zip(indices[0], scores[0])
        if idx >= 0
    ]


def _print_results(results: list[tuple[str, float]], side: str) -> None:
    """top-K を人が読める形で表示 (dogfood 用、 operational only)。"""
    if side == "companies":
        items_path = SYNTHETIC_DIR / "companies_op_synthetic.jsonl"
        id_key = "company_id"
    else:
        items_path = SYNTHETIC_DIR / "profiles_op_synthetic.jsonl"
        id_key = "profile_id"

    items_by_id = {it[id_key]: it for it in _load_jsonl(items_path)}

    print(f"\n[top-{len(results)} {side} matches (operational only, PII vault untouched)]\n")
    for rank, (item_id, score) in enumerate(results, 1):
        item = items_by_id.get(item_id, {})
        if side == "companies":
            tagline = f"{item.get('industry', '?')} / {item.get('revenue_band', '?')} / {item.get('location_pref', '?')} / 創業者 {item.get('founder_age_band', '?')}"
        else:
            inds = "・".join(item.get("industries", []))
            tagline = f"{inds} / {item.get('age_band', '?')} / {item.get('location_pref', '?')} / 経営 {item.get('executive_years', '?')} 年"
        print(f" {rank:2d}. {item_id} score={score:.4f} {tagline}")


def main() -> None:
    parser = argparse.ArgumentParser(description="mais-deal-matching: FAISS top-K query")
    parser.add_argument("--side", choices=["companies", "profiles"], required=True,
                        help="検索対象 corpus")
    parser.add_argument("--text", type=str, help="自由 text query")
    parser.add_argument("--profile-id", type=str, help="既存 profile id を query 化")
    parser.add_argument("--company-id", type=str, help="既存 company id を query 化")
    parser.add_argument("-k", type=int, default=5, help="top-K (default=5)")
    args = parser.parse_args()

    query_text = _resolve_query_text(args)
    results = search(query_text, args.side, args.k)
    _print_results(results, args.side)


if __name__ == "__main__":
    main()
