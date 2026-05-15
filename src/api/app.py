"""FastAPI app — マイページ + マッチング demo UI (ADR-003 / ADR-005 / ADR-006 / ADR-007 統合)。

Run: uvicorn src.api.app:app --reload --port 8000

Routes:
  GET  /                   landing page (provider 選択 + 説明)
  POST /mock-signin        Mock OAuth: profile_id で session 開始
  GET  /mypage             マイページ: 自分の Profile (Op fields) 表示
  GET  /match              マッチング: 自分にマッチする Company top-K
  POST /intro/{company_id} 紹介リクエスト (vault join、 audit 記録)
  GET  /audit-log          access audit log (admin / 透明性 demo 用)

PII boundary 厳守: マイページ default = Op fields のみ表示、 PII vault は
intro 承認 / 自分の編集 経由のみ access (全 access が audit log に literal 記録)。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.auth.session import SESSION_SECRET, is_provider_configured, mock_signin
from src.embedding.text_builder import company_op_to_text, profile_op_to_text
from src.matching.pipeline import hybrid_search_with_reasoning
from src.operational.store import (
    get_company_op,
    get_profile_op,
    list_company_ops,
    list_profile_ops,
)
from src.vault.store import emit_audit, get_company_pii, get_profile_pii

load_dotenv()

APP_DIR = Path(__file__).parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="MAIS — 事業承継マッチング (PoC)")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=3600)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


# ─── helpers ───────────────────────────────────────────────────────

def _current_profile_id(request: Request) -> str:
    pid = request.session.get("profile_id")
    if not pid:
        raise HTTPException(status_code=401, detail="未ログイン (/ から mock-signin してください)")
    return pid


def _current_company_id(request: Request) -> str:
    cid = request.session.get("company_id")
    if not cid:
        raise HTTPException(status_code=401, detail="未ログイン (/ から 企業として登録 してください)")
    return cid


# ─── routes ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    """landing: provider 選択 + 既存合成 profile / company 一覧 (PoC demo 用、 移植時に削除)。"""
    samples = list_profile_ops(limit=10)
    company_samples = list_company_ops(limit=10)
    providers = {
        "google": is_provider_configured("google"),
        "linkedin": is_provider_configured("linkedin"),
    }
    return templates.TemplateResponse(
        request,
        "landing.html",
        {
            "samples": samples,
            "company_samples": company_samples,
            "providers": providers,
            "current_profile_id": request.session.get("profile_id"),
            "current_company_id": request.session.get("company_id"),
        },
    )


@app.post("/mock-signin")
def post_mock_signin(request: Request, profile_id: str = Form(...)):
    """Mock OAuth: 既存合成 profile_id で session 開始 (PoC demo 専用)。"""
    if not get_profile_op(profile_id):
        raise HTTPException(404, f"profile_id 不在: {profile_id}")
    session_info = mock_signin(profile_id)
    request.session.clear()  # company session があれば clear (一人 = 一 account 前提)
    request.session["profile_id"] = session_info["profile_id"]
    request.session["provider"] = session_info["provider"]
    emit_audit("SIGNIN", profile_id, "mock_signin", f"session {session_info['session_id']}")
    return RedirectResponse("/mypage", status_code=303)


@app.post("/signout")
def post_signout(request: Request):
    pid = request.session.get("profile_id")
    cid = request.session.get("company_id")
    request.session.clear()
    if pid:
        emit_audit("SIGNOUT", pid, "session", "user signout (profile side)")
    if cid:
        emit_audit("SIGNOUT", cid, "session", "user signout (company side)")
    return RedirectResponse("/", status_code=303)


@app.post("/mock-signin-company")
def post_mock_signin_company(request: Request, company_id: str = Form(...)):
    """Mock OAuth (企業側): 既存合成 company_id で session 開始 (PoC demo 専用)。"""
    if not get_company_op(company_id):
        raise HTTPException(404, f"company_id 不在: {company_id}")
    request.session.clear()  # profile session があれば clear (一人 = 一 account 前提)
    request.session["company_id"] = company_id
    request.session["provider"] = "mock"
    emit_audit("SIGNIN", company_id, "mock_signin_company", "company side session start")
    return RedirectResponse("/company/mypage", status_code=303)


@app.get("/mypage", response_class=HTMLResponse)
def mypage(request: Request):
    """マイページ: 自分の Op fields 表示 (default)、 PII は 「show pii」 で access (audit 記録)。"""
    pid = _current_profile_id(request)
    op = get_profile_op(pid)
    if not op:
        raise HTTPException(404, "profile_op 不在")

    show_pii = request.query_params.get("show_pii") == "1"
    pii = None
    if show_pii:
        pii = get_profile_pii(pid, requester=f"self:{pid}", reason="マイページ self view")

    return templates.TemplateResponse(
        request, "mypage.html",
        {"op": op, "pii": pii, "profile_id": pid},
    )


@app.get("/match", response_class=HTMLResponse)
def match(request: Request):
    """5-stage hybrid pipeline で自分にマッチする企業 top-5 + fit 理由 (CoT)。"""
    pid = _current_profile_id(request)
    op = get_profile_op(pid)
    if not op:
        raise HTTPException(404, "profile_op 不在")

    query_text = profile_op_to_text(op)
    results = hybrid_search_with_reasoning(query_text, side="companies", top_k=5)

    enriched = []
    for cid, fit_label, reasoning in results:
        c_op = get_company_op(cid)
        enriched.append({
            "company_id": cid,
            "fit_label": fit_label,
            "reasoning": reasoning,
            "industry": c_op.get("industry") if c_op else "?",
            "revenue_band": c_op.get("revenue_band") if c_op else "?",
            "location_pref": c_op.get("location_pref") if c_op else "?",
            "founder_age_band": c_op.get("founder_age_band") if c_op else "?",
        })

    return templates.TemplateResponse(
        request, "match.html",
        {"results": enriched, "profile_id": pid},
    )


@app.post("/intro/{company_id}", response_class=HTMLResponse)
def intro(request: Request, company_id: str):
    """紹介リクエスト: PII vault を join (MAIS 営業向け full info)、 audit literal 記録。"""
    pid = _current_profile_id(request)
    c_pii = get_company_pii(company_id, requester=f"intro_by:{pid}", reason="紹介リクエスト承認 flow")
    if not c_pii:
        raise HTTPException(404, f"company_id 不在: {company_id}")
    c_op = get_company_op(company_id)

    return templates.TemplateResponse(
        request, "intro.html",
        {"company_id": company_id, "pii": c_pii, "op": c_op, "profile_id": pid},
    )


@app.get("/company/mypage", response_class=HTMLResponse)
def company_mypage(request: Request):
    """企業マイページ: 自社 Op fields default、 PII vault は 「show pii」 で access (audit 記録)。"""
    cid = _current_company_id(request)
    op = get_company_op(cid)
    if not op:
        raise HTTPException(404, "company_op 不在")

    show_pii = request.query_params.get("show_pii") == "1"
    pii = None
    if show_pii:
        pii = get_company_pii(cid, requester=f"self:{cid}", reason="企業マイページ self view")

    return templates.TemplateResponse(
        request, "company_mypage.html",
        {"op": op, "pii": pii, "company_id": cid},
    )


@app.get("/company/match", response_class=HTMLResponse)
def company_match(request: Request):
    """5-stage hybrid pipeline で自社にマッチする後継候補 top-5 + fit 理由 (CoT)。"""
    cid = _current_company_id(request)
    op = get_company_op(cid)
    if not op:
        raise HTTPException(404, "company_op 不在")

    query_text = company_op_to_text(op)
    results = hybrid_search_with_reasoning(query_text, side="profiles", top_k=5)

    enriched = []
    for pid, fit_label, reasoning in results:
        p_op = get_profile_op(pid)
        enriched.append({
            "profile_id": pid,
            "fit_label": fit_label,
            "reasoning": reasoning,
            "industries": p_op.get("industries", []) if p_op else [],
            "age_band": p_op.get("age_band") if p_op else "?",
            "location_pref": p_op.get("location_pref") if p_op else "?",
            "executive_years": p_op.get("executive_years") if p_op else "?",
            "preferred_role": p_op.get("preferred_role") if p_op else "?",
        })

    return templates.TemplateResponse(
        request, "company_match.html",
        {"results": enriched, "company_id": cid},
    )


@app.post("/company/intro/{profile_id}", response_class=HTMLResponse)
def company_intro(request: Request, profile_id: str):
    """紹介リクエスト (企業 → 後継候補): PII vault join + audit literal 記録。"""
    cid = _current_company_id(request)
    p_pii = get_profile_pii(profile_id, requester=f"intro_by_company:{cid}", reason="企業発信 紹介リクエスト承認 flow")
    if not p_pii:
        raise HTTPException(404, f"profile_id 不在: {profile_id}")
    p_op = get_profile_op(profile_id)

    return templates.TemplateResponse(
        request, "company_intro.html",
        {"profile_id": profile_id, "pii": p_pii, "op": p_op, "company_id": cid},
    )


@app.get("/audit-log", response_class=HTMLResponse)
def audit_log(request: Request):
    """audit log 表示 (透明性 demo 用、 移植時 admin/RBAC 制御)。"""
    import json
    from src.vault.store import AUDIT_LOG_PATH

    entries = []
    if AUDIT_LOG_PATH.exists():
        for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()[-50:]:
            if line.strip():
                entries.append(json.loads(line))
    entries.reverse()  # 最新順

    return templates.TemplateResponse(
        request, "audit.html",
        {"entries": entries},
    )


@app.get("/health")
def health():
    return {"status": "ok"}
