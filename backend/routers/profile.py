import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from supabase import Client
from ..database import get_supabase
from ..schemas import UserResponse, ProfileUpdate
from ..auth import get_current_user

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

    result = supabase.table("users").update(updates).eq("id", current_user["id"]).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    user = result.data[0]
    assessment = supabase.table("runner_assessments").select("id").eq("user_id", user["id"]).execute()
    return UserResponse.model_validate({**user, "onboarding_complete": bool(assessment.data)})


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
