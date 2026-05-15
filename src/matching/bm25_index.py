"""Stage 1: BM25 sparse lexical retrieval。

BM25 = exact lexical 重視、 dense embedding (Stage 2) が捉えにくい
業界名 / skill 名 / 地域名 の 「字面一致」 を強める。 RRF (Stage 3) で
dense と fuse することで lexical + semantic の両立を達成。

Reference: dorianbrown/rank_BM25、
Python tokenization は単純空白分割 + Japanese: text_builder で句読点 /
記号でも分割される構造前提 (将来 sudachi 等の本格 tokenizer に置換可能)。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from rank_bm25 import BM25Okapi

from src.embedding.text_builder import company_op_to_text, profile_op_to_text

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
SYNTHETIC_DIR = DATA_DIR / "synthetic"

# 日本語 + ASCII の単純 tokenizer (空白 / 記号 / 句読点 で分割)
# 将来 sudachi / mecab に置換可能、 PoC 段階では汎用性優先
_SPLIT_RE = re.compile(r"[\s　\[\]【】・、。/／｜|()（）「」『』:：;；]+")


def tokenize(text: str) -> list[str]:
    """日本語 text → token list (汎用 split)。"""
    tokens = [t for t in _SPLIT_RE.split(text) if t]
    return tokens


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ─── module-level BM25 index cache ─────────────────────────────────
# 再構築 cost: 1,200 件で ~1 秒 / 41 万件で 30-60 秒。 query 毎 rebuild は
# production literal unusable、 module-level cache で 起動時 1 回のみ build。
# data 更新時は invalidate_cache() で literal 再 build trigger。

_PROFILES_CACHE: "BM25Side | None" = None
_COMPANIES_CACHE: "BM25Side | None" = None


class BM25Side:
    """profiles_op or companies_op の片側 BM25 index。

    : operational only 読込。 vault は触らない。
    """

    def __init__(self, items: list[dict[str, Any]], text_fn, id_key: str) -> None:
        self.items = items
        self.ids = [it[id_key] for it in items]
        self.texts = [text_fn(it) for it in items]
        self.tokenized = [tokenize(t) for t in self.texts]
        self.bm25 = BM25Okapi(self.tokenized)

    def search(self, query: str, k: int = 10) -> list[tuple[str, float]]:
        q_tokens = tokenize(query)
        scores = self.bm25.get_scores(q_tokens)
        # numpy argsort で top-k 抽出
        top_k_idx = scores.argsort()[::-1][:k]
        return [(self.ids[i], float(scores[i])) for i in top_k_idx]


def build_profiles_bm25() -> BM25Side:
    """profile_op corpus から BM25 index 構築 (cache されない version、 test 用)。"""
    items = _load_jsonl(SYNTHETIC_DIR / "profiles_op_synthetic.jsonl")
    return BM25Side(items, profile_op_to_text, "profile_id")


def build_companies_bm25() -> BM25Side:
    """company_op corpus から BM25 index 構築 (cache されない version、 test 用)。"""
    items = _load_jsonl(SYNTHETIC_DIR / "companies_op_synthetic.jsonl")
    return BM25Side(items, company_op_to_text, "company_id")


def get_profiles_bm25() -> BM25Side:
    """profile_op BM25 index を取得、 初回 build / 以降 cache 返却。 production-ready。"""
    global _PROFILES_CACHE
    if _PROFILES_CACHE is None:
        _PROFILES_CACHE = build_profiles_bm25()
    return _PROFILES_CACHE


def get_companies_bm25() -> BM25Side:
    """company_op BM25 index を取得、 初回 build / 以降 cache 返却。"""
    global _COMPANIES_CACHE
    if _COMPANIES_CACHE is None:
        _COMPANIES_CACHE = build_companies_bm25()
    return _COMPANIES_CACHE


def invalidate_cache() -> None:
    """data 更新時に cache 無効化 (Op JSONL を re-write した後に call)。"""
    global _PROFILES_CACHE, _COMPANIES_CACHE
    _PROFILES_CACHE = None
    _COMPANIES_CACHE = None
