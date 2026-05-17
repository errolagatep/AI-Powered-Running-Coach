import os
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from supabase import Client

from ..auth import create_access_token, decode_token, get_current_user
from ..database import get_supabase
from .runs import _recalculate_gamification, _sync_achievements

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

STRAVA_CLIENT_ID     = os.getenv("STRAVA_CLIENT_ID", "")
STRAVA_CLIENT_SECRET = os.getenv("STRAVA_CLIENT_SECRET", "")
STRAVA_REDIRECT_URI  = os.getenv("STRAVA_REDIRECT_URI", "http://localhost:8000/api/integrations/strava/callback")
STRAVA_WEBHOOK_VERIFY_TOKEN = os.getenv("STRAVA_WEBHOOK_VERIFY_TOKEN", "takbo_strava_verify")

# Sport types imported as running activities (Strava sport_type field)
_RUN_SPORT_TYPES = {"Run", "TrailRun", "VirtualRun"}

# Max pages per incremental sync — after_ts already filters to recent activities;
# 3 pages (150 runs) is a large safety net for users who skipped many sync cycles.
_MAX_PAGES         = 3
# First-time connect: import only the 100 most recent runs (2 pages).
# Subsequent syncs use after_ts so older history is never needed again.
_MAX_PAGES_INITIAL = 2
_PER_PAGE          = 50
_HTTP_TIMEOUT      = 15  # seconds


# ── Strava OAuth ───────────────────────────────────────────────────────────────

@router.get("/strava/auth-url")
def strava_auth_url(current_user: dict = Depends(get_current_user)):
    """Return the Strava authorization URL (frontend navigates there)."""
    if not STRAVA_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Strava integration is not configured")

    # Short-lived state token: OAuth flow should complete within minutes, not days
    from datetime import timedelta as _td
    state = create_access_token(
        {"sub": current_user["id"], "purpose": "strava_connect"},
        expires_delta=_td(minutes=15),
    )
    params = urlencode({
        "client_id":       STRAVA_CLIENT_ID,
        "redirect_uri":    STRAVA_REDIRECT_URI,
        "response_type":   "code",
        "approval_prompt": "auto",
        "scope":           "activity:read_all",
        "state":           state,
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

    try:
        payload = decode_token(state)
        user_id = payload.get("sub")
        if not user_id or payload.get("purpose") != "strava_connect":
            raise ValueError("invalid state token")
    except Exception:
        return RedirectResponse(url="/dashboard.html?strava=error")

    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        res = client.post("https://www.strava.com/oauth/token", data={
            "client_id":     STRAVA_CLIENT_ID,
            "client_secret": STRAVA_CLIENT_SECRET,
            "code":          code,
            "grant_type":    "authorization_code",
        })
    token_data = res.json()
    if "access_token" not in token_data:
        return RedirectResponse(url="/dashboard.html?strava=error")

    expires_at  = datetime.fromtimestamp(token_data["expires_at"], tz=timezone.utc).isoformat()
    athlete_id  = token_data.get("athlete", {}).get("id")

    existing = supabase.table("strava_tokens").select("id").eq("user_id", user_id).execute()
    token_row = {
        "user_id":       user_id,
        "access_token":  token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at":    expires_at,
        "athlete_id":    athlete_id,
    }
    if existing.data:
        supabase.table("strava_tokens").update(token_row).eq("user_id", user_id).execute()
    else:
        supabase.table("strava_tokens").insert(token_row).execute()

    return RedirectResponse(url="/dashboard.html?strava=connected")


# ── Strava helpers ─────────────────────────────────────────────────────────────

def _refresh_strava_token(token_row: dict, supabase: Client) -> str:
    """Refresh the Strava access token if expired; return a valid access token."""
    try:
        expires_at = datetime.fromisoformat(token_row["expires_at"])
    except (TypeError, ValueError):
        expires_at = datetime.now(tz=timezone.utc)  # treat as expired if unparseable

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if datetime.now(tz=timezone.utc) < expires_at:
        return token_row["access_token"]

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            res = client.post("https://www.strava.com/oauth/token", data={
                "client_id":     STRAVA_CLIENT_ID,
                "client_secret": STRAVA_CLIENT_SECRET,
                "refresh_token": token_row["refresh_token"],
                "grant_type":    "refresh_token",
            })
        data = res.json()
    except Exception as e:
        logger.error("Strava token refresh request failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach Strava to refresh your token. Please try again.")

    if "access_token" not in data:
        raise HTTPException(status_code=401, detail="Failed to refresh Strava token. Please reconnect Strava.")

    try:
        new_expires_at = datetime.fromtimestamp(data["expires_at"], tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        new_expires_at = datetime.now(tz=timezone.utc).isoformat()
    supabase.table("strava_tokens").update({
        "access_token":  data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at":    new_expires_at,
        "updated_at":    datetime.now(tz=timezone.utc).isoformat(),
    }).eq("user_id", token_row["user_id"]).execute()

    return data["access_token"]


def _estimate_effort(heart_rate_avg: int | None, max_hr: int | None) -> int:
    """Estimate effort level 1–10 from HR percentage. Returns 5 if data insufficient."""
    if not heart_rate_avg or not max_hr or max_hr <= 0:
        return 5
    hr_pct = heart_rate_avg / max_hr
    hr_pct = max(0.0, min(hr_pct, 1.5))  # clamp to avoid out-of-range results
    if hr_pct < 0.60: return 3
    if hr_pct < 0.70: return 4
    if hr_pct < 0.80: return 6
    if hr_pct < 0.90: return 8
    return 10


def _activity_to_run_fields(activity: dict, user_id: str, max_hr: int | None) -> dict | None:
    """
    Convert a Strava activity dict to a run_logs insert/update dict.
    Returns None if the activity is missing required fields or has invalid data.
    """
    distance_m     = activity.get("distance")
    moving_time_s  = activity.get("moving_time")
    start_local    = activity.get("start_date_local", "")

    if not distance_m or not moving_time_s or not start_local:
        return None

    try:
        distance_km  = float(distance_m) / 1000
        duration_min = float(moving_time_s) / 60
    except (TypeError, ValueError):
        return None

    if distance_km <= 0 or duration_min <= 0:
        return None

    # Safe date extraction — must be exactly 10 chars of YYYY-MM-DD
    run_date = str(start_local)[:10]
    if len(run_date) != 10 or run_date[4] != "-" or run_date[7] != "-":
        return None

    heart_rate_avg = activity.get("average_heartrate")
    try:
        heart_rate_avg = int(heart_rate_avg) if heart_rate_avg else None
    except (TypeError, ValueError):
        heart_rate_avg = None

    pace_per_km  = duration_min / distance_km
    effort_level = _estimate_effort(heart_rate_avg, max_hr)

    # Safe polyline: Strava can return "map": null
    map_obj       = activity.get("map")
    route_polyline = map_obj.get("summary_polyline") or None if isinstance(map_obj, dict) else None

    # sport_type is the newer field; fall back to deprecated type
    sport_type = activity.get("sport_type") or activity.get("type") or "Run"

    elevation_gain = activity.get("total_elevation_gain")
    if elevation_gain is not None:
        try:
            elevation_gain = round(float(elevation_gain), 1)
        except (TypeError, ValueError):
            elevation_gain = None

    return {
        "user_id":           user_id,
        "date":              run_date,
        "distance_km":       round(distance_km, 2),
        "duration_min":      round(duration_min, 2),
        "pace_per_km":       round(pace_per_km, 4),
        "heart_rate_avg":    heart_rate_avg,
        "effort_level":      effort_level,
        "notes":             f"Imported from Strava: {activity.get('name', 'Run')}",
        "strava_activity_id": activity["id"],
        "route_polyline":    route_polyline,
        "sport_type":        sport_type,
        "elevation_gain":    elevation_gain,
    }


def _fetch_strava_pages(
    access_token: str,
    after_ts: int | None,
    max_pages: int = _MAX_PAGES,
) -> tuple[list[dict], bool]:
    """
    Fetch Strava running activities via pagination.
    Returns (activities, cap_hit) where cap_hit=True means there may be more pages.
    Raises HTTPException on rate-limit (429) or other Strava errors.
    """
    all_activities = []
    cap_hit = False
    params = {"per_page": _PER_PAGE}
    if after_ts:
        # 24-hour safety buffer so near-boundary runs aren't missed
        params["after"] = max(0, after_ts - 86400)

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            for page in range(1, max_pages + 1):
                params["page"] = page
                resp = client.get(
                    "https://www.strava.com/api/v3/athlete/activities",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )

                if resp.status_code == 429:
                    raise HTTPException(
                        status_code=429,
                        detail="Strava rate limit reached. Please wait a few minutes and try again.",
                    )
                if resp.status_code == 401:
                    raise HTTPException(
                        status_code=401,
                        detail="Strava token expired. Please reconnect Strava.",
                    )
                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Strava returned an error (HTTP {resp.status_code}). Please try again later.",
                    )

                try:
                    page_activities = resp.json()
                except Exception:
                    logger.warning("Non-JSON response from Strava on page %d (status %d)", page, resp.status_code)
                    break

                if not isinstance(page_activities, list) or not page_activities:
                    break  # no more pages or unexpected response shape

                all_activities.extend(page_activities)

                if len(page_activities) < _PER_PAGE:
                    break  # last page
            else:
                # Loop completed without a break — hit the page cap
                cap_hit = True
    except HTTPException:
        raise  # let 4xx/5xx pass through
    except Exception as e:
        logger.error("Network error fetching Strava activities: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach Strava. Please check your connection and try again.")

    return all_activities, cap_hit


# ── Strava sync & status ───────────────────────────────────────────────────────

@router.get("/strava/status")
def strava_status(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = supabase.table("strava_tokens").select("*").eq("user_id", current_user["id"]).execute()
    connected = bool(result.data)
    return {
        "connected":      connected,
        "athlete_id":     result.data[0].get("athlete_id")      if connected else None,
        "last_synced_at": result.data[0].get("last_synced_at")   if connected else None,
    }


@router.post("/strava/sync")
def strava_sync(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Fetch Strava running activities and sync them into run_logs.
    - New activities are inserted.
    - Existing activities are updated if Strava data changed (distance, duration, HR, elevation).
    - Incremental: uses last_synced_at to only fetch recent pages when available.
    - Paginates up to _MAX_PAGES (500 activities) per call.
    """
    token_result = supabase.table("strava_tokens").select("*").eq("user_id", current_user["id"]).execute()
    if not token_result.data:
        raise HTTPException(status_code=400, detail="Strava not connected. Please connect Strava first.")

    token_row    = token_result.data[0]
    access_token = _refresh_strava_token(token_row, supabase)

    # Determine incremental sync window
    last_synced_at_str = token_row.get("last_synced_at")
    after_ts: int | None = None
    if last_synced_at_str:
        try:
            last_synced_dt = datetime.fromisoformat(str(last_synced_at_str))
            if last_synced_dt.tzinfo is None:
                last_synced_dt = last_synced_dt.replace(tzinfo=timezone.utc)
            after_ts = int(last_synced_dt.timestamp())
        except (TypeError, ValueError):
            after_ts = None

    # Initial sync (no prior timestamp) gets a higher page cap to import full history
    pages_limit = _MAX_PAGES if after_ts else _MAX_PAGES_INITIAL
    all_activities, sync_incomplete = _fetch_strava_pages(access_token, after_ts, pages_limit)

    max_hr = current_user.get("max_hr")
    run_activities = [
        a for a in all_activities
        if (a.get("sport_type") or a.get("type")) in _RUN_SPORT_TYPES
    ]

    imported = 0
    updated  = 0
    skipped  = 0

    if run_activities:
        # ── Batch dedup: one query for all Strava IDs instead of one per activity ──
        strava_ids = [a["id"] for a in run_activities if a.get("id")]
        try:
            dup_result = (
                supabase.table("run_logs")
                .select("id,strava_activity_id,distance_km,duration_min,heart_rate_avg,elevation_gain")
                .eq("user_id", current_user["id"])
                .in_("strava_activity_id", strava_ids)
                .execute()
            )
            existing_map = {
                str(row["strava_activity_id"]): row
                for row in (dup_result.data or [])
                if row.get("strava_activity_id") is not None
            }
        except Exception as e:
            logger.error("Strava dedup query failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=(
                    "Sync failed: database query error. "
                    "If this is a new install, run migrations/supabase_schema.sql in your Supabase SQL Editor. "
                    f"Error: {str(e)[:200]}"
                ),
            )

        # ── Classify each activity as new / changed / unchanged ──────────────────
        to_insert: list[dict] = []
        to_update: list[tuple[str, dict]] = []  # (run_id, update_fields)

        for activity in run_activities:
            strava_id = activity.get("id")
            if not strava_id:
                continue
            fields = _activity_to_run_fields(activity, current_user["id"], max_hr)
            if fields is None:
                skipped += 1
                continue

            existing = existing_map.get(str(strava_id))
            if existing:
                changed = (
                    abs(float(existing.get("distance_km") or 0) - fields["distance_km"]) > 0.01
                    or abs(float(existing.get("duration_min") or 0) - fields["duration_min"]) > 0.1
                    or existing.get("heart_rate_avg") != fields["heart_rate_avg"]
                    or existing.get("elevation_gain") != fields["elevation_gain"]
                )
                if changed:
                    to_update.append((existing["id"], {
                        "distance_km":    fields["distance_km"],
                        "duration_min":   fields["duration_min"],
                        "pace_per_km":    fields["pace_per_km"],
                        "heart_rate_avg": fields["heart_rate_avg"],
                        "elevation_gain": fields["elevation_gain"],
                        "route_polyline": fields["route_polyline"],
                        "sport_type":     fields["sport_type"],
                    }))
                else:
                    skipped += 1
            else:
                to_insert.append(fields)

        # ── Batch insert new activities ───────────────────────────────────────────
        if to_insert:
            try:
                supabase.table("run_logs").insert(to_insert).execute()
                imported = len(to_insert)
            except Exception as e:
                logger.error("Batch insert failed (%d activities): %s", len(to_insert), e, exc_info=True)
                # Fallback: insert one-by-one so partial success is possible
                for fields in to_insert:
                    try:
                        supabase.table("run_logs").insert(fields).execute()
                        imported += 1
                    except Exception as e2:
                        logger.error("Single insert failed for activity %s: %s", fields.get("strava_activity_id"), e2)
                        skipped += 1

        # ── Apply individual updates for changed activities ───────────────────────
        for run_id, update_fields in to_update:
            try:
                supabase.table("run_logs").update(update_fields).eq("id", run_id).execute()
                updated += 1
            except Exception as e:
                logger.error("Update failed for run %s: %s", run_id, e)
                skipped += 1

    # Stamp last_synced_at so next call can do incremental sync.
    # Non-fatal: if the column doesn't exist yet (migration pending), log and continue.
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    try:
        supabase.table("strava_tokens").update({
            "last_synced_at": now_iso,
            "updated_at":     now_iso,
        }).eq("user_id", current_user["id"]).execute()
    except Exception as e:
        logger.warning("Could not stamp last_synced_at (run migration?): %s", e)

    # Recalculate gamification — failures are logged but don't block the response
    joined_date = str(current_user.get("created_at", ""))[:10] or None
    new_achievements = []

    if imported > 0 or updated > 0:
        try:
            _recalculate_gamification(current_user["id"], supabase)
        except Exception as e:
            logger.error("_recalculate_gamification failed after Strava sync: %s", e, exc_info=True)

        try:
            new_achievements = _sync_achievements(current_user["id"], supabase, joined_date=joined_date) or []
        except Exception as e:
            logger.error("_sync_achievements failed after Strava sync: %s", e, exc_info=True)

    return {
        "imported":         imported,
        "updated":          updated,
        "skipped":          skipped,
        "total_fetched":    len(run_activities),
        "new_achievements": new_achievements,
        "sync_incomplete":  sync_incomplete,
    }


# ── Strava Webhook ────────────────────────────────────────────────────────────

@router.get("/strava/webhook")
def strava_webhook_verify(
    hub_mode: str         = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str    = Query(None, alias="hub.challenge"),
):
    """Strava webhook subscription verification endpoint."""
    if hub_mode == "subscribe" and hub_verify_token == STRAVA_WEBHOOK_VERIFY_TOKEN:
        return JSONResponse(content={"hub.challenge": hub_challenge})
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@router.post("/strava/webhook")
async def strava_webhook_event(request: Request):
    """
    Receive Strava webhook event notifications.
    Acknowledges immediately (Strava requires response within 2 seconds).
    Full processing is done via the manual /strava/sync endpoint.
    """
    return JSONResponse(content={"status": "ok"})


@router.delete("/strava/disconnect")
def strava_disconnect(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    supabase.table("strava_tokens").delete().eq("user_id", current_user["id"]).execute()
    return {"disconnected": True}
