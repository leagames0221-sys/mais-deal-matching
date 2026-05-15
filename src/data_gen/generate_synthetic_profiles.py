"""Generate synthetic Profile + Company JSONL with PII / Operational split.

Run: python -m src.data_gen.generate_synthetic_profiles

Output (4 file、 ADR-006 PII / Op 分離 schema):
  data/synthetic/profiles_pii_synthetic.jsonl    (vault 側、 暗号化対象)
  data/synthetic/profiles_op_synthetic.jsonl     (operational 側、 仮名加工情報)
  data/synthetic/companies_pii_synthetic.jsonl   (vault 側)
  data/synthetic/companies_op_synthetic.jsonl    (operational 側、 仮名加工情報)

link key = profile_id / company_id (`secrets.token_urlsafe` 同等の不可推測 token)。
embedding pipeline (Week 2) は *_op_*.jsonl のみ literal 読む。

ADR-006 / ADR-007 順守:
  - 年齢 → 年代 band、 詳細住所 → 都道府県 only、 自由 text は Op 側で PII 抜き派生
  - vault 側に raw text + 連絡先 + 詳細住所、 Op に literal 書かない
"""
from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from faker import Faker

load_dotenv()

SEED = int(os.environ.get("SYNTHETIC_SEED", "20260512"))
PROFILE_COUNT = int(os.environ.get("SYNTHETIC_PROFILE_COUNT", "1000"))
COMPANY_COUNT = int(os.environ.get("SYNTHETIC_COMPANY_COUNT", "200"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data")) / "synthetic"

PREFECTURES = [
    "東京都", "大阪府", "京都府", "神奈川県", "愛知県", "兵庫県",
    "福岡県", "北海道", "宮城県", "広島県", "静岡県", "茨城県",
    "千葉県", "埼玉県", "新潟県", "長野県", "岡山県", "熊本県",
]
INDUSTRIES = [
    "出版", "映像制作", "広告", "印刷", "アパレル",
    "食品製造", "外食", "小売", "卸売", "物流",
    "建設", "不動産", "ホテル", "観光", "教育",
    "医療", "介護", "農業", "IT", "コンサルティング",
]
SKILLS_MANAGEMENT = [
    "経営", "事業企画", "M&A", "PMI", "事業承継", "組織改革",
    "財務戦略", "事業再生", "海外展開", "DX 推進",
]
SKILLS_INDUSTRY = [
    "営業統括", "商品開発", "マーケティング", "ブランディング",
    "サプライチェーン", "生産管理", "品質管理", "顧客対応",
    "業界 KOL", "業界団体ネットワーク",
]
SKILLS_FINANCIAL = [
    "投資家ネットワーク", "VC 連携", "PE 連携", "銀行融資交渉",
    "IPO 経験", "上場企業役員経験",
]
PREFERRED_ROLES = ["CEO", "COO", "CFO", "CEO/COO", "代表取締役", "取締役", "顧問"]
CAPITAL_SIZE_BANDS = [
    "小規模 (10 億円未満)", "中堅 (10-50 億円)",
    "中堅 (50-500 億円)", "中堅大手 (500-1000 億円)",
]
REVENUE_BANDS = [
    "3-10 億円", "10-30 億円", "30-50 億円",
    "50-100 億円", "100-300 億円", "300-500 億円",
]
TECHNICAL_ASSETS_BY_INDUSTRY = {
    "出版": ["著者ネットワーク", "編集ノウハウ", "印刷パートナー", "電子書籍配信権"],
    "映像制作": ["制作スタジオ", "監督ネットワーク", "編集 SaaS 内製", "アーカイブ"],
    "広告": ["クライアント graph", "クリエイティブ蓄積", "媒体折衝経験"],
    "印刷": ["印刷工場", "色管理ノウハウ", "デジタル印刷設備"],
    "アパレル": ["素材調達ルート", "縫製パートナー", "EC プラットフォーム"],
    "食品製造": ["HACCP 認証工場", "原料調達ネット", "通販リスト"],
    "外食": ["店舗網", "セントラルキッチン", "FC ノウハウ"],
    "小売": ["店舗網", "POS データ", "EC サイト"],
    "卸売": ["仕入網", "倉庫", "配送網"],
    "物流": ["倉庫", "車両", "ドライバー network"],
    "建設": ["施工実績", "資格保有技術者", "下請ネットワーク"],
    "不動産": ["保有物件", "仲介ネットワーク", "管理 SaaS"],
    "ホテル": ["建物", "予約 system", "リピート顧客"],
    "観光": ["催行実績", "現地ガイド網", "予約 system"],
    "教育": ["教材", "講師網", "受講者 DB"],
    "医療": ["診療実績", "医師スタッフ", "電子カルテ"],
    "介護": ["施設", "介護スタッフ", "ケアプラン蓄積"],
    "農業": ["耕作地", "栽培ノウハウ", "JA 連携"],
    "IT": ["既存システム", "顧客 DB", "GitHub asset", "AWS infra"],
    "コンサルティング": ["クライアント graph", "提案テンプレ", "コンサル人材"],
}


def _age_band(age: int) -> str:
    """exact 年齢 → 10 歳刻み band (仮名加工情報化、 ADR-006)。"""
    lo = (age // 10) * 10
    return f"{lo}-{lo + 9}"


def _redact_pii(text: str, *, name_kana: str = "", phone: str = "", email: str = "") -> str:
    """Presidio 相当の最低限 PII redaction (試作版、 移植時に Presidio 本体採用)。

    Note: 移植段階で Microsoft Presidio (MIT) に置換、 spaCy ja_core_news_md +
    日本固有 recognizer (マイナンバー / 銀行口座 等) を追加。
    """
    out = text
    if name_kana:
        out = out.replace(name_kana, "[NAME]")
    if phone:
        out = out.replace(phone, "[PHONE]")
    if email:
        out = out.replace(email, "[EMAIL]")
    out = re.sub(r"\b0\d{1,4}-?\d{1,4}-?\d{4}\b", "[PHONE]", out)
    out = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "[EMAIL]", out)
    return out


# ─── Profile generators ─────────────────────────────────────────────

def _make_profile_pair(faker: Faker, rng: random.Random, idx: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Profile を PII / Op の 2 dict に literal 分離して返す。"""
    profile_id = f"PROF-{idx:06d}"
    name_kana = faker.kana_name()
    name_full = faker.name()
    age = rng.randint(35, 68)
    industries = rng.sample(INDUSTRIES, k=rng.choice([1, 1, 2]))

    skills = (
        rng.sample(SKILLS_MANAGEMENT, k=rng.randint(1, 3))
        + rng.sample(SKILLS_INDUSTRY, k=rng.randint(1, 3))
    )
    if rng.random() < 0.40:
        skills += rng.sample(SKILLS_FINANCIAL, k=rng.choice([1, 1, 2]))

    executive_years = rng.randint(0, age - 30)
    investor_network = rng.random() < 0.30
    preferred_role = rng.choice(PREFERRED_ROLES)
    preferred_capital_size = rng.choice(CAPITAL_SIZE_BANDS)
    location_pref = rng.choice(PREFERRED_ROLES) if False else rng.choice(PREFECTURES)

    email = faker.email()
    phone = faker.phone_number()
    address_full = faker.address().replace("\n", " ")
    dob_exact = faker.date_of_birth(minimum_age=age, maximum_age=age).isoformat()

    # raw self_intro (PII 含む、 vault 側に格納)
    intro_parts_raw = [
        f"私 {name_kana} は {age} 歳、 {address_full} 在住。",
        f"{ '・'.join(industries) } 業界で {executive_years} 年の経営経験。",
        f"得意は {'、 '.join(skills[:3])} など。",
    ]
    if investor_network:
        intro_parts_raw.append("投資家ネットワーク保有。")
    intro_parts_raw.append(
        f"次は {preferred_role} ポジション、 {preferred_capital_size} 規模の事業承継希望。 連絡先: {email} / {phone}"
    )
    raw_self_intro = " ".join(intro_parts_raw)

    # redacted self_intro (Op 側に格納、 PII redact 済)
    redacted_self_intro = _redact_pii(
        raw_self_intro, name_kana=name_kana, phone=phone, email=email
    )
    # 詳細住所 → 都道府県 only に正規化
    redacted_self_intro = redacted_self_intro.replace(address_full, location_pref)
    # 「{age} 歳」 → 「{age_band}」
    redacted_self_intro = redacted_self_intro.replace(f"{age} 歳", _age_band(age))

    profile_pii = {
        "profile_id": profile_id,
        "name_kana": name_kana,
        "name_full": name_full,
        "email": email,
        "phone": phone,
        "address_full": address_full,
        "dob_exact": dob_exact,
        "raw_self_intro": raw_self_intro,
    }
    profile_op = {
        "profile_id": profile_id,
        "age_band": _age_band(age),
        "location_pref": location_pref,
        "industries": industries,
        "skills": skills,
        "executive_years": executive_years,
        "investor_network": investor_network,
        "preferred_role": preferred_role,
        "preferred_capital_size": preferred_capital_size,
        "redacted_self_intro": redacted_self_intro,
    }
    return profile_pii, profile_op


# ─── Company generators ─────────────────────────────────────────────

def _make_company_pair(faker: Faker, rng: random.Random, idx: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """Company を PII / Op の 2 dict に literal 分離して返す。"""
    company_id = f"COMP-{idx:05d}"
    industry = rng.choice(INDUSTRIES)
    revenue_band = rng.choice(REVENUE_BANDS)
    employee_count = rng.choice([15, 25, 40, 60, 80, 120, 180, 250, 400, 600])
    location_pref = rng.choice(PREFECTURES)
    founder_age = rng.randint(65, 82)

    company_name = f"{faker.company()}"
    address_full = faker.address().replace("\n", " ")
    contact_person = faker.name()
    contact_email = faker.email()
    contact_phone = faker.phone_number()

    base_reqs = ["経営経験", f"{industry}業界知見"]
    if rng.random() < 0.35:
        base_reqs.append("財務戦略")
    if rng.random() < 0.20:
        base_reqs.append("DX 推進")
    successor_requirements = base_reqs

    industry_assets = TECHNICAL_ASSETS_BY_INDUSTRY.get(industry, [])
    asset_count = rng.randint(2, min(4, len(industry_assets)) if industry_assets else 2)
    technical_assets = rng.sample(industry_assets, k=asset_count) if industry_assets else []

    financial_health = rng.choice([
        "黒字", "黒字", "黒字", "黒字", "微減益", "赤字 (再生中)",
    ])

    # raw description (PII 含む、 vault 側)
    raw_description = (
        f"{company_name} ({address_full})、 {industry} 業界。 "
        f"売上 {revenue_band}、 従業員 {employee_count} 名。 "
        f"創業者 {founder_age} 歳、 後継未定。 主要資産は {'、 '.join(technical_assets)}。 "
        f"財務 {financial_health}。 連絡先 {contact_person} ({contact_email} / {contact_phone})。"
    )

    # redacted description (Op 側、 PII redact 済、 仮名加工)
    redacted_description = _redact_pii(
        raw_description.replace(company_name, "[COMPANY]"),
        phone=contact_phone, email=contact_email,
    )
    redacted_description = redacted_description.replace(address_full, location_pref)
    redacted_description = redacted_description.replace(contact_person, "[CONTACT]")
    redacted_description = redacted_description.replace(f"{founder_age} 歳", _age_band(founder_age))

    company_pii = {
        "company_id": company_id,
        "company_name": company_name,
        "address_full": address_full,
        "contact_person": contact_person,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "raw_description": raw_description,
    }
    company_op = {
        "company_id": company_id,
        "industry": industry,
        "revenue_band": revenue_band,
        "employee_count": employee_count,
        "location_pref": location_pref,
        "founder_age_band": _age_band(founder_age),
        "successor_requirements": successor_requirements,
        "technical_assets": technical_assets,
        "financial_health": financial_health,
        "redacted_description": redacted_description,
    }
    return company_pii, company_op


# ─── Orchestrator ───────────────────────────────────────────────────

def generate(
    profile_count: int = PROFILE_COUNT,
    company_count: int = COMPANY_COUNT,
    seed: int = SEED,
    out_dir: Path = DATA_DIR,
) -> dict[str, Path]:
    """4 JSONL を生成、 path dict を返す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    faker = Faker("ja_JP")
    Faker.seed(seed)

    paths = {
        "profiles_pii": out_dir / "profiles_pii_synthetic.jsonl",
        "profiles_op": out_dir / "profiles_op_synthetic.jsonl",
        "companies_pii": out_dir / "companies_pii_synthetic.jsonl",
        "companies_op": out_dir / "companies_op_synthetic.jsonl",
    }

    with paths["profiles_pii"].open("w", encoding="utf-8") as fpii, \
         paths["profiles_op"].open("w", encoding="utf-8") as fop:
        for i in range(1, profile_count + 1):
            pii, op = _make_profile_pair(faker, rng, i)
            fpii.write(json.dumps(pii, ensure_ascii=False) + "\n")
            fop.write(json.dumps(op, ensure_ascii=False) + "\n")

    with paths["companies_pii"].open("w", encoding="utf-8") as fpii, \
         paths["companies_op"].open("w", encoding="utf-8") as fop:
        for i in range(1, company_count + 1):
            pii, op = _make_company_pair(faker, rng, i)
            fpii.write(json.dumps(pii, ensure_ascii=False) + "\n")
            fop.write(json.dumps(op, ensure_ascii=False) + "\n")

    return paths


def main() -> None:
    paths = generate()
    print(f"[OK] {PROFILE_COUNT} profile pairs  -> {paths['profiles_pii'].name} (PII vault) + {paths['profiles_op'].name} (operational)")
    print(f"[OK] {COMPANY_COUNT} company pairs  -> {paths['companies_pii'].name} (PII vault) + {paths['companies_op'].name} (operational)")
    print(f"     seed={SEED} (同 seed = 同出力)")
    print(f"     ADR-006 PII/Op 分離 + ADR-007 Vault Pattern 適用")


if __name__ == "__main__":
    main()
