from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client
from datetime import datetime, timedelta, date as date_type
import json
from ..database import get_supabase
from ..auth import get_current_user
from ..coach import generate_weekly_plan, generate_workout_variation, generate_program_skeleton, _fmt_pace
from .runs import _compute_personal_bests
from ..schemas import PlanRescheduleRequest, ProgramCreate, ProgramResponse, NextWeekRequest, WeekSkeletonItem

router = APIRouter(prefix="/api/plans", tags=["plans"])


@router.get("/current")
def get_current_plan(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    # For users with an active program, return the highest week_number plan so
    # that recalibrating week N never shadows an already-generated week N+1.
    prog_result = (
        supabase.table("training_programs")
        .select("id")
        .eq("user_id", current_user["id"])
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if prog_result.data:
        program_id = prog_result.data[0]["id"]
        prog_plan = (
            supabase.table("training_plans")
            .select("*")
            .eq("user_id", current_user["id"])
            .eq("program_id", program_id)
            .order("week_number", desc=True)
            .limit(1)
            .execute()
        )
        if prog_plan.data:
            plan = prog_plan.data[0]
            # Build response directly (skip the fallback query below)
            response = {
                "id": plan["id"],
                "week_start": plan["week_start"],
                "generated_at": plan["generated_at"],
                "plan": json.loads(plan["plan_json"]),
                "program_id": plan.get("program_id"),
                "week_number": plan.get("week_number"),
                "total_weeks": None,
                "end_date": None,
            }
            prog_meta = (
                supabase.table("training_programs")
                .select("total_weeks,end_date")
                .eq("id", program_id)
                .execute()
            )
            if prog_meta.data:
                response["total_weeks"] = prog_meta.data[0]["total_weeks"]
                response["end_date"] = str(prog_meta.data[0]["end_date"])[:10]
            return response

    # No active program — fall back to most recently generated plan
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
    response = {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": json.loads(plan["plan_json"]),
        "program_id": plan.get("program_id"),
        "week_number": plan.get("week_number"),
        "total_weeks": None,
        "end_date": None,
    }
    if plan.get("program_id"):
        prog_result = (
            supabase.table("training_programs")
            .select("total_weeks,end_date")
            .eq("id", plan["program_id"])
            .execute()
        )
        if prog_result.data:
            response["total_weeks"] = prog_result.data[0]["total_weeks"]
            response["end_date"] = str(prog_result.data[0]["end_date"])[:10]
    return response


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

    rest_types = ("Rest", "Active Recovery", None)
    if src_content.get("workout_type") in rest_types:
        raise HTTPException(status_code=400, detail="Cannot reschedule a rest day — choose a workout day to move")

    for f in CONTENT_FIELDS:
        days[src_idx][f] = tgt_content[f]
        days[tgt_idx][f] = src_content[f]

    note = (body.note or "").strip()[:200] or None

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
    local_monday: str = Query(None, description="Local Monday date YYYY-MM-DD from client"),
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
        "week_start": _resolve_week_start(local_monday).isoformat(),
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


@router.get("/program/active")
def get_active_program(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return the user's active training program skeleton, or null if none exists."""
    result = (
        supabase.table("training_programs")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    prog = result.data[0]
    return {
        "id": prog["id"],
        "total_weeks": prog["total_weeks"],
        "start_date": str(prog["start_date"])[:10],
        "end_date": str(prog["end_date"])[:10],
        "goal_id": prog.get("goal_id"),
        "skeleton": json.loads(prog["skeleton_json"]),
        "status": prog["status"],
    }


@router.post("/program")
def create_program(
    body: ProgramCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Generate a full-duration periodization skeleton tied to the user's goal.

    For race goals: goal_id is required (has a race_date).
    For non-race goals: goal_id optional; duration_weeks used to compute end_date.
    If no goal exists, one is auto-created from the user's assessment primary_goal.
    """
    start_date = _resolve_week_start(body.local_monday)
    goal = None

    # ── Resolve the goal ──────────────────────────────────────────────────────
    if body.goal_id:
        goal_result = (
            supabase.table("goals")
            .select("*")
            .eq("id", body.goal_id)
            .eq("user_id", current_user["id"])
            .execute()
        )
        if not goal_result.data:
            raise HTTPException(status_code=404, detail="Goal not found")
        goal = goal_result.data[0]
    else:
        # No goal_id: look up latest goal for this user
        goal_result = (
            supabase.table("goals")
            .select("*")
            .eq("user_id", current_user["id"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if goal_result.data:
            goal = goal_result.data[0]

    # ── Compute end_date ──────────────────────────────────────────────────────
    if goal and goal.get("race_date"):
        try:
            end_date = date_type.fromisoformat(str(goal["race_date"])[:10])
        except Exception:
            raise HTTPException(status_code=400, detail="Goal has an invalid race_date")
    elif body.duration_weeks:
        end_date = start_date + timedelta(weeks=body.duration_weeks)
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either a goal with a race_date or duration_weeks to build a program"
        )

    if (end_date - start_date).days < 14:
        raise HTTPException(status_code=400, detail="Program end date must be at least 2 weeks away")

    total_weeks = min(max(2, (end_date - start_date).days // 7), 26)

    # ── Fetch assessment ──────────────────────────────────────────────────────
    assessment_result = (
        supabase.table("runner_assessments")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    assessment = assessment_result.data[0] if assessment_result.data else None

    # ── Auto-create goal if none exists (non-race users who skipped Step 3) ──
    if not goal and body.duration_weeks:
        primary_goal = assessment.get("primary_goal", "fitness") if assessment else "fitness"
        label_map = {
            "fitness": "General Fitness",
            "speed": "Speed Training",
            "endurance": "Build Endurance",
            "weight_loss": "Weight Loss",
            "race_prep": "Race Prep",
        }
        goal_insert = supabase.table("goals").insert({
            "user_id": current_user["id"],
            "race_type": label_map.get(primary_goal, primary_goal.replace("_", " ").title()),
            "race_date": end_date.isoformat(),
            "goal_type": primary_goal,
            "target_value": body.target_value,
            "target_unit": body.target_unit,
            "target_weight_kg": body.target_weight_kg,
        }).execute()
        goal = goal_insert.data[0]

    # Update goal with target fields if provided and not already set
    if goal and (body.target_value or body.target_weight_kg):
        update_fields = {}
        if body.target_value and not goal.get("target_value"):
            update_fields["target_value"] = body.target_value
        if body.target_unit and not goal.get("target_unit"):
            update_fields["target_unit"] = body.target_unit
        if body.target_weight_kg and not goal.get("target_weight_kg"):
            update_fields["target_weight_kg"] = body.target_weight_kg
        if update_fields:
            supabase.table("goals").update(update_fields).eq("id", goal["id"]).execute()
            goal.update(update_fields)

    # ── Fetch user weight for weight loss quantification ──────────────────────
    user_result = (
        supabase.table("users")
        .select("weight_kg")
        .eq("id", current_user["id"])
        .execute()
    )
    current_weight_kg = user_result.data[0].get("weight_kg") if user_result.data else None

    personal_bests = _compute_personal_bests(current_user["id"], supabase)

    # ── Apply intensity preferences from the modal ────────────────────────────
    # If the user re-confirmed load/days/distance, update the assessment so all
    # future weekly plans also reflect their current preferences.
    intensity_updates = {}
    if body.load_capacity:
        intensity_updates["load_capacity"] = body.load_capacity
    if body.available_days:
        intensity_updates["available_days"] = body.available_days
    if body.preferred_distance:
        intensity_updates["preferred_distance"] = body.preferred_distance

    if intensity_updates and assessment:
        supabase.table("runner_assessments")\
            .update(intensity_updates)\
            .eq("user_id", current_user["id"])\
            .execute()
        assessment.update(intensity_updates)
    elif intensity_updates and not assessment:
        # No assessment yet — skip the update gracefully
        pass

    # ── Build goal context for Claude ─────────────────────────────────────────
    goal_ctx = {
        "race_type": goal.get("race_type", "Goal") if goal else "Goal",
        "race_date": goal.get("race_date") if goal else None,
        "end_date_str": str(end_date),
        "target_time_min": goal.get("target_time_min") if goal else None,
        "goal_type": goal.get("goal_type", "race") if goal else "fitness",
        "goal_description": goal.get("goal_description") if goal else None,
        "target_value": goal.get("target_value") if goal else body.target_value,
        "target_unit": goal.get("target_unit") if goal else body.target_unit,
        "target_weight_kg": goal.get("target_weight_kg") if goal else body.target_weight_kg,
        "current_weight_kg": current_weight_kg,
    }

    try:
        skeleton = generate_program_skeleton(
            goal=goal_ctx,
            total_weeks=total_weeks,
            assessment=assessment,
            user_name=current_user.get("name", "Athlete"),
            personal_bests=personal_bests,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Program generation failed — please try again")

    # Mark any existing active programs as abandoned
    supabase.table("training_programs").update({"status": "abandoned"}).eq(
        "user_id", current_user["id"]
    ).eq("status", "active").execute()

    # Insert new program
    insert_result = supabase.table("training_programs").insert({
        "user_id": current_user["id"],
        "goal_id": goal["id"] if goal else None,
        "total_weeks": total_weeks,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "skeleton_json": json.dumps(skeleton),
        "status": "active",
    }).execute()

    prog = insert_result.data[0]
    return {
        "id": prog["id"],
        "user_id": prog["user_id"],
        "goal_id": prog.get("goal_id"),
        "total_weeks": prog["total_weeks"],
        "start_date": str(prog["start_date"])[:10],
        "end_date": str(prog["end_date"])[:10],
        "skeleton": skeleton,
        "status": prog["status"],
        "created_at": prog["created_at"],
    }


@router.post("/next-week")
def generate_next_week(
    body: NextWeekRequest,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Generate the detailed 7-day plan for a specific week of a training program."""
    # Fetch and verify program ownership
    prog_result = (
        supabase.table("training_programs")
        .select("*")
        .eq("id", body.program_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not prog_result.data:
        raise HTTPException(status_code=404, detail="Training program not found")
    prog = prog_result.data[0]

    # Find the skeleton entry for this week
    skeleton = json.loads(prog["skeleton_json"])
    skeleton_week = next((w for w in skeleton if w["week_number"] == body.week_number), None)
    if not skeleton_week:
        raise HTTPException(status_code=404, detail=f"Week {body.week_number} not found in program skeleton")

    # Idempotency: return existing plan if already generated
    existing = (
        supabase.table("training_plans")
        .select("*")
        .eq("program_id", body.program_id)
        .eq("week_number", body.week_number)
        .execute()
    )
    if existing.data:
        plan_row = existing.data[0]
        return {
            "id": plan_row["id"],
            "week_start": plan_row["week_start"],
            "generated_at": plan_row["generated_at"],
            "plan": json.loads(plan_row["plan_json"]),
            "program_id": body.program_id,
            "week_number": body.week_number,
            "total_weeks": prog["total_weeks"],
            "end_date": str(prog["end_date"])[:10],
        }

    # Compute week_start date
    from datetime import date
    prog_start = date.fromisoformat(str(prog["start_date"])[:10])
    week_start = prog_start + timedelta(weeks=body.week_number - 1)

    # Fetch inputs for plan generation
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

    # Add total_weeks into the week_context
    week_ctx = dict(skeleton_week)
    week_ctx["total_weeks"] = prog["total_weeks"]

    plan_data = generate_weekly_plan(
        recent_runs=recent_result.data,
        goal=goal,
        user_name=current_user.get("name", "Athlete"),
        assessment=assessment,
        personal_bests=personal_bests,
        week_context=week_ctx,
    )

    insert_result = supabase.table("training_plans").insert({
        "user_id": current_user["id"],
        "week_start": week_start.isoformat(),
        "plan_json": json.dumps(plan_data),
        "program_id": body.program_id,
        "week_number": body.week_number,
    }).execute()

    plan_row = insert_result.data[0]
    return {
        "id": plan_row["id"],
        "week_start": plan_row["week_start"],
        "generated_at": plan_row["generated_at"],
        "plan": plan_data,
        "program_id": body.program_id,
        "week_number": body.week_number,
        "total_weeks": prog["total_weeks"],
        "end_date": str(prog["end_date"])[:10],
    }


@router.get("/by-week")
def get_plan_by_week(
    program_id: str = Query(...),
    week_number: int = Query(...),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Return the training plan and run logs for a specific week of a program.

    Used by the week navigator to view past weeks.
    """
    # Verify program belongs to user
    prog_result = (
        supabase.table("training_programs")
        .select("id,total_weeks,start_date,end_date,skeleton_json")
        .eq("id", program_id)
        .eq("user_id", current_user["id"])
        .execute()
    )
    if not prog_result.data:
        raise HTTPException(status_code=404, detail="Program not found")
    prog = prog_result.data[0]

    # Compute that week's Monday from the program start_date
    try:
        prog_start = date_type.fromisoformat(str(prog["start_date"])[:10])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid program start_date")

    week_start = prog_start + timedelta(weeks=week_number - 1)
    # Use the Monday of the *next* week as an exclusive upper bound so all Sunday runs are captured
    week_end_exclusive = week_start + timedelta(days=7)

    # Look up the generated plan for this week
    plan_result = (
        supabase.table("training_plans")
        .select("*")
        .eq("user_id", current_user["id"])
        .eq("program_id", program_id)
        .eq("week_number", week_number)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )

    plan = None
    if plan_result.data:
        row = plan_result.data[0]
        plan = json.loads(row["plan_json"]) if isinstance(row["plan_json"], str) else row["plan_json"]

    # Fetch runs logged during this week
    runs_result = (
        supabase.table("run_logs")
        .select("id,date,distance_km,duration_min,pace_per_km,heart_rate_avg,effort_level,notes,ai_feedback")
        .eq("user_id", current_user["id"])
        .gte("date", week_start.isoformat())
        .lt("date", week_end_exclusive.isoformat())
        .order("date")
        .execute()
    )

    # Pull skeleton info for this week
    skeleton = json.loads(prog["skeleton_json"]) if isinstance(prog["skeleton_json"], str) else prog["skeleton_json"]
    week_skeleton = next((w for w in skeleton if w.get("week_number") == week_number), None)

    return {
        "week_number": week_number,
        "total_weeks": prog["total_weeks"],
        "week_start": week_start.isoformat(),
        "week_end": (week_end_exclusive - timedelta(days=1)).isoformat(),
        "plan": plan,
        "runs": runs_result.data,
        "skeleton": week_skeleton,
        "is_generated": plan is not None,
    }


def _current_monday() -> datetime:
    """Returns the Monday of the current UTC week (today if today is Monday).
    Prefer _resolve_week_start(local_monday) when a local date is available from the client.
    """
    today = datetime.utcnow()
    return (today - timedelta(days=today.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _resolve_week_start(local_monday: str | None) -> date_type:
    """Return a date for the Monday of the current week.
    Uses the client-supplied local_monday (YYYY-MM-DD) when provided,
    falling back to UTC-based calculation. The local date is required to
    avoid off-by-one errors for users in UTC+ timezones where UTC Monday
    morning may still be Sunday.
    """
    if local_monday:
        try:
            return date_type.fromisoformat(local_monday)
        except ValueError:
            pass
    return _current_monday().date()


@router.post("/recalibrate")
def recalibrate_plan(
    local_monday: str = Query(None, description="Local Monday date YYYY-MM-DD from client"),
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
        "week_start": _resolve_week_start(local_monday).isoformat(),
        "plan_json": json.dumps(plan_data),
    }).execute()

    plan = result.data[0]
    return {
        "id": plan["id"],
        "week_start": plan["week_start"],
        "generated_at": plan["generated_at"],
        "plan": plan_data,
    }
