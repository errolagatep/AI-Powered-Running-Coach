from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from typing import Optional
from ..database import get_supabase
from ..schemas import GoalCreate, GoalResponse
from ..auth import get_current_user

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.post("/", response_model=GoalResponse)
def set_goal(
    data: GoalCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = supabase.table("goals").insert({
        "user_id": current_user["id"],
        "race_type": data.race_type,
        "race_date": data.race_date.isoformat(),
        "target_time_min": data.target_time_min,
    }).execute()
    return GoalResponse.model_validate(result.data[0])


@router.get("/", response_model=Optional[GoalResponse])
def get_goal(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("goals")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return GoalResponse.model_validate(result.data[0])


@router.delete("/{goal_id}")
def delete_goal(
    goal_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    existing = (
        supabase.table("goals")
        .select("id")
        .eq("id", goal_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Goal not found")
    supabase.table("goals").delete().eq("id", goal_id).execute()
    return {"message": "Goal deleted"}
