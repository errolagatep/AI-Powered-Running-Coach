from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
from ..database import get_db
from ..models import RunLog, Goal, TrainingPlan
from ..auth import get_current_user
from ..models import User
from ..coach import generate_weekly_plan

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _run_to_dict(r: RunLog) -> dict:
    return {
        "date": str(r.date),
        "distance_km": r.distance_km,
        "duration_min": r.duration_min,
        "pace_per_km": r.pace_per_km,
        "heart_rate_avg": r.heart_rate_avg,
        "effort_level": r.effort_level,
    }


@router.get("/current")
def get_current_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.user_id == current_user.id)
        .order_by(TrainingPlan.generated_at.desc())
        .first()
    )
    if not plan:
        return None
    return {
        "id": plan.id,
        "week_start": plan.week_start,
        "generated_at": plan.generated_at,
        "plan": json.loads(plan.plan_json),
    }


@router.post("/generate")
def create_plan(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    recent_runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id)
        .order_by(RunLog.date.desc())
        .limit(28)
        .all()
    )

    goal_obj = (
        db.query(Goal)
        .filter(Goal.user_id == current_user.id)
        .order_by(Goal.created_at.desc())
        .first()
    )
    goal = (
        {"race_type": goal_obj.race_type, "race_date": goal_obj.race_date, "target_time_min": goal_obj.target_time_min}
        if goal_obj
        else None
    )

    plan_data = generate_weekly_plan(
        recent_runs=[_run_to_dict(r) for r in recent_runs],
        goal=goal,
        user_name=current_user.name,
    )

    # Start on next Monday
    today = datetime.utcnow()
    days_to_monday = (7 - today.weekday()) % 7 or 7
    week_start = (today + timedelta(days=days_to_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    plan = TrainingPlan(
        user_id=current_user.id,
        week_start=week_start,
        plan_json=json.dumps(plan_data),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    return {
        "id": plan.id,
        "week_start": plan.week_start,
        "generated_at": plan.generated_at,
        "plan": plan_data,
    }
