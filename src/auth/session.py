"""Session + OAuth provider hooks。

PoC 試作 = mock OAuth (button click → fake session with synthetic profile_id)、
real OAuth (Google / LinkedIn) は OAuth client_id / client_secret を .env で provision 後
literal 有効化可能な配線。

移植 phase = Authlib + fastapi-users 経由で real OAuth、 JWT RS256、 MFA。
"""
from __future__ import annotations

import os
import secrets
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(32)
"""SESSION_SECRET: .env で固定推奨 (試作中は session 再生成 OK、 移植時に KMS rotate)。"""

ProviderName = Literal["mock", "google", "linkedin"]

# OAuth provider 設定 hook (real key を .env で provision 後 literal active 化)
OAUTH_PROVIDERS = {
    "google": {
        "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": "openid email profile",
    },
    "linkedin": {
        "client_id": os.environ.get("LINKEDIN_OAUTH_CLIENT_ID", ""),
        "client_secret": os.environ.get("LINKEDIN_OAUTH_CLIENT_SECRET", ""),
        "authorize_url": "https://www.linkedin.com/oauth/v2/authorization",
        "token_url": "https://www.linkedin.com/oauth/v2/accessToken",
        "userinfo_url": "https://api.linkedin.com/v2/userinfo",
        "scope": "openid email profile",
    },
}


def is_provider_configured(name: ProviderName) -> bool:
    """OAuth provider が .env に key configured されているか。"""
    if name == "mock":
        return True
    cfg = OAUTH_PROVIDERS.get(name)
    return bool(cfg and cfg["client_id"] and cfg["client_secret"])


def mock_signin(profile_id: str) -> dict[str, str]:
    """Mock OAuth: 指定 profile_id でログイン session を返す (PoC demo 用)。

    移植時に Authlib OAuth flow callback handler に置換、 user info から
    profile_id を resolve する。
    """
    return {
        "session_id": secrets.token_urlsafe(16),
        "profile_id": profile_id,
        "provider": "mock",
    }
