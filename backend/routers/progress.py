from fastapi import APIRouter, Depends
from supabase import Client
from datetime import datetime, timedelta
from ..database import get_supabase
from ..auth import get_current_user

router = APIRouter(prefix="/api/progress", tags=["progress"])


def _parse_date(date_str) -> datetime:
    if isinstance(date_str, datetime):
        return date_str.replace(tzinfo=None) if date_str.tzinfo else date_str
    s = str(date_str).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return datetime.utcnow()


@router.get("/")
def get_progress(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    # Last 30 runs for individual charts (asc for display order)
    recent_result = (
        supabase.table("run_logs")
        .select("date,distance_km,pace_per_km,heart_rate_avg")
        .eq("user_id", current_user["id"])
        .order("date", desc=False)
        .limit(30)
        .execute()
    )
    recent_runs = recent_result.data

    run_labels, pace_data, distance_data, hr_data = [], [], [], []
    for r in recent_runs:
        dt = _parse_date(r["date"])
        run_labels.append(dt.strftime("%b %d"))
        pace_data.append(round(r["pace_per_km"], 2))
        distance_data.append(round(r["distance_km"], 2))
        hr_data.append(r.get("heart_rate_avg"))

    # All runs for weekly aggregation and stats
    all_result = (
        supabase.table("run_logs")
        .select("date,distance_km,pace_per_km")
        .eq("user_id", current_user["id"])
        .execute()
    )
    all_runs = all_result.data

    today = datetime.utcnow()
    weekly_labels, weekly_km = [], []
    for weeks_ago in range(11, -1, -1):
        week_start = today - timedelta(weeks=weeks_ago, days=today.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        total = sum(
            r["distance_km"]
            for r in all_runs
            if week_start <= _parse_date(r["date"]) < week_end
        )
        weekly_labels.append(week_start.strftime("%b %d"))
        weekly_km.append(round(total, 2))

    total_runs = len(all_runs)
    total_km = round(sum(r["distance_km"] for r in all_runs), 2)
    avg_pace = round(sum(r["pace_per_km"] for r in all_runs) / total_runs, 2) if total_runs else 0
    best_pace = round(min(r["pace_per_km"] for r in all_runs), 2) if total_runs else 0

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
