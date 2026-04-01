from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from ..database import get_db
from ..models import RunLog
from ..auth import get_current_user
from ..models import User

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/")
def get_progress(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Last 30 runs for individual charts
    recent_runs = (
        db.query(RunLog)
        .filter(RunLog.user_id == current_user.id)
        .order_by(RunLog.date.asc())
        .limit(30)
        .all()
    )

    run_labels, pace_data, distance_data, hr_data = [], [], [], []
    for r in recent_runs:
        run_labels.append(r.date.strftime("%b %d"))
        pace_data.append(round(r.pace_per_km, 2))
        distance_data.append(round(r.distance_km, 2))
        hr_data.append(r.heart_rate_avg)

    # Weekly mileage: last 12 weeks
    today = datetime.utcnow()
    weekly_labels, weekly_km = [], []
    for weeks_ago in range(11, -1, -1):
        week_start = today - timedelta(weeks=weeks_ago, days=today.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        total = sum(
            r.distance_km
            for r in db.query(RunLog).filter(
                RunLog.user_id == current_user.id,
                RunLog.date >= week_start,
                RunLog.date < week_end,
            ).all()
        )
        weekly_labels.append(week_start.strftime("%b %d"))
        weekly_km.append(round(total, 2))

    all_runs = db.query(RunLog).filter(RunLog.user_id == current_user.id).all()
    total_runs = len(all_runs)
    total_km = round(sum(r.distance_km for r in all_runs), 2)
    avg_pace = round(sum(r.pace_per_km for r in all_runs) / total_runs, 2) if total_runs else 0
    best_pace = round(min(r.pace_per_km for r in all_runs), 2) if total_runs else 0

    return {
        "runs": {
            "labels": run_labels,
            "pace": pace_data,
            "distance": distance_data,
            "heart_rate": hr_data,
        },
        "weekly": {
            "labels": weekly_labels,
            "km": weekly_km,
        },
        "stats": {
            "total_runs": total_runs,
            "total_km": total_km,
            "avg_pace": avg_pace,
            "best_pace": best_pace,
        },
    }
