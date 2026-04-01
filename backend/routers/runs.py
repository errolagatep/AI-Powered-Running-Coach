from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..models import RunLog, Goal
from ..schemas import RunCreate, RunResponse
from ..auth import get_current_user
from ..models import User
from ..coach import generate_run_feedback

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _run_to_dict(run: RunLog) -> dict:
    return {
        "date": str(run.date),
        "distance_km": run.distance_km,
        "duration_min": run.duration_min,
        "pace_per_km": run.pace_per_km,
        "heart_rate_avg": run.heart_rate_avg,
        "effort_level": run.effort_level,
        "notes": run.notes,
    }


def _latest_goal(user_id: int, db: Session):
    goal = (
        db.query(Goal)
        .filter(Goal.user_id == user_id)
        .order_by(Goal.created_at.desc())
        .first()
    )
    if not goal:
        return None
    return {
        "race_type": goal.race_type,
        "race_date": goal.race_date,
        "target_time_min": goal.target_time_min,
    }


@router.post("/", response_model=RunResponse)
def log_run(
    data: RunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.distance_km <= 0:
        raise HTTPException(status_code=400, detail="Distance must be positive")
    if data.duration_min <= 0:
        raise HTTPException(status_code=400, detail="Duration must be positive")
    if not (1 <= data.effort_level <= 10):
        raise HTTPException(status_code=400, detail="Effort level must be between 1 and 10")

    pace = data.duration_min / data.distance_km

    run = RunLog(
        user_id=current_user.id,
        date=data.date,
        distance_km=data.distance_km,
        duration_min=data.duration_min,
        pace_per_km=pace,
        heart_rate_avg=data.heart_rate_avg,
        effort_level=data.effort_level,
        notes=data.notes,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    recent = (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id, RunLog.id != run.id)
        .order_by(RunLog.date.desc())
        .limit(10)
        .all()
    )

    feedback = generate_run_feedback(
        run=_run_to_dict(run),
        recent_runs=[_run_to_dict(r) for r in recent],
        goal=_latest_goal(current_user.id, db),
        user_profile={"max_hr": current_user.max_hr, "weight_kg": current_user.weight_kg},
    )

    run.ai_feedback = feedback
    db.commit()
    db.refresh(run)
    return run


@router.get("/", response_model=List[RunResponse])
def list_runs(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id)
        .order_by(RunLog.date.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{run_id}", response_model=RunResponse)
def get_run(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(RunLog).filter(RunLog.id == run_id, RunLog.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/{run_id}/regenerate", response_model=RunResponse)
def regenerate_feedback(
    run_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = db.query(RunLog).filter(RunLog.id == run_id, RunLog.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    recent = (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id, RunLog.id != run.id)
        .order_by(RunLog.date.desc())
        .limit(10)
        .all()
    )

    run.ai_feedback = generate_run_feedback(
        run=_run_to_dict(run),
        recent_runs=[_run_to_dict(r) for r in recent],
        goal=_latest_goal(current_user.id, db),
        user_profile={"max_hr": current_user.max_hr, "weight_kg": current_user.weight_kg},
    )
    db.commit()
    db.refresh(run)
    return run
