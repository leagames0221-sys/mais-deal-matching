"""Operational DB: 仮名加工情報 (PII redact 済) を JSONL で保管。

embedding / matching engine が literal 読む唯一の data source。 vault と link は
profile_id / company_id のみ。 漏洩しても仮名加工情報 = 個人情報保護法 2026
改正方針で報告義務 ZERO。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
OP_DIR = DATA_DIR / "synthetic" # 試作 phase = 合成データ dir、 移植 phase で別 path


def _op_file(table: str) -> Path:
    """table → operational JSONL path。"""
    if table == "profile_op":
        return OP_DIR / "profiles_op_synthetic.jsonl"
    if table == "company_op":
        return OP_DIR / "companies_op_synthetic.jsonl"
    raise ValueError(f"unknown table: {table!r}")


def _load_all(table: str) -> dict[str, dict[str, Any]]:
    path = _op_file(table)
    if not path.exists():
        return {}
    out = {}
    id_key = "profile_id" if "profile" in table else "company_id"
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec[id_key]] = rec
    return out


def _save_all(table: str, records: dict[str, dict[str, Any]]) -> None:
    path = _op_file(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(rec, ensure_ascii=False) for rec in records.values()),
        encoding="utf-8",
    )


# ─── public API (audit 不要、 仮名加工情報層) ──────────────────────

def get_profile_op(profile_id: str) -> dict[str, Any] | None:
    return _load_all("profile_op").get(profile_id)


def list_profile_ops(limit: int | None = None) -> list[dict[str, Any]]:
    items = list(_load_all("profile_op").values())
    return items[:limit] if limit else items


def put_profile_op(record: dict[str, Any]) -> None:
    records = _load_all("profile_op")
    records[record["profile_id"]] = record
    _save_all("profile_op", records)


def get_company_op(company_id: str) -> dict[str, Any] | None:
    return _load_all("company_op").get(company_id)


def list_company_ops(limit: int | None = None) -> list[dict[str, Any]]:
    items = list(_load_all("company_op").values())
    return items[:limit] if limit else items


def put_company_op(record: dict[str, Any]) -> None:
    records = _load_all("company_op")
    records[record["company_id"]] = record
    _save_all("company_op", records)
