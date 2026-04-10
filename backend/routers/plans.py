from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from datetime import datetime, timedelta
import json
from ..database import get_supabase
from ..auth import get_current_user
from ..coach import generate_weekly_plan, generate_workout_variation, _fmt_pace
from .runs import _compute_personal_bests
from ..schemas import PlanRescheduleRequest

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


VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}


@router.patch("/{plan_id}")
def reschedule_workout(
    plan_id: str,
    body: PlanRescheduleRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    result = (
        supabase.table("training_plans")
        .select("*")
        .eq("id", plan_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_row = result.data[0]
    plan_data = json.loads(plan_row["plan_json"])

    if body.source_day not in VALID_DAYS or body.target_day not in VALID_DAYS:
        raise HTTPException(status_code=400, detail="Invalid day name")
    if body.source_day == body.target_day:
        raise HTTPException(status_code=400, detail="Source and target day must differ")

    days = plan_data.get("days", [])
    src_idx = next((i for i, d in enumerate(days) if d["day"] == body.source_day), None)
    tgt_idx = next((i for i, d in enumerate(days) if d["day"] == body.target_day), None)
    if src_idx is None or tgt_idx is None:
        raise HTTPException(status_code=400, detail="Day not found in plan")

    CONTENT_FIELDS = ["workout_type", "title", "description", "distance_km", "duration_min", "intensity", "notes"]
    src_content = {f: days[src_idx].get(f) for f in CONTENT_FIELDS}
    tgt_content = {f: days[tgt_idx].get(f) for f in CONTENT_FIELDS}

    for f in CONTENT_FIELDS:
        days[src_idx][f] = tgt_content[f]
        days[tgt_idx][f] = src_content[f]

    note = (body.note or "").strip()[:200] or None
    rest_types = ("Rest", "Active Recovery", None)

    days[tgt_idx]["rescheduled_from"] = body.source_day
    days[tgt_idx]["reschedule_note"] = note

    if src_content.get("workout_type") not in rest_types:
        days[src_idx]["rescheduled_from"] = body.target_day
        days[src_idx]["reschedule_note"] = note
    else:
        days[src_idx].pop("rescheduled_from", None)
        days[src_idx].pop("reschedule_note", None)

    supabase.table("training_plans").update({"plan_json": json.dumps(plan_data)}).eq("id", plan_id).execute()

    return {
        "id": plan_row["id"],
        "week_start": plan_row["week_start"],
        "generated_at": plan_row["generated_at"],
        "plan": plan_data,
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

    personal_bests = _compute_personal_bests(current_user["id"], supabase)

    plan_data = generate_weekly_plan(
        recent_runs=recent_result.data,
        goal=goal,
        user_name=current_user["name"],
        assessment=assessment,
        personal_bests=personal_bests,
    )

    result = supabase.table("training_plans").insert({
        "user_id": current_user["id"],
        "week_start": _current_monday().isoformat(),
        "plan_json": json.dumps(plan_data),
    }).execute()

    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": plan_data,
    }


@router.post("/{plan_id}/vary/{day_name}")
def vary_workout(
    plan_id: str,
    day_name: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Replace a workout day with an AI-generated variation at the same intensity."""
    if day_name not in VALID_DAYS:
        raise HTTPException(status_code=400, detail="Invalid day name")

    result = (
        supabase.table("training_plans")
        .select("*")
        .eq("id", plan_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_row = result.data[0]
    plan_data = json.loads(plan_row["plan_json"])

    days = plan_data.get("days", [])
    day_idx = next((i for i, d in enumerate(days) if d["day"] == day_name), None)
    if day_idx is None:
        raise HTTPException(status_code=404, detail="Day not found in plan")

    day = days[day_idx]
    if day.get("workout_type") in ("Rest", "Active Recovery"):
        raise HTTPException(status_code=400, detail="Cannot vary a rest or active recovery day")

    recent_result = (
        supabase.table("run_logs")
        .select("date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level")
        .eq("user_id", current_user["id"])
        .order("date", desc=True)
        .limit(10)
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

    variation = generate_workout_variation(
        day=day,
        recent_runs=recent_result.data,
        goal=goal,
        assessment=assessment,
    )

    if not variation:
        raise HTTPException(status_code=500, detail="Failed to generate workout variation")

    CONTENT_FIELDS = ["workout_type", "title", "description", "distance_km", "duration_min", "intensity", "notes"]
    for field in CONTENT_FIELDS:
        if field in variation:
            days[day_idx][field] = variation[field]
    days[day_idx]["is_variation"] = True

    supabase.table("training_plans").update({"plan_json": json.dumps(plan_data)}).eq("id", plan_id).execute()

    return {
        "id": plan_row["id"],
        "week_start": plan_row["week_start"],
        "generated_at": plan_row["generated_at"],
        "plan": plan_data,
    }


def _current_monday() -> datetime:
    """Returns the Monday of the current UTC week (today if today is Monday)."""
    today = datetime.utcnow()
    return (today - timedelta(days=today.weekday())).replace(
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

    personal_bests = _compute_personal_bests(current_user["id"], supabase)

    plan_data = generate_weekly_plan(
        recent_runs=recent_runs,
        goal=goal,
        user_name=current_user["name"],
        assessment=assessment,
        coach_notes=coach_notes or None,
        personal_bests=personal_bests,
    )

    result = supabase.table("training_plans").insert({
        "user_id": current_user["id"],
        "week_start": _current_monday().isoformat(),
        "plan_json": json.dumps(plan_data),
    }).execute()

    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": plan_data,
    }
