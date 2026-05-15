"""sentence-transformers wrapper with asymmetric (query / passage) convention.

multilingual-e5 系 model は "query: " / "passage: " prefix が必須 (asymmetric)。
HuggingFace 公式 example の encode_query / encode_document pattern を自作 code で
literal 再現。
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

DEFAULT_MODEL = os.environ.get("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")


@lru_cache(maxsize=2)
def _get_model(name: str = DEFAULT_MODEL) -> SentenceTransformer:
    """model 初回 load を cache (multi-process / multi-call で重複 load 回避)。"""
    return SentenceTransformer(name)


def encode_documents(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """corpus 側 (= passage)、 e5 prefix "passage: " 付与 + L2 normalize。"""
    model = _get_model(model_name)
    prefixed = [f"passage: {t}" for t in texts]
    embeddings = model.encode(
        prefixed,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.astype("float32")


def encode_queries(
    texts: list[str],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """query 側、 e5 prefix "query: " 付与 + L2 normalize。"""
    model = _get_model(model_name)
    prefixed = [f"query: {t}" for t in texts]
    embeddings = model.encode(
        prefixed,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.astype("float32")
