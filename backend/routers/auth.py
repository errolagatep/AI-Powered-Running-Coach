import os
from urllib.parse import urlencode
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from supabase import Client
from ..database import get_supabase
from ..schemas import UserRegister, UserLogin, Token, UserResponse
from ..auth import hash_password, verify_password, create_access_token, get_current_user

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _with_onboarding_flag(user: dict, supabase: Client) -> dict:
    """Add onboarding_complete field to user dict."""
    result = (
        supabase.table("runner_assessments")
        .select("id")
        .eq("user_id", user["id"])
        .execute()
    )
    return {**user, "onboarding_complete": bool(result.data)}


@router.post("/register", response_model=Token)
def register(data: UserRegister, supabase: Client = Depends(get_supabase)):
    existing = supabase.table("users").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="Email already registered")

    result = supabase.table("users").insert({
        "email": data.email,
        "name": data.name,
        "password_hash": hash_password(data.password),
        "weight_kg": data.weight_kg,
        "max_hr": data.max_hr,
    }).execute()

    user = _with_onboarding_flag(result.data[0], supabase)
    token = create_access_token({"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}


@router.post("/login", response_model=Token)
def login(data: UserLogin, supabase: Client = Depends(get_supabase)):
    result = supabase.table("users").select("*").eq("email", data.email).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="No account found with that email. Please register first.")

    user_raw = result.data[0]
    if not user_raw.get("password_hash"):
        raise HTTPException(status_code=401, detail="This account uses Google Sign-In. Please sign in with Google.")
    if not verify_password(data.password, user_raw["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = _with_onboarding_flag(user_raw, supabase)
    token = create_access_token({"sub": user["id"]})
    return {"access_token": token, "token_type": "bearer", "user": UserResponse.model_validate(user)}


@router.get("/google")
def google_login():
    """Redirect the browser to Google's OAuth consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google Sign-In is not configured")
    params = urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    })
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/auth?{params}")


@router.get("/google/callback")
def google_callback(code: str = None, error: str = None, supabase: Client = Depends(get_supabase)):
    """Handle Google's OAuth redirect, upsert user, issue JWT, redirect to app."""
    if error or not code:
        return RedirectResponse(url="/index.html?google=denied")

    # Exchange auth code for Google access token
    token_res = httpx.post("https://oauth2.googleapis.com/token", data={
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    token_data = token_res.json()
    google_access_token = token_data.get("access_token")
    if not google_access_token:
        return RedirectResponse(url="/index.html?google=error")

    # Fetch the user's Google profile
    profile_res = httpx.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {google_access_token}"},
    )
    profile = profile_res.json()
    google_id = profile.get("id")
    email = profile.get("email")
    name = profile.get("name") or email.split("@")[0]

    if not google_id or not email:
        return RedirectResponse(url="/index.html?google=error")

    # Find existing user by google_id, then by email
    existing = supabase.table("users").select("*").eq("google_id", google_id).execute()
    if existing.data:
        user_raw = existing.data[0]
    else:
        by_email = supabase.table("users").select("*").eq("email", email).execute()
        if by_email.data:
            # Link Google ID to existing email account
            supabase.table("users").update({"google_id": google_id}).eq("id", by_email.data[0]["id"]).execute()
            user_raw = {**by_email.data[0], "google_id": google_id}
        else:
            # Create new user (no password)
            result = supabase.table("users").insert({
                "email": email,
                "name": name,
                "google_id": google_id,
            }).execute()
            user_raw = result.data[0]

    jwt_token = create_access_token({"sub": user_raw["id"]})
    return RedirectResponse(url=f"/oauth-callback.html?token={jwt_token}")


@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    user = _with_onboarding_flag(current_user, supabase)
    return UserResponse.model_validate(user)
