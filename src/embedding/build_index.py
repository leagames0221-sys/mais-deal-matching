"""Build FAISS index for Profiles + Companies (two-sided embedding、 ADR-002 / ADR-003).

Run: python -m src.embedding.build_index

Output:
  data/cache/profiles.index     (FAISS IndexFlatIP、 inner-product = cosine on normalized)
  data/cache/profiles_ids.npy   (profile_id 順序、 index row → profile_id mapping)
  data/cache/companies.index
  data/cache/companies_ids.npy

両 index は L2-normalize 済 embedding を IndexFlatIP に格納、 inner product で cosine 同等。
IRS2021 paper の two-sided embedding 思想 + HuggingFace 公式 example の正規化 + FAISS pattern を
自作 code に落とし込む (ADR-002 「盗んで真似て、 自作」)。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import faiss
import numpy as np
from dotenv import load_dotenv

from src.embedding.encoder import encode_documents
from src.embedding.text_builder import company_op_to_text, profile_op_to_text

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"
CACHE_DIR = DATA_DIR / "cache"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _build_one(
    items: list[dict],
    text_fn,
    id_key: str,
    out_index_path: Path,
    out_ids_path: Path,
) -> tuple[int, float, int]:
    """1 type 分の index 構築。 returns (件数, 経過秒, 次元数)。"""
    t0 = time.time()
    texts = [text_fn(it) for it in items]
    ids = [it[id_key] for it in items]

    embeddings = encode_documents(texts)
    dim = embeddings.shape[1]

    # IndexFlatIP = inner product、 normalize 済 embedding と組み合わせて cosine と等価
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)

    out_index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(out_index_path))
    np.save(out_ids_path, np.array(ids, dtype=object), allow_pickle=True)

    return len(items), time.time() - t0, dim


def build_all() -> None:
    # ADR-006: embedding pipeline は operational side のみ literal 読む (vault は触らない)
    profiles_path = SYNTHETIC_DIR / "profiles_op_synthetic.jsonl"
    companies_path = SYNTHETIC_DIR / "companies_op_synthetic.jsonl"
    profiles_op = _load_jsonl(profiles_path)
    companies_op = _load_jsonl(companies_path)

    print(f"[INFO] loading {len(profiles_op)} profile_op + {len(companies_op)} company_op (operational only, PII vault untouched)...")

    n_p, t_p, dim_p = _build_one(
        profiles_op,
        profile_op_to_text,
        "profile_id",
        CACHE_DIR / "profiles.index",
        CACHE_DIR / "profiles_ids.npy",
    )
    print(f"[OK] profiles  index: {n_p} items / {dim_p} dim / {t_p:.1f}s -> {CACHE_DIR / 'profiles.index'}")

    n_c, t_c, dim_c = _build_one(
        companies_op,
        company_op_to_text,
        "company_id",
        CACHE_DIR / "companies.index",
        CACHE_DIR / "companies_ids.npy",
    )
    print(f"[OK] companies index: {n_c} items / {dim_c} dim / {t_c:.1f}s -> {CACHE_DIR / 'companies.index'}")


def main() -> None:
    build_all()


if __name__ == "__main__":
    main()
