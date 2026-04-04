from fastapi import APIRouter, Depends
from supabase import Client
from datetime import datetime, timedelta
import json
from ..database import get_supabase
from ..auth import get_current_user
from ..coach import generate_weekly_plan, _fmt_pace

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("/current")
def get_current_plan(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("training_plans")
        .select("*")
        .eq("user_id", current_user["id"])
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": json.loads(plan["plan_json"]),
    }


@router.post("/generate")
def create_plan(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    recent_result = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level")
        .eq("user_id", current_user["id"])
        .order("date", desc=True)
        .limit(28)
        .execute()
    )

    goal_result = (
        supabase.table("goals")
        .select("race_type,race_date,target_time_min")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    goal = None
    if goal_result.data:
        g = goal_result.data[0]
        goal = {"race_type": g["race_type"], "race_date": g["race_date"], "target_time_min": g["target_time_min"]}

    assessment_result = (
        supabase.table("runner_assessments")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    assessment = assessment_result.data[0] if assessment_result.data else None

    plan_data = generate_weekly_plan(
        recent_runs=recent_result.data,
        goal=goal,
        user_name=current_user["name"],
        assessment=assessment,
    )

    result = supabase.table("training_plans").insert({
        "user_id": current_user["id"],
        "week_start": _next_monday().isoformat(),
        "plan_json": json.dumps(plan_data),
    }).execute()

    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": plan_data,
    }


def _next_monday() -> datetime:
    today = datetime.utcnow()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    return (today + timedelta(days=days_to_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


@router.post("/recalibrate")
def recalibrate_plan(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Regenerate the training plan, explicitly using AI feedback from recent runs."""
    recent_result = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level,ai_feedback")
        .eq("user_id", current_user["id"])
        .order("date", desc=True)
        .limit(10)
        .execute()
    )

    # Build coach notes from runs that have AI feedback
    feedback_runs = [r for r in recent_result.data if r.get("ai_feedback")]
    coach_notes = ""
    if feedback_runs:
        lines = ["Coaching observations from recent logged runs (use these to shape the plan):\n"]
        for r in feedback_runs[:5]:
            date_str = str(r["date"])[:10]
            lines.append(
                f"— {date_str}: {r['distance_km']:.1f} km @ {_fmt_pace(r['pace_per_km'])}/km, "
                f"effort {r['effort_level']}/10\n  Feedback: {r['ai_feedback'][:400]}\n"
            )
        coach_notes = "\n".join(lines)

    goal_result = (
        supabase.table("goals")
        .select("race_type,race_date,target_time_min")
        .eq("user_id", current_user["id"])
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    goal = None
    if goal_result.data:
        g = goal_result.data[0]
        goal = {"race_type": g["race_type"], "race_date": g["race_date"], "target_time_min": g["target_time_min"]}

    assessment_result = (
        supabase.table("runner_assessments")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    assessment = assessment_result.data[0] if assessment_result.data else None

    # Use only run data columns that generate_weekly_plan expects
    recent_runs = [
        {k: r[k] for k in ("date", "distance_km", "duration_min", "pace_per_km", "heart_rate_avg", "effort_level")}
        for r in recent_result.data
    ]

    plan_data = generate_weekly_plan(
        recent_runs=recent_runs,
        goal=goal,
        user_name=current_user["name"],
        assessment=assessment,
        coach_notes=coach_notes or None,
    )

    result = supabase.table("training_plans").insert({
        "user_id": current_user["id"],
        "week_start": _next_monday().isoformat(),
        "plan_json": json.dumps(plan_data),
    }).execute()

    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": plan_data,
    }
