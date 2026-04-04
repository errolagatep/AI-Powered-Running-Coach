import math
from fastapi import APIRouter, Depends
from supabase import Client
from typing import List
from ..database import get_supabase
from ..schemas import GamificationResponse, AchievementResponse
from ..auth import get_current_user

router = APIRouter(prefix="/api/gamification", tags=["gamification"])


def xp_for_level(level: int) -> int:
    """XP required to reach the start of `level`."""
    return (level - 1) ** 2 * 100


def level_from_xp(total_xp: int) -> int:
    return int(math.sqrt(total_xp / 100)) + 1


@router.get("/", response_model=GamificationResponse)
def get_gamification(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("user_gamification")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        # Return default zeroed state for new users
        return GamificationResponse(
            total_xp=0,
            level=1,
            xp_for_current_level=0,
            xp_for_next_level=100,
            current_streak=0,
            longest_streak=0,
        )

    g = result.data[0]
    level = g["level"]
    return GamificationResponse(
        total_xp=g["total_xp"],
        level=level,
        xp_for_current_level=xp_for_level(level),
        xp_for_next_level=xp_for_level(level + 1),
        current_streak=g["current_streak"],
        longest_streak=g["longest_streak"],
    )


@router.get("/achievements", response_model=List[AchievementResponse])
def get_achievements(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("achievements")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("unlocked_at", desc=False)
        .execute()
    )
    return [AchievementResponse.model_validate(a) for a in result.data]
