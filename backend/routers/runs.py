import logging
import math
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from typing import List

logger = logging.getLogger(__name__)
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


def _get_user_joined_date(user_id: str, supabase: Client) -> str:
    """Return the user's account creation date as an ISO date string (YYYY-MM-DD)."""
    result = supabase.table("users").select("created_at").eq("id", user_id).execute()
    if result.data and result.data[0].get("created_at"):
        return str(result.data[0]["created_at"])[:10]
    return "1970-01-01"


def _sync_achievements(user_id: str, supabase: Client, joined_date: str = None) -> list:
    """Recompute all achievements from run history with correct unlocked_at dates.

    Non-destructive: inserts missing achievements and corrects existing dates via
    individual updates. Never wipes the table, so a failed insert cannot leave
    the user with zero achievements.
    Only runs with date >= joined_date are counted (defaults to user's account creation date).
    Returns list of newly unlocked achievement dicts (ones that weren't there before).
    """
    if joined_date is None:
        joined_date = _get_user_joined_date(user_id, supabase)

    # Build a map of existing achievements: key → row
    existing_map = {
        a["achievement_key"]: a
        for a in supabase.table("achievements").select("*").eq("user_id", user_id).execute().data
    }

    # Fetch runs sorted oldest-first for chronological replay
    all_runs = (
        supabase.table("run_logs")
        .select("distance_km,pace_per_km,date")
        .eq("user_id", user_id)
        .gte("date", joined_date)
        .order("date", desc=False)
        .execute()
        .data
    )

    if not all_runs:
        return []

    # Normalise dates to YYYY-MM-DD strings
    for r in all_runs:
        r["_date"] = str(r["date"])[:10]

    # ── Run-count achievements: date of the Nth run ───────────────────────────
    def date_of_nth_run(n):
        return all_runs[n - 1]["_date"] if len(all_runs) >= n else None

    # ── Cumulative distance achievements: date the running total crossed threshold
    def date_km_threshold(threshold):
        cum = 0.0
        for r in all_runs:
            cum += r["distance_km"]
            if cum >= threshold:
                return r["_date"]
        return None

    # ── Speed demon: date of the earliest run under 5:00/km ──────────────────
    def date_first_fast_run():
        for r in all_runs:
            if r["pace_per_km"] < 5.0:
                return r["_date"]
        return None

    # ── Streak achievements: date the streak first hit N consecutive days ─────
    def date_streak_reached(n):
        unique_dates = sorted({r["_date"] for r in all_runs})
        if len(unique_dates) < n:
            return None
        streak = 1
        for i in range(1, len(unique_dates)):
            prev = date.fromisoformat(unique_dates[i - 1])
            curr = date.fromisoformat(unique_dates[i])
            if (curr - prev).days == 1:
                streak += 1
                if streak >= n:
                    return unique_dates[i]
            else:
                streak = 1
        return None

    # ── Weekly warrior: date of the run that pushed any week over 30 km ───────
    def date_weekly_warrior():
        from collections import defaultdict
        weekly = defaultdict(float)
        weekly_last_date = {}
        for r in all_runs:
            d = date.fromisoformat(r["_date"])
            week_key = d.isocalendar()[:2]  # (year, week)
            weekly[week_key] += r["distance_km"]
            weekly_last_date[week_key] = r["_date"]
            if weekly[week_key] >= 30:
                return weekly_last_date[week_key]
        return None

    # Map each key to its earned date
    unlock_dates = {
        "first_run":      date_of_nth_run(1),
        "runs_10":        date_of_nth_run(10),
        "runs_50":        date_of_nth_run(50),
        "runs_100":       date_of_nth_run(100),
        "dist_10km":      date_km_threshold(10),
        "dist_100km":     date_km_threshold(100),
        "dist_500km":     date_km_threshold(500),
        "dist_1000km":    date_km_threshold(1000),
        "streak_3":       date_streak_reached(3),
        "streak_7":       date_streak_reached(7),
        "streak_30":      date_streak_reached(30),
        "speed_demon":    date_first_fast_run(),
        "weekly_warrior": date_weekly_warrior(),
    }

    newly_unlocked = []
    for key, earned_date in unlock_dates.items():
        if earned_date is None or key not in ACHIEVEMENTS:
            continue
        meta = ACHIEVEMENTS[key]
        expected_unlocked_at = earned_date + "T00:00:00+00:00"

        if key not in existing_map:
            # New achievement — insert it
            supabase.table("achievements").insert({
                "user_id":         user_id,
                "achievement_key": key,
                "title":           meta["title"],
                "description":     meta["description"],
                "icon":            meta["icon"],
                "unlocked_at":     expected_unlocked_at,
            }).execute()
            newly_unlocked.append({"achievement_key": key, **meta})
        elif str(existing_map[key].get("unlocked_at", ""))[:10] != earned_date:
            # Existing achievement with wrong date — update it
            supabase.table("achievements").update({
                "unlocked_at": expected_unlocked_at,
            }).eq("id", existing_map[key]["id"]).execute()

    return newly_unlocked


def _compute_personal_bests(user_id: str, supabase: Client) -> dict:
    """Compute estimated personal best times from logged runs, merged with any manually entered PBs.
    Manual bests override computed ones for a given distance if they are faster."""
    result = (
        supabase.table("run_logs")
        .select("date,distance_km,pace_per_km")
        .eq("user_id", user_id)
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
            bests[race_name] = {
                "time_min":    round(best["pace_per_km"] * race_km, 2),
                "pace_per_km": round(best["pace_per_km"], 4),
                "date":        str(best["date"])[:10],
            }

    # Merge manually entered PBs — prefer the faster time for each distance
    manual_result = (
        supabase.table("user_personal_bests")
        .select("race,time_min,race_date")
        .eq("user_id", user_id)
        .execute()
    )
    for row in (manual_result.data or []):
        race = row["race"]
        if race not in bests or row["time_min"] < bests[race]["time_min"]:
            bests[race] = {
                "time_min":  round(row["time_min"], 2),
                "race_date": str(row["race_date"])[:10] if row.get("race_date") else None,
            }

    return bests


def _get_planned_workout_for_date(user_id: str, run_date: datetime, supabase: Client):
    """Look up the training plan and return the scheduled workout for the run's day of week."""
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_name = DAY_NAMES[run_date.weekday()]

    result = (
        supabase.table("training_plans")
        .select("plan_json,week_start")
        .eq("user_id", user_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None

    try:
        plan_data = json.loads(result.data[0]["plan_json"])
        days = plan_data.get("days", [])
        for day in days:
            if day.get("day") == day_name:
                return day
    except Exception:
        pass
    return None


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
    # Only count runs on or after the user's account creation date
    joined_date = _get_user_joined_date(user_id, supabase)

    # Collect existing achievement keys to avoid duplicates
    existing_keys = {
        a["achievement_key"]
        for a in supabase.table("achievements").select("achievement_key").eq("user_id", user_id).execute().data
    }

    all_runs = (
        supabase.table("run_logs")
        .select("distance_km,pace_per_km")
        .eq("user_id", user_id)
        .gte("date", joined_date)
        .execute()
        .data
    )
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
        .gte("date", max(joined_date, week_start.isoformat()[:10]))
        .execute()
    )
    weekly_km = sum(r["distance_km"] for r in weekly_result.data)

    candidates = []
    if total_runs >= 1:                     candidates.append("first_run")
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

    # Use the actual run date as unlocked_at, not the current timestamp
    run_date_iso = str(run.get("date", ""))[:10] + "T00:00:00+00:00"

    newly_unlocked = []
    for key in candidates:
        if key not in existing_keys and key in ACHIEVEMENTS:
            meta = ACHIEVEMENTS[key]
            supabase.table("achievements").insert({
                "user_id":         user_id,
                "achievement_key": key,
                "title":           meta["title"],
                "description":     meta["description"],
                "icon":            meta["icon"],
                "unlocked_at":     run_date_iso,
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
        "date": data.date.strftime("%Y-%m-%d"),
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
    planned_workout = _get_planned_workout_for_date(current_user["id"], data.date, supabase)
    personal_bests = _compute_personal_bests(current_user["id"], supabase)

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
        planned_workout=planned_workout,
        personal_bests=personal_bests,
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
            # Derive week_start from the run's local date to avoid UTC off-by-one
            run_date_str = str(saved_run.get("date", ""))[:10]
            try:
                run_date_obj = date.fromisoformat(run_date_str)
                week_start_str = (run_date_obj - timedelta(days=run_date_obj.weekday())).isoformat()
            except Exception:
                week_start_str = (datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())).strftime("%Y-%m-%d")
            supabase.table("training_plans").insert({
                "user_id": current_user["id"],
                "week_start": week_start_str,
                "plan_json": json.dumps(new_plan),
            }).execute()
            plan_adjusted = True
            plan_adjustment_reason = adjustment["reason"]
    except Exception as _adj_err:
        logger.warning("Plan adjustment failed for user %s: %s", current_user["id"], _adj_err, exc_info=True)

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
    run_date = datetime.fromisoformat(str(run["date"]).replace("Z", "").split(".")[0])
    planned_workout = _get_planned_workout_for_date(current_user["id"], run_date, supabase)
    personal_bests = _compute_personal_bests(current_user["id"], supabase)

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
        planned_workout=planned_workout,
        personal_bests=personal_bests,
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
        patch["date"] = patch["date"].strftime("%Y-%m-%d")

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
    """Recompute XP, level, and streak from scratch, replaying pace-PR and streak bonuses."""
    joined_date = _get_user_joined_date(user_id, supabase)

    all_runs = (
        supabase.table("run_logs")
        .select("distance_km,effort_level,pace_per_km,date")
        .eq("user_id", user_id)
        .gte("date", joined_date)
        .order("date", desc=False)  # chronological for correct replay
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

    # Build streak value at each unique run date (chronological)
    unique_dates_asc = sorted(set(str(r["date"])[:10] for r in all_runs))
    streak_at_date: dict = {}
    _s = 1
    streak_at_date[unique_dates_asc[0]] = 1
    for i in range(1, len(unique_dates_asc)):
        prev = date.fromisoformat(unique_dates_asc[i - 1])
        curr = date.fromisoformat(unique_dates_asc[i])
        _s = _s + 1 if (curr - prev).days == 1 else 1
        streak_at_date[unique_dates_asc[i]] = _s

    # Replay XP chronologically — mirrors _process_gamification logic
    total_xp = 0
    best_pace = None
    for r in all_runs:
        xp = int(r["distance_km"] * 10) + r["effort_level"] * 5
        # Streak bonus (capped at 50), matching _process_gamification
        run_streak = streak_at_date.get(str(r["date"])[:10], 1)
        xp += min(run_streak * 2, 50)
        # Pace PR bonus
        if best_pace is not None and r["pace_per_km"] < best_pace:
            xp += 50
        if best_pace is None or r["pace_per_km"] < best_pace:
            best_pace = r["pace_per_km"]
        total_xp += xp

    new_level = level_from_xp(total_xp)
    last_run_date = unique_dates_asc[-1]

    # Current streak: only active if most recent run is today or yesterday
    today_d = date.today()
    most_recent = date.fromisoformat(last_run_date)
    current_streak = streak_at_date[last_run_date] if (today_d - most_recent).days <= 1 else 0
    longest_streak = max(streak_at_date.values())

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
