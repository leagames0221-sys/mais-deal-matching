"""Serialize ProfileOp / CompanyOp dict → embedding-input text (operational only).

ADR-006 順守: embedding pipeline は operational 側のみ literal 読む、 PII vault は触らない。
field 順序固定で再現性確保 (ADR-002 → ADR-005 の HuggingFace asymmetric pattern を継承)。
"""
from __future__ import annotations

from typing import Any


def profile_op_to_text(profile_op: dict[str, Any]) -> str:
    """ProfileOp (後継候補、 仮名加工情報) → embedding-input text。 field 順序固定。"""
    industries = "・".join(profile_op.get("industries", []))
    skills = "・".join(profile_op.get("skills", []))
    investor_note = "投資家ネットワーク保有。 " if profile_op.get("investor_network") else ""

    return (
        f"[業界] {industries} "
        f"[役職希望] {profile_op.get('preferred_role', '')} "
        f"[企業規模希望] {profile_op.get('preferred_capital_size', '')} "
        f"[経営経験年数] {profile_op.get('executive_years', 0)} 年 "
        f"[skill] {skills} "
        f"[地域] {profile_op.get('location_pref', '')} "
        f"[年代] {profile_op.get('age_band', '')} "
        f"{investor_note}"
        f"[自己紹介] {profile_op.get('redacted_self_intro', '')}"
    )


def company_op_to_text(company_op: dict[str, Any]) -> str:
    """CompanyOp (後継不在企業、 仮名加工情報) → embedding-input text。 field 順序固定。"""
    successor_reqs = "・".join(company_op.get("successor_requirements", []))
    technical_assets = "・".join(company_op.get("technical_assets", []))

    return (
        f"[業界] {company_op.get('industry', '')} "
        f"[後継要件] {successor_reqs} "
        f"[売上規模] {company_op.get('revenue_band', '')} "
        f"[従業員数] {company_op.get('employee_count', 0)} 名 "
        f"[技術資産] {technical_assets} "
        f"[地域] {company_op.get('location_pref', '')} "
        f"[創業者年代] {company_op.get('founder_age_band', '')} "
        f"[財務] {company_op.get('financial_health', '')} "
        f"[企業概要] {company_op.get('redacted_description', '')}"
    )
