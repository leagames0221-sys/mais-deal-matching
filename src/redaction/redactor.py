"""PII redaction (Presidio integration hook、 ADR-007 layer 4 仮名加工)。

PoC 試作 = regex-based (氏名 / 電話 / email / 詳細住所)、 既存 data_gen の redaction
ロジックを module 化、 マイページ self-edit 時の入力 sanitize に使う。

移植 phase = Microsoft Presidio (MIT) に literal swap、 spaCy ja_core_news_md +
業界特化 recognizer (マイナンバー / 銀行口座 / クレカ / 保険証 等) 追加。
"""
from __future__ import annotations

import re

_PHONE_RE = re.compile(r"\b0\d{1,4}-?\d{1,4}-?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_POSTAL_RE = re.compile(r"\b\d{3}-?\d{4}\b")
# 簡易日本住所 (都道府県 + 市区町村 + 番地、 移植時 Presidio に置換)
_ADDRESS_RE = re.compile(
    r"[一-鿿々]+(?:都|道|府|県)[一-鿿々ぁ-んァ-ヶー]+(?:市|区|町|村)[一-鿿々ぁ-んァ-ヶー\d\- 　]+"
)


def redact(
    text: str,
    *,
    name_kana: str = "",
    name_full: str = "",
    phone: str = "",
    email: str = "",
    address_full: str = "",
) -> str:
    """text 内 PII を redact、 戻り値 = 仮名加工情報 ready。

    既知 PII (name / phone / email / address) を最優先で literal replace、
    残余を regex で 2 次 sweep (誤検知の取りこぼし防御)。
    """
    out = text
    for name in (name_full, name_kana):
        if name and name in out:
            out = out.replace(name, "[NAME]")
    if phone and phone in out:
        out = out.replace(phone, "[PHONE]")
    if email and email in out:
        out = out.replace(email, "[EMAIL]")
    if address_full and address_full in out:
        out = out.replace(address_full, "[ADDRESS]")

    # 2 次 sweep: regex で残存 PII を検出 / mask
    out = _PHONE_RE.sub("[PHONE]", out)
    out = _EMAIL_RE.sub("[EMAIL]", out)
    out = _POSTAL_RE.sub("[POSTAL]", out)
    out = _ADDRESS_RE.sub("[ADDRESS]", out)

    return out


def age_to_band(age: int) -> str:
    """exact 年齢 → 10 歳刻み band (仮名加工情報、 ADR-006)。"""
    lo = (age // 10) * 10
    return f"{lo}-{lo + 9}"
