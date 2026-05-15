"""Week 2 dense baseline vs Week 3a 4-stage hybrid の比較 dogfood。

Run: python -m scripts.dogfood_compare

 5-stage 構成の rationale を literal 実証する用途。
4 query で baseline / hybrid の top-5 を並べて表示。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows console UTF-8 (mojibake 防止)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

from src.embedding.query_index import search as dense_search
from src.embedding.text_builder import company_op_to_text, profile_op_to_text
from src.matching.pipeline import hybrid_search

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _items_by_id(side: str):
    if side == "companies":
        return {it["company_id"]: it for it in _load_jsonl(SYNTHETIC_DIR / "companies_op_synthetic.jsonl")}
    return {it["profile_id"]: it for it in _load_jsonl(SYNTHETIC_DIR / "profiles_op_synthetic.jsonl")}


def _format(item_id: str, score: float, item: dict, side: str) -> str:
    if side == "companies":
        tag = f"{item.get('industry', '?')} / {item.get('revenue_band', '?')} / {item.get('location_pref', '?')}"
    else:
        inds = "・".join(item.get("industries", []))
        tag = f"{inds} / {item.get('age_band', '?')} / {item.get('location_pref', '?')} / 経営 {item.get('executive_years', '?')} 年"
    return f" {item_id} score={score:+.4f} {tag}"


def compare(query_text: str, query_label: str, side: str, k: int = 5) -> None:
    print(f"\n{'='*78}\nQuery: {query_label}\n{'='*78}")
    items_by_id = _items_by_id(side)

    print(f"\n[A] Week 2 baseline (dense only / e5-large + FAISS)")
    base = dense_search(query_text, side=side, k=k)
    for cid, score in base:
        print(_format(cid, score, items_by_id.get(cid, {}), side))

    print(f"\n[B] Week 3a hybrid (BM25 + dense + RRF + cross-encoder)")
    hybr = hybrid_search(query_text, side=side, top_k=k)
    for cid, score in hybr:
        print(_format(cid, score, items_by_id.get(cid, {}), side))


def main() -> None:
    # Q1: PROF-000001 (食品製造/60-69/千葉県) → companies
    profiles = _load_jsonl(SYNTHETIC_DIR / "profiles_op_synthetic.jsonl")
    p1 = next(p for p in profiles if p["profile_id"] == "PROF-000001")
    compare(profile_op_to_text(p1), f"PROF-000001 ({'・'.join(p1['industries'])}/{p1['age_band']}/{p1['location_pref']}) → companies", "companies")

    # Q2 / Q3: text query → companies
    compare("IT 業界 経営経験 投資家ネットワーク CEO 希望", "text 'IT 経営 投資家' → companies", "companies")
    compare("出版業 後継 関西 経営経験 20 年 黒字", "text '出版 後継 関西' → companies", "companies")

    # Q4: COMP-00001 → profiles (逆方向)
    companies = _load_jsonl(SYNTHETIC_DIR / "companies_op_synthetic.jsonl")
    c1 = next(c for c in companies if c["company_id"] == "COMP-00001")
    compare(company_op_to_text(c1), f"COMP-00001 ({c1['industry']}/{c1['revenue_band']}/{c1['location_pref']}) → profiles", "profiles")


if __name__ == "__main__":
    main()
