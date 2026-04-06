import os
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from supabase import Client

from ..auth import create_access_token, decode_token, get_current_user
from ..database import get_supabase

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

STRAVA_CLIENT_ID = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REDIRECT_URI = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/api/integrations/strava/callback")


# ── Strava OAuth ──────────────────────────────────────────────────────────────

@router.get("/strava/auth-url")
def strava_auth_url(current_user: dict = Depends(get_current_user)):
    """Return the Strava authorization URL (frontend navigates there)."""
    if not STRAVA_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Strava integration is not configured")

    # Embed user identity in state so callback can look up the user
    state = create_access_token({"sub": current_user["id"], "purpose": "strava_connect"})
    params = urlencode({
        "client_id": STRAVA_CLIENT_ID,
        "redirect_uri": STRAVA_REDIRECT_URI,
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": "activity:read_all",
        "state": state,
    })
    return {"url": f"https://www.strava.com/oauth/authorize?{params}"}


@router.get("/strava/callback")
def strava_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    scope: str = "",
    supabase: Client = Depends(get_supabase),
):
    """Handle Strava's OAuth redirect, save tokens, redirect to dashboard."""
    if error or not code or not state:
        return RedirectResponse(url="/dashboard.html?strava=denied")

    # Recover user_id from state
    try:
        payload = decode_token(state)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("missing sub")
    except Exception:
        return RedirectResponse(url="/dashboard.html?strava=error")

    # Exchange code for Strava tokens
    res = httpx.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
    })
    token_data = res.json()
    if "access_token" not in token_data:
        return RedirectResponse(url="/dashboard.html?strava=error")

    expires_at = datetime.fromtimestamp(token_data["expires_at"], tz=timezone.utc).isoformat()
    athlete_id = token_data.get("athlete", {}).get("id")

    # Upsert strava_tokens row
    existing = supabase.table("strava_tokens").select("id").eq("user_id", user_id).execute()
    token_row = {
        "user_id": user_id,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": expires_at,
        "athlete_id": athlete_id,
    }
    if existing.data:
        supabase.table("strava_tokens").update(token_row).eq("user_id", user_id).execute()
    else:
        supabase.table("strava_tokens").insert(token_row).execute()

    return RedirectResponse(url="/dashboard.html?strava=connected")


# ── Strava helpers ────────────────────────────────────────────────────────────

def _refresh_strava_token(token_row: dict, supabase: Client) -> str:
    """Refresh the Strava access token if expired; return a valid access token."""
    expires_at = datetime.fromisoformat(token_row["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    if now < expires_at:
        return token_row["access_token"]

    res = httpx.post("https://www.strava.com/oauth/token", data={
        "client_id": STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "refresh_token": token_row["refresh_token"],
        "grant_type": "refresh_token",
    })
    data = res.json()
    if "access_token" not in data:
        raise HTTPException(status_code=401, detail="Failed to refresh Strava token. Please reconnect Strava.")

    new_expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc).isoformat()
    supabase.table("strava_tokens").update({
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at": new_expires_at,
    }).eq("user_id", token_row["user_id"]).execute()

    return data["access_token"]


# ── Strava sync & status ──────────────────────────────────────────────────────

@router.get("/strava/status")
def strava_status(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = supabase.table("strava_tokens").select("athlete_id,updated_at").eq("user_id", current_user["id"]).execute()
    connected = bool(result.data)
    return {
        "connected": connected,
        "athlete_id": result.data[0]["athlete_id"] if connected else None,
    }


@router.post("/strava/sync")
def strava_sync(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Fetch recent Strava running activities and import new ones into run_logs."""
    token_result = supabase.table("strava_tokens").select("*").eq("user_id", current_user["id"]).execute()
    if not token_result.data:
        raise HTTPException(status_code=400, detail="Strava not connected. Please connect Strava first.")

    token_row = token_result.data[0]
    access_token = _refresh_strava_token(token_row, supabase)

    # Fetch up to 50 recent activities from Strava
    activities_res = httpx.get(
        "https://www.strava.com/api/v3/athlete/activities",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"per_page": 50, "page": 1},
    )
    if activities_res.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch Strava activities")

    activities = activities_res.json()
    run_activities = [a for a in activities if a.get("type") == "Run"]

    imported = 0
    skipped = 0
    for activity in run_activities:
        strava_id = activity["id"]

        # Skip if already imported
        dup = (
            supabase.table("run_logs")
            .select("id")
            .eq("user_id", current_user["id"])
            .eq("strava_activity_id", strava_id)
            .execute()
        )
        if dup.data:
            skipped += 1
            continue

        distance_km = activity["distance"] / 1000
        duration_min = activity["moving_time"] / 60
        if distance_km <= 0 or duration_min <= 0:
            continue

        pace_per_km = duration_min / distance_km
        heart_rate_avg = activity.get("average_heartrate")
        if heart_rate_avg:
            heart_rate_avg = int(heart_rate_avg)

        # Estimate effort from heart rate if available, else default to 5
        effort_level = 5
        if heart_rate_avg and current_user.get("max_hr"):
            hr_pct = heart_rate_avg / current_user["max_hr"]
            if hr_pct < 0.60:
                effort_level = 3
            elif hr_pct < 0.70:
                effort_level = 4
            elif hr_pct < 0.80:
                effort_level = 6
            elif hr_pct < 0.90:
                effort_level = 8
            else:
                effort_level = 10

        run_date = activity["start_date"][:10]  # ISO date, strip time

        supabase.table("run_logs").insert({
            "user_id": current_user["id"],
            "date": run_date,
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 2),
            "pace_per_km": round(pace_per_km, 4),
            "heart_rate_avg": heart_rate_avg,
            "effort_level": effort_level,
            "notes": f"Imported from Strava: {activity.get('name', 'Run')}",
            "strava_activity_id": strava_id,
        }).execute()
        imported += 1

    return {"imported": imported, "skipped": skipped, "total_fetched": len(run_activities)}


@router.delete("/strava/disconnect")
def strava_disconnect(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    supabase.table("strava_tokens").delete().eq("user_id", current_user["id"]).execute()
    return {"disconnected": True}
