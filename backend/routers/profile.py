import os
import uuid
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from supabase import Client
from ..database import get_supabase
from ..schemas import UserResponse, ProfileUpdate
from ..auth import get_current_user
from .. import coach as coach_module

router = APIRouter(prefix="/api/profile", tags=["profile"])

SUPABASE_URL = os.getenv("SUPABASE_URL", "")


@router.get("/", response_model=UserResponse)
def get_profile(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = supabase.table("users").select("*").eq("id", current_user["id"]).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")
    user = result.data[0]
    assessment = supabase.table("runner_assessments").select("id").eq("user_id", user["id"]).execute()
    return UserResponse.model_validate({**user, "onboarding_complete": bool(assessment.data)})


@router.put("/", response_model=UserResponse)
def update_profile(
    data: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Auto-compute age from birthdate if provided
    if "birthdate" in updates:
        try:
            bd = date.fromisoformat(updates["birthdate"])
            today = date.today()
            updates["age"] = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except Exception:
            pass

    result = supabase.table("users").update(updates).eq("id", current_user["id"]).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user = result.data[0]
    assessment = supabase.table("runner_assessments").select("id").eq("user_id", user["id"]).execute()
    return UserResponse.model_validate({**user, "onboarding_complete": bool(assessment.data)})


@router.get("/health")
def get_health_info(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return the user's injury history and medications from their assessment."""
    result = (
        supabase.table("runner_assessments")
        .select("injury_history,medications")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        return {"injury_history": None, "medications": None}
    return result.data[0]


@router.put("/health")
def update_health_info(
    body: dict,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Update injury history and/or medications in the runner assessment."""
    updates = {}
    if "injury_history" in body:
        updates["injury_history"] = body["injury_history"] or None
    if "medications" in body:
        updates["medications"] = body["medications"] or None

    if not updates:
        return {"injury_history": None, "medications": None}

    existing = (
        supabase.table("runner_assessments")
        .select("id")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if existing.data:
        supabase.table("runner_assessments").update(updates).eq("user_id", current_user["id"]).execute()
    else:
        # No assessment yet — create a minimal stub so health info is persisted
        supabase.table("runner_assessments").insert({
            "user_id": current_user["id"],
            "experience_level": "beginner",
            "years_running": 0,
            "weekly_runs": 0,
            "weekly_km": 0,
            "primary_goal": "fitness",
            "available_days": 3,
            "preferred_distance": "mixed",
            "load_capacity": "moderate",
            **updates,
        }).execute()

    return {**updates}


@router.get("/bests")
def get_personal_bests(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Compute personal best estimated times from logged runs (used by AI context)."""
    result = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km")
        .eq("user_id", current_user["id"])
        .execute()
    )

    RACE_WINDOWS = {
        "5K":            (4.0,  6.0,   5.0),
        "10K":           (8.0,  12.0,  10.0),
        "Half Marathon": (19.0, 23.0,  21.0975),
        "Marathon":      (38.0, 45.0,  42.195),
    }

    bests = {}
    for race_name, (min_km, max_km, race_km) in RACE_WINDOWS.items():
        matching = [r for r in result.data if min_km <= r["distance_km"] <= max_km]
        if matching:
            best = min(matching, key=lambda r: r["pace_per_km"])
            est_min = best["pace_per_km"] * race_km
            bests[race_name] = {
                "time_min":    round(est_min, 2),
                "pace_per_km": round(best["pace_per_km"], 4),
                "date":        str(best["date"])[:10],
                "distance_km": round(best["distance_km"], 2),
            }

    return bests


@router.get("/manual-bests")
def get_manual_bests(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return the user's manually entered personal bests."""
    result = (
        supabase.table("user_personal_bests")
        .select("race,time_min,race_date")
        .eq("user_id", current_user["id"])
        .execute()
    )
    bests = {}
    for row in (result.data or []):
        bests[row["race"]] = {
            "time_min": row["time_min"],
            "race_date": str(row["race_date"])[:10] if row.get("race_date") else None,
        }
    return bests


@router.put("/manual-bests")
def update_manual_bests(
    body: dict,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Upsert the user's manually entered personal bests.
    Body: {race_name: {time_min, race_date?}} — send null time_min to delete that entry.
    """
    VALID_RACES = {"5K", "10K", "Half Marathon", "Marathon"}
    for race, data in body.items():
        if race not in VALID_RACES:
            continue
        if data is None or data.get("time_min") is None:
            # Delete entry if time is cleared
            supabase.table("user_personal_bests").delete().eq("user_id", current_user["id"]).eq("race", race).execute()
            continue
        row = {
            "user_id": current_user["id"],
            "race": race,
            "time_min": float(data["time_min"]),
            "race_date": data.get("race_date") or None,
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        existing = (
            supabase.table("user_personal_bests")
            .select("id")
            .eq("user_id", current_user["id"])
            .eq("race", race)
            .execute()
        )
        if existing.data:
            supabase.table("user_personal_bests").update(row).eq("user_id", current_user["id"]).eq("race", race).execute()
        else:
            supabase.table("user_personal_bests").insert(row).execute()

    return get_manual_bests(current_user, supabase)


@router.get("/predictions")
def get_predictions(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return cached AI race time predictions."""
    result = (
        supabase.table("user_race_predictions")
        .select("predictions,generated_at")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        return {"predictions": None, "generated_at": None}
    row = result.data[0]
    return {"predictions": row["predictions"], "generated_at": row["generated_at"]}


@router.post("/predictions")
def generate_predictions(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Generate AI race time predictions and cache them."""
    # Gather all run logs
    runs_result = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level,notes")
        .eq("user_id", current_user["id"])
        .order("date", desc=True)
        .execute()
    )
    run_logs = runs_result.data or []
    if not run_logs:
        raise HTTPException(status_code=400, detail="No runs logged yet. Log some runs first to generate predictions.")

    # Gather assessment
    assessment_result = (
        supabase.table("runner_assessments").select("*").eq("user_id", current_user["id"]).execute()
    )
    assessment = assessment_result.data[0] if assessment_result.data else None

    # Gather user profile
    user_result = supabase.table("users").select("age,weight_kg,max_hr").eq("id", current_user["id"]).execute()
    user_profile = user_result.data[0] if user_result.data else None

    # Gather manual bests
    bests_result = (
        supabase.table("user_personal_bests")
        .select("race,time_min,race_date")
        .eq("user_id", current_user["id"])
        .execute()
    )
    manual_bests = {}
    for row in (bests_result.data or []):
        manual_bests[row["race"]] = {
            "time_min": row["time_min"],
            "race_date": str(row["race_date"])[:10] if row.get("race_date") else None,
        }

    result_data = coach_module.predict_race_times(run_logs, assessment, user_profile, manual_bests or None)
    if not result_data:
        raise HTTPException(status_code=500, detail="Prediction generation failed. Please try again.")

    now_iso = datetime.now(tz=timezone.utc).isoformat()

    # Cache in user_race_predictions (upsert)
    existing = (
        supabase.table("user_race_predictions")
        .select("user_id")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if existing.data:
        supabase.table("user_race_predictions").update({
            "predictions": result_data,
            "generated_at": now_iso,
        }).eq("user_id", current_user["id"]).execute()
    else:
        supabase.table("user_race_predictions").insert({
            "user_id": current_user["id"],
            "predictions": result_data,
            "generated_at": now_iso,
        }).execute()

    return {"predictions": result_data, "generated_at": now_iso}


@router.post("/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        raise HTTPException(status_code=400, detail="Unsupported image format")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 5 MB")

    # Delete old avatar if exists
    user_row = supabase.table("users").select("avatar_url").eq("id", current_user["id"]).execute()
    if user_row.data and user_row.data[0].get("avatar_url"):
        old_url = user_row.data[0]["avatar_url"]
        # Extract path from URL
        if "/storage/v1/object/public/avatars/" in old_url:
            old_path = old_url.split("/storage/v1/object/public/avatars/")[-1]
            try:
                supabase.storage.from_("avatars").remove([old_path])
            except Exception:
                pass

    # Ensure avatars bucket exists (public)
    try:
        supabase.storage.get_bucket("avatars")
    except Exception:
        try:
            supabase.storage.create_bucket("avatars", options={"public": True})
        except Exception:
            pass  # may already exist or lack permissions

    # Upload new avatar
    path = f"{current_user['id']}/{uuid.uuid4()}.{ext}"
    supabase.storage.from_("avatars").upload(
        path,
        contents,
        file_options={"content-type": file.content_type, "upsert": "true"},
    )

    # Build public URL
    avatar_url = f"{SUPABASE_URL}/storage/v1/object/public/avatars/{path}"

    result = supabase.table("users").update({"avatar_url": avatar_url}).eq("id", current_user["id"]).execute()
    user = result.data[0]
    assessment = supabase.table("runner_assessments").select("id").eq("user_id", user["id"]).execute()
    return UserResponse.model_validate({**user, "onboarding_complete": bool(assessment.data)})


@router.delete("/")
def delete_account(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    uid = current_user["id"]

    # Delete avatar from storage if present
    user_row = supabase.table("users").select("avatar_url").eq("id", uid).execute()
    if user_row.data and user_row.data[0].get("avatar_url"):
        old_url = user_row.data[0]["avatar_url"]
        if "/storage/v1/object/public/avatars/" in old_url:
            old_path = old_url.split("/storage/v1/object/public/avatars/")[-1]
            try:
                supabase.storage.from_("avatars").remove([old_path])
            except Exception:
                pass

    # Delete user (cascades to run_logs, strava_tokens, runner_assessments, etc.)
    supabase.table("users").delete().eq("id", uid).execute()
    return {"detail": "Account deleted"}
