"""E2E smoke test — MAIS 動画作成前の最終確認 (doctrine: client-no-recovery 順守、 ★★★ verify)。

live uvicorn (default http://127.0.0.1:8000) に対して 16 step walkthrough を literal 実行、
全 endpoint の動作 + content + audit log + 5-stage AI を verify。

Run:
    python -m scripts.e2e_smoke
    # or against tunnel:
    BASE_URL=https://luggage-fully-commented-publisher.trycloudflare.com python -m scripts.e2e_smoke

exit code: 0 = 全 PASS、 1 = いずれか FAIL。
"""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = httpx.Timeout(60.0) # /match は 5-stage で重い (cross-encoder + LLM)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    sym = "[OK]" if ok else "[FAIL]"
    results.append((name, ok, detail))
    print(f"{sym} {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print(f"=== MAIS E2E smoke (target: {BASE}) ===\n")

    # 1. /health
    r = httpx.get(f"{BASE}/health", timeout=TIMEOUT)
    check("01. GET /health", r.status_code == 200 and r.json() == {"status": "ok"}, f"status={r.status_code}")

    # 2. / landing (two-sided)
    r = httpx.get(f"{BASE}/", timeout=TIMEOUT)
    ok = (
        r.status_code == 200
        and "MAIS" in r.text
        and "経営の責務を" in r.text
        and "PROF-000001" in r.text
        and "COMP-00001" in r.text
        and "後継候補として登録" in r.text
        and "企業として登録" in r.text
    )
    check("02. GET / (landing two-sided + brand + both samples)", ok, f"{len(r.text)} chars")

    # 3. /static/hero-rings.svg (年輪 brand asset)
    r = httpx.get(f"{BASE}/static/hero-rings.svg", timeout=TIMEOUT)
    check(
        "03. GET /static/hero-rings.svg",
        r.status_code == 200 and r.text.startswith("<?xml") and "treeRings" not in r.text and "c9a227" in r.text,
        f"{len(r.text)} bytes (gold stroke present)",
    )

    # 4-10: 後継候補 (profile) side flow
    print("\n--- Profile side flow (後継候補) ---")
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        # 4. POST /mock-signin
        r = client.post("/mock-signin", data={"profile_id": "PROF-000001"}, follow_redirects=False)
        check(
            "04. POST /mock-signin (PROF-000001)",
            r.status_code == 303 and r.headers.get("location") == "/mypage",
            f"redirect={r.headers.get('location')}",
        )

        # 5. /mypage (op default)
        r = client.get("/mypage")
        ok = (
            r.status_code == 200
            and "公開情報 (仮名加工)" in r.text
            and "個人情報 vault (暗号化保管中)" in r.text
            and "食品製造" in r.text # PROF-000001 = 食品製造
            and "千葉県" in r.text # 千葉県 在住
        )
        check("05. GET /mypage (op default + 食品製造/千葉県)", ok)

        # 6. /mypage?show_pii=1 (vault decrypt + audit)
        r = client.get("/mypage?show_pii=1")
        ok = (
            r.status_code == 200
            and "個人情報 vault (一時表示中)" in r.text
            and "氏名 (カナ)" in r.text
        )
        check("06. GET /mypage?show_pii=1 (vault decrypt)", ok)

        # 7. /match (5-stage hybrid pipeline、 重い)
        print(" /match 実行中 (5-stage pipeline、 ~5-15 秒)...")
        t0 = time.time()
        r = client.get("/match")
        elapsed = time.time() - t0
        ok = (
            r.status_code == 200
            and "AI 判定理由" in r.text
            and "fit:" in r.text
            and "AI 判定ロジック" in r.text
            and r.text.count("COMP-") >= 5 # top-5 候補
        )
        check(f"07. GET /match (5-stage AI, {elapsed:.1f}s)", ok, f"COMP- 出現 {r.text.count('COMP-')} 回")

        # 8. POST /intro/COMP-00001 (vault join + audit)
        r = client.post("/intro/COMP-00001", follow_redirects=False)
        ok = (
            r.status_code == 200
            and "個人情報 vault への access が発生しました" in r.text
            and "社名" in r.text
        )
        check("08. POST /intro/COMP-00001 (vault join)", ok)

        # 9. /audit-log (SIGNIN + GET + 等 literal 記録確認)
        r = client.get("/audit-log")
        ok = (
            r.status_code == 200
            and "SIGNIN" in r.text
            and "PROF-000001" in r.text
            and "COMP-00001" in r.text # intro 経由で出現
            and "監査ログが重要か" in r.text # rebrand 後 copy
        )
        check("09. GET /audit-log (profile session events)", ok)

        # 10. POST /signout
        r = client.post("/signout", follow_redirects=False)
        check(
            "10. POST /signout (profile)",
            r.status_code == 303 and r.headers.get("location") == "/",
        )

    # 11-16: 企業 (company) side flow
    print("\n--- Company side flow (企業) ---")
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        # 11. POST /mock-signin-company
        r = client.post("/mock-signin-company", data={"company_id": "COMP-00001"}, follow_redirects=False)
        check(
            "11. POST /mock-signin-company (COMP-00001)",
            r.status_code == 303 and r.headers.get("location") == "/company/mypage",
            f"redirect={r.headers.get('location')}",
        )

        # 12. /company/mypage (op default)
        r = client.get("/company/mypage")
        ok = (
            r.status_code == 200
            and "公開情報 (仮名加工)" in r.text
            and "機密情報 vault (暗号化保管中)" in r.text
            and "企業マイページ" in r.text # nav 切替確認
            and "候補者マッチング" in r.text
        )
        check("12. GET /company/mypage (op default + nav 切替)", ok)

        # 13. /company/mypage?show_pii=1 (vault decrypt)
        r = client.get("/company/mypage?show_pii=1")
        ok = (
            r.status_code == 200
            and "機密情報 vault (一時表示中)" in r.text
            and "社名" in r.text
        )
        check("13. GET /company/mypage?show_pii=1 (vault decrypt)", ok)

        # 14. /company/match (5-stage、 重い)
        print(" /company/match 実行中 (5-stage pipeline、 ~5-15 秒)...")
        t0 = time.time()
        r = client.get("/company/match")
        elapsed = time.time() - t0
        ok = (
            r.status_code == 200
            and "AI 判定理由" in r.text
            and "fit:" in r.text
            and r.text.count("PROF-") >= 5 # top-5 候補
        )
        check(f"14. GET /company/match (5-stage AI, {elapsed:.1f}s)", ok, f"PROF- 出現 {r.text.count('PROF-')} 回")

        # 15. POST /company/intro/PROF-000001 (vault join + audit)
        r = client.post("/company/intro/PROF-000001", follow_redirects=False)
        ok = (
            r.status_code == 200
            and "候補者の個人情報 vault への access が発生しました" in r.text
            and "氏名 (カナ)" in r.text
        )
        check("15. POST /company/intro/PROF-000001 (vault join)", ok)

        # 16. POST /signout (company side)
        r = client.post("/signout", follow_redirects=False)
        check(
            "16. POST /signout (company)",
            r.status_code == 303 and r.headers.get("location") == "/",
        )

    # 17. 401 guard 確認 (signed out 状態で /mypage / /company/mypage)
    print("\n--- Auth gate checks (signed out) ---")
    r = httpx.get(f"{BASE}/mypage", timeout=TIMEOUT)
    check("17. GET /mypage 401 (signed out)", r.status_code == 401)

    r = httpx.get(f"{BASE}/company/mypage", timeout=TIMEOUT)
    check("18. GET /company/mypage 401 (signed out)", r.status_code == 401)

    # === Summary ===
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    pct = (passed / len(results) * 100) if results else 0
    print(f"=== Result: {passed}/{len(results)} PASS ({pct:.0f}%), {failed} FAIL ===")

    if failed > 0:
        print("\nFailed steps:")
        for name, ok, detail in results:
            if not ok:
                print(f" [FAIL] {name}{f' — {detail}' if detail else ''}")
        return 1

    print("\n動画作成 ready: 全 endpoint literal 動作確認済、 5-stage AI + vault + audit + nav 切替 全 PASS ★★★")
    return 0


if __name__ == "__main__":
    sys.exit(main())
