import math
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from typing import List
from ..database import get_supabase
from ..schemas import RunCreate, RunUpdate, RunResponse
from ..auth import get_current_user
import json
from ..coach import generate_run_feedback, should_adjust_plan, generate_weekly_plan

router = APIRouter(prefix="/api/runs", tags=["runs"])

# ── Achievement catalogue ─────────────────────────────────────
ACHIEVEMENTS = {
    "first_run":       {"title": "First Steps",        "description": "Logged your very first run",                   "icon": "👟"},
    "runs_10":         {"title": "Ten Strong",          "description": "Logged 10 runs",                               "icon": "🔟"},
    "runs_50":         {"title": "Fifty Milestone",     "description": "Logged 50 runs",                               "icon": "5️⃣0️⃣"},
    "runs_100":        {"title": "Century Runner",      "description": "Logged 100 runs",                              "icon": "💯"},
    "dist_10km":       {"title": "10 km Club",          "description": "Accumulated 10 km total",                      "icon": "🥉"},
    "dist_100km":      {"title": "100 km Club",         "description": "Accumulated 100 km total",                     "icon": "🥈"},
    "dist_500km":      {"title": "500 km Club",         "description": "Accumulated 500 km total",                     "icon": "🥇"},
    "dist_1000km":     {"title": "1000 km Legend",      "description": "Accumulated 1000 km total",                    "icon": "🏆"},
    "streak_3":        {"title": "3-Day Streak",        "description": "Ran 3 days in a row",                          "icon": "🔥"},
    "streak_7":        {"title": "Week Warrior",        "description": "Ran 7 days in a row",                          "icon": "🔥🔥"},
    "streak_30":       {"title": "Iron Streak",         "description": "Ran 30 days in a row",                         "icon": "⚡"},
    "speed_demon":     {"title": "Speed Demon",         "description": "Ran a km in under 5 minutes",                  "icon": "💨"},
    "weekly_warrior":  {"title": "Weekly Warrior",      "description": "Ran 30+ km in a single week",                  "icon": "🗓️"},
}


def xp_for_level(level: int) -> int:
    return (level - 1) ** 2 * 100


def level_from_xp(total_xp: int) -> int:
    return int(math.sqrt(total_xp / 100)) + 1


def _latest_goal(user_id: str, supabase: Client):
    result = (
        supabase.table("goals")
        .select("race_type,race_date,target_time_min")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    g = result.data[0]
    return {"race_type": g["race_type"], "race_date": g["race_date"], "target_time_min": g["target_time_min"]}


def _get_assessment(user_id: str, supabase: Client):
    result = (
        supabase.table("runner_assessments")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0] if result.data else None


def _process_gamification(user_id: str, run: dict, supabase: Client) -> list:
    """Update streak, XP, level; check and unlock achievements. Returns list of new achievements."""
    today = date.today()

    # ── Fetch current state ───────────────────────────────────
    g_result = supabase.table("user_gamification").select("*").eq("user_id", user_id).execute()
    g = g_result.data[0] if g_result.data else {
        "total_xp": 0, "level": 1, "current_streak": 0, "longest_streak": 0, "last_run_date": None
    }

    # ── Streak logic ──────────────────────────────────────────
    last_run = g.get("last_run_date")
    if last_run:
        if isinstance(last_run, str):
            last_run = date.fromisoformat(last_run[:10])
        delta = (today - last_run).days
        if delta == 0:
            new_streak = g["current_streak"]
        elif delta == 1:
            new_streak = g["current_streak"] + 1
        else:
            new_streak = 1
    else:
        new_streak = 1

    longest = max(g["longest_streak"], new_streak)

    # ── XP calculation ────────────────────────────────────────
    xp_earned = int(run["distance_km"] * 10)
    xp_earned += run["effort_level"] * 5

    # Pace PR bonus
    pr_result = (
        supabase.table("run_logs")
        .select("pace_per_km")
        .eq("user_id", user_id)
        .neq("id", run["id"])
        .execute()
    )
    if pr_result.data:
        best_prev = min(r["pace_per_km"] for r in pr_result.data)
        if run["pace_per_km"] < best_prev:
            xp_earned += 50

    # Streak bonus (capped at 50)
    xp_earned += min(new_streak * 2, 50)

    new_total_xp = g["total_xp"] + xp_earned
    new_level = level_from_xp(new_total_xp)

    # ── Upsert gamification row ───────────────────────────────
    gam_payload = {
        "user_id": user_id,
        "total_xp": new_total_xp,
        "level": new_level,
        "current_streak": new_streak,
        "longest_streak": longest,
        "last_run_date": today.isoformat(),
    }
    if g_result.data:
        supabase.table("user_gamification").update(gam_payload).eq("user_id", user_id).execute()
    else:
        supabase.table("user_gamification").insert(gam_payload).execute()

    # ── Achievement checks ────────────────────────────────────
    # Collect existing achievement keys to avoid duplicates
    existing_keys = {
        a["achievement_key"]
        for a in supabase.table("achievements").select("achievement_key").eq("user_id", user_id).execute().data
    }

    all_runs = supabase.table("run_logs").select("distance_km,pace_per_km").eq("user_id", user_id).execute().data
    total_runs = len(all_runs)
    total_km = sum(r["distance_km"] for r in all_runs)

    # Weekly km — use timedelta to avoid crossing month boundaries
    today_dt = datetime.now(timezone.utc)
    week_start = (today_dt - timedelta(days=today_dt.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    weekly_result = (
        supabase.table("run_logs")
        .select("distance_km,date")
        .eq("user_id", user_id)
        .gte("date", week_start.isoformat())
        .execute()
    )
    weekly_km = sum(r["distance_km"] for r in weekly_result.data)

    candidates = []
    if total_runs == 1:                     candidates.append("first_run")
    if total_runs >= 10:                    candidates.append("runs_10")
    if total_runs >= 50:                    candidates.append("runs_50")
    if total_runs >= 100:                   candidates.append("runs_100")
    if total_km >= 10:                      candidates.append("dist_10km")
    if total_km >= 100:                     candidates.append("dist_100km")
    if total_km >= 500:                     candidates.append("dist_500km")
    if total_km >= 1000:                    candidates.append("dist_1000km")
    if new_streak >= 3:                     candidates.append("streak_3")
    if new_streak >= 7:                     candidates.append("streak_7")
    if new_streak >= 30:                    candidates.append("streak_30")
    if run["pace_per_km"] < 5.0:            candidates.append("speed_demon")
    if weekly_km >= 30:                     candidates.append("weekly_warrior")

    newly_unlocked = []
    for key in candidates:
        if key not in existing_keys and key in ACHIEVEMENTS:
            meta = ACHIEVEMENTS[key]
            supabase.table("achievements").insert({
                "user_id": user_id,
                "achievement_key": key,
                "title": meta["title"],
                "description": meta["description"],
                "icon": meta["icon"],
            }).execute()
            newly_unlocked.append({"achievement_key": key, **meta})

    return newly_unlocked


@router.post("/", response_model=RunResponse)
def log_run(
    data: RunCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    if data.distance_km <= 0:
        raise HTTPException(status_code=400, detail="Distance must be positive")
    if data.duration_min <= 0:
        raise HTTPException(status_code=400, detail="Duration must be positive")
    if not (1 <= data.effort_level <= 10):
        raise HTTPException(status_code=400, detail="Effort level must be between 1 and 10")

    pace = data.duration_min / data.distance_km

    result = supabase.table("run_logs").insert({
        "user_id": current_user["id"],
        "date": data.date.isoformat(),
        "distance_km": data.distance_km,
        "duration_min": data.duration_min,
        "pace_per_km": pace,
        "heart_rate_avg": data.heart_rate_avg,
        "effort_level": data.effort_level,
        "notes": data.notes,
    }).execute()

    run = result.data[0]

    recent = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level,notes")
        .eq("user_id", current_user["id"])
        .neq("id", run["id"])
        .order("date", desc=True)
        .limit(10)
        .execute()
    )

    assessment = _get_assessment(current_user["id"], supabase)

    feedback = generate_run_feedback(
        run=run,
        recent_runs=recent.data,
        goal=_latest_goal(current_user["id"], supabase),
        user_profile={
            "max_hr":    current_user.get("max_hr"),
            "weight_kg": current_user.get("weight_kg"),
            "age":       current_user.get("age"),
            "height_cm": current_user.get("height_cm"),
        },
        assessment=assessment,
    )

    updated = supabase.table("run_logs").update({"ai_feedback": feedback}).eq("id", run["id"]).execute()
    saved_run = updated.data[0]

    new_achievements = _process_gamification(current_user["id"], saved_run, supabase)

    # Ask coach whether the training plan needs restructuring
    plan_adjusted = False
    plan_adjustment_reason = ""
    try:
        adjustment = should_adjust_plan(
            run=saved_run,
            recent_runs=recent.data,
            assessment=assessment,
            feedback=feedback,
        )
        if adjustment["adjust"]:
            goal = _latest_goal(current_user["id"], supabase)
            new_plan = generate_weekly_plan(
                recent_runs=recent.data,
                goal=goal,
                user_name=current_user["name"],
                assessment=assessment,
                coach_notes=(
                    f"Reason for plan update: {adjustment['reason']}\n\n"
                    f"Latest coaching feedback (use specific distances/paces mentioned here):\n{feedback[:1200]}"
                ),
            )
            supabase.table("training_plans").insert({
                "user_id": current_user["id"],
                "week_start": (datetime.utcnow() - timedelta(days=datetime.utcnow().weekday()))
                              .replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
                "plan_json": json.dumps(new_plan),
            }).execute()
            plan_adjusted = True
            plan_adjustment_reason = adjustment["reason"]
    except Exception:
        pass  # Plan adjustment is non-critical — never fail a run log because of it

    response_data = {
        **saved_run,
        "new_achievements": new_achievements,
        "plan_adjusted": plan_adjusted,
        "plan_adjustment_reason": plan_adjustment_reason,
    }
    return RunResponse.model_validate(response_data)


@router.get("/", response_model=List[RunResponse])
def list_runs(
    skip: int = 0,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("run_logs")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("date", desc=True)
        .range(skip, skip + limit - 1)
        .execute()
    )
    return [RunResponse.model_validate(r) for r in result.data]


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("run_logs")
        .select("*")
        .eq("id", run_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.model_validate(result.data[0])


@router.post("/{run_id}/regenerate", response_model=RunResponse)
def regenerate_feedback(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    run_result = (
        supabase.table("run_logs")
        .select("*")
        .eq("id", run_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Run not found")
    run = run_result.data[0]

    recent = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level,notes")
        .eq("user_id", current_user["id"])
        .neq("id", run_id)
        .order("date", desc=True)
        .limit(10)
        .execute()
    )

    assessment = _get_assessment(current_user["id"], supabase)

    feedback = generate_run_feedback(
        run=run,
        recent_runs=recent.data,
        goal=_latest_goal(current_user["id"], supabase),
        user_profile={
            "max_hr":    current_user.get("max_hr"),
            "weight_kg": current_user.get("weight_kg"),
            "age":       current_user.get("age"),
            "height_cm": current_user.get("height_cm"),
        },
        assessment=assessment,
    )

    updated = supabase.table("run_logs").update({"ai_feedback": feedback}).eq("id", run_id).execute()
    return RunResponse.model_validate(updated.data[0])


@router.put("/{run_id}", response_model=RunResponse)
def update_run(
    run_id: str,
    data: RunUpdate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    existing = (
        supabase.table("run_logs")
        .select("*")
        .eq("id", run_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Run not found")

    patch = {k: v for k, v in data.model_dump().items() if v is not None}
    if not patch:
        return RunResponse.model_validate(existing.data[0])

    if "date" in patch:
        patch["date"] = patch["date"].isoformat()

    # Recalculate pace if distance or duration changed
    current = existing.data[0]
    new_distance = patch.get("distance_km", current["distance_km"])
    new_duration = patch.get("duration_min", current["duration_min"])
    patch["pace_per_km"] = new_duration / new_distance

    if "effort_level" in patch and not (1 <= patch["effort_level"] <= 10):
        raise HTTPException(status_code=400, detail="Effort level must be between 1 and 10")

    result = supabase.table("run_logs").update(patch).eq("id", run_id).execute()
    return RunResponse.model_validate(result.data[0])


def _recalculate_gamification(user_id: str, supabase: Client):
    """Recompute XP, level, and streak from scratch. Called after a run is deleted."""
    all_runs = (
        supabase.table("run_logs")
        .select("distance_km,effort_level,pace_per_km,date")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .execute()
        .data
    )

    if not all_runs:
        supabase.table("user_gamification").upsert({
            "user_id": user_id,
            "total_xp": 0,
            "level": 1,
            "current_streak": 0,
            "longest_streak": 0,
            "last_run_date": None,
        }, on_conflict="user_id").execute()
        return

    total_xp = sum(int(r["distance_km"] * 10) + r["effort_level"] * 5 for r in all_runs)
    new_level = level_from_xp(total_xp)

    # Unique run dates sorted descending
    dates = sorted(set(str(r["date"])[:10] for r in all_runs), reverse=True)
    last_run_date = dates[0]

    # Current streak: only count if most recent run is today or yesterday
    today_d = date.today()
    most_recent = date.fromisoformat(dates[0])
    current_streak = 0
    if (today_d - most_recent).days <= 1:
        current_streak = 1
        for i in range(1, len(dates)):
            if (date.fromisoformat(dates[i - 1]) - date.fromisoformat(dates[i])).days == 1:
                current_streak += 1
            else:
                break

    # Longest streak (full scan)
    longest_streak = current_streak
    running = 1
    for i in range(1, len(dates)):
        if (date.fromisoformat(dates[i - 1]) - date.fromisoformat(dates[i])).days == 1:
            running += 1
            longest_streak = max(longest_streak, running)
        else:
            running = 1

    supabase.table("user_gamification").upsert({
        "user_id": user_id,
        "total_xp": total_xp,
        "level": new_level,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "last_run_date": last_run_date,
    }, on_conflict="user_id").execute()


@router.delete("/{run_id}", status_code=204)
def delete_run(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    existing = (
        supabase.table("run_logs")
        .select("id")
        .eq("id", run_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Run not found")
    supabase.table("run_logs").delete().eq("id", run_id).execute()
    _recalculate_gamification(current_user["id"], supabase)
