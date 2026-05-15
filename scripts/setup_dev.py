"""Dev setup: VAULT_KEY 生成 + vault 初期化 + .env への hint 出力。

Run: python -m scripts.setup_dev
出力: dev-only VAULT_KEY / SESSION_SECRET を console に表示、 user が .env に literal copy 推奨。
合成データから vault を初期化、 PoC 即時起動可能 state へ。
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

# Windows console UTF-8
sys.stdout.reconfigure(encoding="utf-8")

from cryptography.fernet import Fernet

# .env file が無ければ初回 setup、 dev key を env に inject
ENV_PATH = Path(__file__).parent.parent / ".env"


def main() -> None:
    if not ENV_PATH.exists():
        vault_key = Fernet.generate_key().decode()
        session_secret = secrets.token_urlsafe(32)
        print("=" * 70)
        print("[dev setup] .env が存在しません、 dev key を生成しました。")
        print("=" * 70)
        print()
        print("以下を .env file に literal copy してください (gitignore 済、 安全):")
        print()
        print(f"VAULT_KEY={vault_key}")
        print(f"SESSION_SECRET={session_secret}")
        print(f"SYNTHETIC_SEED=20260512")
        print(f"DATA_DIR=./data")
        print()
        print("(その後 `python -m scripts.setup_dev` を再実行で vault 初期化)")
        return

    # .env 存在 → vault 初期化
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)

    if not os.environ.get("VAULT_KEY"):
        print("ERROR: VAULT_KEY が .env に未設定")
        return

    print("[dev setup] .env を読込、 vault 初期化中...")
    from src.vault.store import init_vault_from_synthetic
    init_vault_from_synthetic()

    # smoke verify
    from src.vault.store import get_profile_pii
    sample = get_profile_pii("PROF-000001", requester="dev_setup_smoke", reason="init verify")
    if sample:
        print(f"[OK] vault 初期化成功、 PROF-000001 の name_kana = {sample.get('name_kana')}")
    else:
        print("[WARN] vault 初期化したが PROF-000001 が見つからない (synthetic data 未生成?)")

    print()
    print("起動 command:")
    print(" .venv/Scripts/python.exe -m uvicorn src.api.app:app --reload --port 8000")
    print(" → http://localhost:8000/ で landing page")


if __name__ == "__main__":
    main()
