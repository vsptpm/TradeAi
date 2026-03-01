"""
Upstox OAuth 2.0 helper routes.

Flow
----
1. Visit  GET /auth/upstox/login  → redirects your browser to Upstox consent page.
2. After you approve, Upstox redirects to:
     GET /auth/upstox/callback?code=<auth_code>
3. This handler exchanges the code for an access_token and returns it as JSON.
4. Copy the `access_token` value into your .env as UPSTOX_ACCESS_TOKEN.

Note: The Upstox access token is valid until 3:30 AM IST the next trading day.
You do NOT need to re-run this flow on every restart — only once per trading day.
"""

import requests
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from config import settings

router = APIRouter(prefix="/auth/upstox", tags=["upstox-oauth"])

UPSTOX_AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"


@router.get("/login")
def upstox_login():
    """Step 1 — redirect browser to Upstox consent page."""
    url = (
        f"{UPSTOX_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={settings.UPSTOX_API_KEY}"
        f"&redirect_uri={settings.UPSTOX_REDIRECT_URI}"
    )
    return RedirectResponse(url=url)


@router.get("/callback")
def upstox_callback(code: str):
    """Step 2 — exchange authorization code for access token."""
    resp = requests.post(
        UPSTOX_TOKEN_URL,
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": settings.UPSTOX_API_KEY,
            "client_secret": settings.UPSTOX_API_SECRET,
            "redirect_uri": settings.UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    access_token = data.get("access_token", "")

    if access_token:
        # Update in-memory token so the streamer picks it up immediately
        settings.UPSTOX_ACCESS_TOKEN = access_token

        # Restart the streamer with the fresh token
        from market_feed import streamer
        streamer.restart()

    # Redirect to frontend dashboard with success indicator
    return RedirectResponse(url="http://localhost:5173/dashboard?upstox_auth=success")
