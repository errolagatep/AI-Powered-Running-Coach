import anthropic
import json
from typing import Optional
from datetime import datetime

COACH_SYSTEM_PROMPT = """You are an expert running coach with 20+ years of experience coaching athletes \
from beginners to competitive runners. You use evidence-based periodization principles (80/20 training, \
progressive overload, recovery cycles). You are encouraging but honest. Be specific with numbers and \
actionable with advice. Keep responses focused and practical."""

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _fmt_pace(pace_per_km: float) -> str:
    """Format decimal minutes as mm:ss per km."""
    minutes = int(pace_per_km)
    seconds = int(round((pace_per_km - minutes) * 60))
    return f"{minutes}:{seconds:02d}"


def _run_to_context_line(r: dict) -> str:
    date = str(r.get("date", ""))[:10]
    line = f"  {date}: {r['distance_km']:.1f}km @ {_fmt_pace(r['pace_per_km'])}/km, effort {r['effort_level']}/10"
    if r.get("heart_rate_avg"):
        line += f", HR {r['heart_rate_avg']}bpm"
    return line


def generate_run_feedback(
    run: dict,
    recent_runs: list,
    goal: Optional[dict] = None,
    user_profile: Optional[dict] = None,
) -> str:
    """Generate AI coaching feedback for a completed run."""
    parts = [f"""## Current Run
- Date: {str(run.get("date", ""))[:10]}
- Distance: {run["distance_km"]:.2f} km
- Duration: {run["duration_min"]:.1f} minutes
- Pace: {_fmt_pace(run["pace_per_km"])} min/km
- Heart Rate: {run.get("heart_rate_avg") or "Not recorded"} bpm
- Effort Level: {run["effort_level"]}/10
- Notes: {run.get("notes") or "None"}"""]

    if recent_runs:
        history = "\n## Recent Training History (last 10 runs)\n"
        history += "\n".join(_run_to_context_line(r) for r in recent_runs[:10])
        parts.append(history)

    if goal:
        try:
            race_date = datetime.fromisoformat(str(goal["race_date"]).replace("Z", "").split(".")[0])
            weeks_until = max(0, (race_date - datetime.utcnow()).days // 7)
        except Exception:
            weeks_until = "unknown"
        goal_txt = f"\n## Current Goal\n- Race: {goal['race_type']}\n- Weeks until race: {weeks_until}"
        if goal.get("target_time_min"):
            hrs = int(goal["target_time_min"] // 60)
            mins = int(goal["target_time_min"] % 60)
            goal_txt += f"\n- Target time: {hrs}h {mins}m" if hrs else f"\n- Target time: {mins} min"
        parts.append(goal_txt)

    if user_profile:
        profile = []
        if user_profile.get("max_hr"):
            profile.append(f"- Max HR: {user_profile['max_hr']} bpm")
        if user_profile.get("weight_kg"):
            profile.append(f"- Weight: {user_profile['weight_kg']} kg")
        if profile:
            parts.append("\n## Athlete Profile\n" + "\n".join(profile))

    context = "\n".join(parts)
    prompt = (
        f"{context}\n\n"
        "Please provide coaching feedback structured with these sections:\n\n"
        "## Performance Assessment\n"
        "## What Worked Well\n"
        "## Next Session Suggestion\n"
        "## Recovery Advice"
    )

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=1200,
        thinking={"type": "adaptive"},
        system=COACH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text
    return "Unable to generate feedback at this time."


def generate_weekly_plan(
    recent_runs: list,
    goal: Optional[dict] = None,
    user_name: str = "Athlete",
) -> dict:
    """Generate a 7-day structured training plan as JSON."""
    total_km = sum(r["distance_km"] for r in recent_runs[-14:]) if recent_runs else 0
    avg_effort = (
        sum(r["effort_level"] for r in recent_runs[-7:]) / len(recent_runs[-7:])
        if recent_runs
        else 5
    )

    context = f"Athlete: {user_name}\n"
    context += f"Total km in last 2 weeks: {total_km:.1f} km\n"
    context += f"Average recent effort: {avg_effort:.1f}/10\n"

    if recent_runs:
        context += "\nRecent training (last 4 weeks):\n"
        for r in sorted(recent_runs[-20:], key=lambda x: x.get("date", "")):
            context += _run_to_context_line(r) + "\n"
    else:
        context += "\nNew athlete — no runs logged yet. Create a beginner-friendly base-building plan.\n"

    if goal:
        try:
            race_date = datetime.fromisoformat(str(goal["race_date"]).replace("Z", "").split(".")[0])
            weeks_until = max(0, (race_date - datetime.utcnow()).days // 7)
        except Exception:
            weeks_until = "unknown"
        context += f"\nGoal race: {goal['race_type']} in {weeks_until} weeks"
        if goal.get("target_time_min"):
            context += f" (target: {goal['target_time_min']:.0f} min)"

    plan_schema = {
        "type": "object",
        "properties": {
            "week_summary": {"type": "string"},
            "total_km": {"type": "number"},
            "focus": {"type": "string"},
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "string"},
                        "workout_type": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "distance_km": {"type": "number"},
                        "duration_min": {"type": "number"},
                        "intensity": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "day", "workout_type", "title", "description",
                        "distance_km", "duration_min", "intensity", "notes",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["week_summary", "total_km", "focus", "days"],
        "additionalProperties": False,
    }

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=COACH_SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": plan_schema}},
        messages=[{
            "role": "user",
            "content": (
                f"{context}\n\n"
                "Create a 7-day training plan (Monday–Sunday). Include all 7 days including rest days. "
                "Workout types: Easy Run, Tempo Run, Interval Training, Long Run, Cross Training, Rest, Active Recovery. "
                "For Rest and Active Recovery days set distance_km and duration_min to 0. "
                "Intensity values: Easy, Moderate, Hard, Rest."
            ),
        }],
    )

    for block in response.content:
        if block.type == "text":
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                break

    return {"week_summary": "Plan generation failed", "total_km": 0, "focus": "", "days": []}
