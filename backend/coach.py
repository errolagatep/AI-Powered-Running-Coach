import anthropic
import json
import math
from typing import Optional
from datetime import datetime, date as _date

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
    if seconds == 60:          # rounding overflow: e.g. 5:59.5 → 6:00 not 5:60
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d}"


def _run_to_context_line(r: dict) -> str:
    date = str(r.get("date", ""))[:10]
    line = f"  {date}: {r['distance_km']:.1f}km @ {_fmt_pace(r['pace_per_km'])}/km, effort {r['effort_level']}/10"
    if r.get("heart_rate_avg"):
        line += f", HR {r['heart_rate_avg']}bpm"
    return line


# HR ceiling as % of max HR by workout type
_HR_ZONE_CEILINGS = {
    "Easy Run":          0.75,
    "Recovery Run":      0.72,
    "Long Run":          0.78,
    "Aerobic Run":       0.82,
    "Tempo Run":         0.90,
    "Interval Training": 0.95,
    "Hill Repeats":      0.95,
}
_DEFAULT_HR_CEILING = 0.82   # moderate / unclassified


def _hr_zone_compliance(
    run: dict,
    workout_type: str,
    planned_workout: Optional[dict],
    max_hr: Optional[int],
) -> Optional[dict]:
    """Return HR zone compliance data, or None if max_hr / HR data unavailable."""
    if not max_hr or not run.get("heart_rate_avg"):
        return None

    actual_hr = run["heart_rate_avg"]

    # Try to refine ceiling from planned intensity label
    intensity = ((planned_workout or {}).get("intensity") or "").lower()
    if "easy" in intensity or "recovery" in intensity:
        ceiling_pct = 0.75
    elif "long" in intensity:
        ceiling_pct = 0.78
    elif "tempo" in intensity or "threshold" in intensity:
        ceiling_pct = 0.90
    elif "interval" in intensity or "hard" in intensity or "hill" in intensity:
        ceiling_pct = 0.95
    else:
        ceiling_pct = _HR_ZONE_CEILINGS.get(workout_type, _DEFAULT_HR_CEILING)

    hr_ceiling = int(max_hr * ceiling_pct)
    over_by = actual_hr - hr_ceiling   # negative = under ceiling

    if over_by <= 0:
        compliance = "compliant"
    elif over_by <= 5:
        compliance = "near-zone"      # small tolerance
    elif over_by <= 12:
        compliance = "slightly-over"
    else:
        compliance = "over-zone"

    return {
        "ceiling_pct": int(ceiling_pct * 100),
        "hr_ceiling":  hr_ceiling,
        "actual_hr":   actual_hr,
        "hr_pct":      round(actual_hr / max_hr * 100, 1),
        "over_by":     over_by,
        "compliance":  compliance,
    }


def _hr_zone_context(zone: dict, workout_type: str) -> str:
    if not zone:
        return ""
    c = zone["compliance"]
    lines = [f"\n## HR Zone Assessment"]
    lines.append(f"- Workout target: {workout_type}")
    lines.append(f"- HR ceiling: {zone['hr_ceiling']} bpm ({zone['ceiling_pct']}% max HR)")
    lines.append(f"- Actual HR: {zone['actual_hr']} bpm ({zone['hr_pct']}% max HR)")

    if c == "compliant":
        lines.append("- Zone compliance: COMPLIANT (athlete held HR in correct zone)")
        lines.append("- Pace interpretation: any pace deficit reflects current aerobic capacity — NOT a failure")
    elif c == "near-zone":
        lines.append(f"- Zone compliance: NEAR-ZONE ({zone['over_by']} bpm over ceiling — within tolerance)")
        lines.append("- Pace interpretation: HR discipline was good; slow pace is aerobic capacity, not execution failure")
    elif c == "slightly-over":
        lines.append(f"- Zone compliance: SLIGHTLY OVER ({zone['over_by']} bpm above ceiling)")
    else:
        lines.append(f"- Zone compliance: OVER ZONE ({zone['over_by']} bpm above ceiling — significant drift)")

    return "\n".join(lines)


def _trend_context(recent_runs: list, max_hr: Optional[int] = None) -> str:
    """Compute pace and HR trend lines from recent runs (most-recent-first)."""
    if len(recent_runs) < 4:
        return ""

    lines = []

    # Pace trend: avg of 3 most recent vs avg of next 3
    paces = [r["pace_per_km"] for r in recent_runs if r.get("pace_per_km")]
    if len(paces) >= 6:
        avg_recent = sum(paces[:3]) / 3
        avg_older  = sum(paces[3:6]) / 3
        diff = avg_older - avg_recent   # positive = getting faster
        if abs(diff) >= 0.1:
            direction = "faster" if diff > 0 else "slower"
            lines.append(f"- Pace trend: {direction} by {abs(diff):.1f} min/km vs 3 runs ago")
        else:
            lines.append("- Pace trend: stable over last 6 runs")

    # HR trend: compare two halves of HR-recorded runs
    hr_runs = [r for r in recent_runs if r.get("heart_rate_avg")]
    if len(hr_runs) >= 4:
        mid = len(hr_runs) // 2
        avg_recent_hr = sum(r["heart_rate_avg"] for r in hr_runs[:mid]) / mid
        avg_older_hr  = sum(r["heart_rate_avg"] for r in hr_runs[mid:mid * 2]) / mid
        hr_diff = avg_recent_hr - avg_older_hr   # positive = HR rising
        if abs(hr_diff) >= 4:
            if hr_diff > 0:
                lines.append(f"- HR trend: cardiac load RISING ({hr_diff:+.0f} bpm avg) — possible fatigue or heat stress")
            else:
                lines.append(f"- HR trend: cardiac efficiency IMPROVING ({hr_diff:+.0f} bpm avg) — aerobic adaptation")
        else:
            lines.append("- HR trend: stable")

    # Flag easy runs where HR exceeded 80% of max HR
    if max_hr:
        flags = []
        for r in recent_runs[:5]:
            hr = r.get("heart_rate_avg")
            effort = r.get("effort_level") or 99
            if hr and effort <= 6:
                pct = hr / max_hr * 100
                if pct > 80:
                    flags.append(f"  {str(r.get('date',''))[:10]}: easy-effort run at {pct:.0f}% max HR ({hr} bpm)")
        if flags:
            lines.append("- Easy-run HR concern (>80% max HR on low-effort runs):")
            lines.extend(flags)

    return "\n## Pace & HR Trends\n" + "\n".join(lines) if lines else ""


def _extract_json_block(text: str) -> str:
    """Strip markdown fences and extract the outermost JSON object or array."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]).rstrip("`").strip()

    obj_start, obj_end = text.find("{"), text.rfind("}")
    arr_start, arr_end = text.find("["), text.rfind("]")
    has_obj = obj_start != -1 and obj_end > obj_start
    has_arr = arr_start != -1 and arr_end > arr_start

    if has_obj and has_arr:
        # Whichever opens first is the outermost container
        if obj_start < arr_start:
            return text[obj_start : obj_end + 1]
        return text[arr_start : arr_end + 1]
    if has_obj:
        return text[obj_start : obj_end + 1]
    if has_arr:
        return text[arr_start : arr_end + 1]
    return text


def generate_athlete_summary(
    recent_runs: list,
    assessment: Optional[dict] = None,
    user_profile: Optional[dict] = None,
    existing_summary: Optional[str] = None,
) -> str:
    """Generate or refresh a 200–350 word rolling athlete summary.

    This is stored in athlete_summaries and prepended to every coaching prompt
    so Claude has longitudinal context without re-reading raw metrics each time.
    """
    context = ""

    if user_profile:
        parts = []
        if user_profile.get("name"):  parts.append(f"Name: {user_profile['name']}")
        if user_profile.get("age"):   parts.append(f"Age: {user_profile['age']}")
        if user_profile.get("weight_kg"): parts.append(f"Weight: {user_profile['weight_kg']} kg")
        if user_profile.get("max_hr"):    parts.append(f"Max HR: {user_profile['max_hr']} bpm")
        if parts:
            context += "Athlete: " + ", ".join(parts) + "\n"

    if assessment:
        context += _assessment_context(assessment) + "\n"

    if recent_runs:
        context += f"\nLast {min(len(recent_runs), 20)} runs (newest first):\n"
        for r in recent_runs[:20]:
            line = _run_to_context_line(r)
            if r.get("notes"):
                line += f" | Notes: {str(r['notes'])[:120]}"
            if r.get("coach_note"):
                line += f" | Pre-run note: {str(r['coach_note'])[:80]}"
            if r.get("ai_feedback"):
                line += f" | Feedback: {str(r['ai_feedback'])[:180]}"
            context += line + "\n"

    prior = ""
    if existing_summary:
        prior = (
            f"\nPrevious summary (update where facts have changed; keep what's still accurate):\n"
            f"{existing_summary}\n"
        )

    prompt = (
        f"{context}{prior}\n"
        "Write a concise 200–350 word athlete summary for use by an AI running coach. "
        "Cover:\n"
        "1. Current fitness level and weekly training volume\n"
        "2. Observed patterns — pacing discipline, effort control, consistency, "
        "any tendency to push easy runs too hard\n"
        "3. Injury signals, health notes, or medications mentioned\n"
        "4. What is working well and what to monitor\n"
        "5. Current goal and training phase context\n\n"
        "Write in third person (e.g. 'The athlete...'). Be specific with numbers. "
        "Flowing prose only — no bullet points, no headings. "
        "This text will be prepended to every coaching prompt."
    )

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        system=COACH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def get_onboarding_followup(assessment: dict) -> Optional[str]:
    """Ask Claude if the runner assessment needs one clarifying question."""
    prompt = f"""A new runner just completed their onboarding assessment:
- Experience level: {assessment.get('experience_level')}
- Years running: {assessment.get('years_running')}
- Current weekly runs: {assessment.get('weekly_runs')} runs, {assessment.get('weekly_km')} km
- Primary goal: {assessment.get('primary_goal')}
- Available days/week: {assessment.get('available_days')}
- Preferred distance: {assessment.get('preferred_distance')}
- Load capacity: {assessment.get('load_capacity')}
- Injury history: {assessment.get('injury_history') or 'None reported'}

Is there ONE important clarifying question you'd ask to better personalise their training plan? \
If the profile is clear enough, reply with just the word: none
If you do have a question, reply with ONLY the question itself (no preamble, no explanation)."""

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=150,
        system=COACH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            return None if text.lower() == "none" else text
    return None


def _assessment_context(assessment: dict) -> str:
    """Format assessment data as a runner profile block for AI prompts."""
    goal_map = {
        "fitness": "General Fitness",
        "speed": "Speed / PR",
        "endurance": "Build Endurance",
        "race_prep": "Race Preparation",
        "weight_loss": "Weight Loss",
    }
    dist_map = {"short": "3–5 km", "medium": "5–10 km", "long": "10 km+", "mixed": "Mixed"}
    return (
        "\n## Runner Profile\n"
        f"- Experience: {assessment.get('experience_level', '').capitalize()} "
        f"({assessment.get('years_running', 0)} years running)\n"
        f"- Current volume: {assessment.get('weekly_km', 0):.0f} km/week, "
        f"{assessment.get('weekly_runs', 0)} runs/week\n"
        f"- Primary goal: {goal_map.get(assessment.get('primary_goal', ''), assessment.get('primary_goal', ''))}\n"
        f"- Available days: {assessment.get('available_days', 0)}/week\n"
        f"- Load capacity: {assessment.get('load_capacity', '').capitalize()}\n"
        f"- Preferred distance: {dist_map.get(assessment.get('preferred_distance', ''), assessment.get('preferred_distance', ''))}\n"
        f"- Injury history: {assessment.get('injury_history') or 'None reported'}\n"
        f"- Medications: {assessment.get('medications') or 'None reported'}\n"
        + (f"- Additional note: {assessment['ai_followup_a']}\n" if assessment.get('ai_followup_a') else "")
    )


def should_adjust_plan(
    run: dict,
    recent_runs: list,
    assessment: Optional[dict],
    feedback: str,
) -> dict:
    """Ask Claude whether the training plan needs adjusting based on this run.

    Returns {"adjust": bool, "reason": str}.
    """
    recent_summary = ""
    if recent_runs:
        recent_summary = "\nRecent runs (last 5):\n" + "\n".join(
            _run_to_context_line(r) for r in recent_runs[:5]
        )

    assessment_note = ""
    if assessment:
        assessment_note = (
            f"\nRunner profile — Goal: {assessment.get('primary_goal')}, "
            f"Load: {assessment.get('load_capacity')}, "
            f"Experience: {assessment.get('experience_level')}"
        )
        if assessment.get('injury_history'):
            assessment_note += f", Injuries: {assessment['injury_history']}"
        if assessment.get('medications'):
            assessment_note += f", Medications: {assessment['medications']}"

    prompt = f"""A runner just logged a run and received the coaching feedback below.
Decide whether their TRAINING PLAN should be restructured because of this run.

Run: {run['distance_km']:.1f} km, pace {_fmt_pace(run['pace_per_km'])}/km, effort {run['effort_level']}/10{recent_summary}{assessment_note}

Coaching feedback summary:
{feedback[:800]}

Adjust the plan ONLY if there is a clear, specific reason — for example:
- Significantly elevated heart rate on an easy/recovery run (suggests fatigue or overreaching — even a single instance is enough)
- Consistent overexertion or underperformance across multiple recent runs
- A new or worsening injury signal
- A significant unexpected fitness leap warranting progression
- Pace or effort drifting far outside the plan's intent

Do NOT adjust for a single run where metrics are within normal variation, or if the athlete is clearly following the plan well.

Reply with JSON only (no explanation outside the JSON):
{{"adjust": true or false, "reason": "one sentence reason — empty string if adjust is false"}}"""

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=120,
        system="You are a conservative running coach assistant. Only recommend plan changes when clearly justified.",
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            try:
                data = json.loads(_extract_json_block(block.text))
                return {"adjust": bool(data.get("adjust")), "reason": str(data.get("reason", ""))}
            except (json.JSONDecodeError, KeyError, ValueError):
                break
    return {"adjust": False, "reason": ""}


_DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def adjust_upcoming_workouts(plan_json: dict, today_day_name: str, reason: str) -> dict:
    """Soften the remaining workouts this week after a fatigue/overreaching signal.

    Calls Claude to modify only the days after today, leaving past workouts untouched.
    Returns the modified plan_json.
    """
    try:
        today_idx = _DAYS_ORDER.index(today_day_name)
    except ValueError:
        return plan_json

    upcoming = [d for d in plan_json.get("days", []) if d.get("day") in _DAYS_ORDER and _DAYS_ORDER.index(d["day"]) > today_idx]
    if not upcoming:
        return plan_json

    prompt = f"""A runner just completed a workout that revealed a fatigue signal: {reason}

The following days remain in their training week and need to be softened for recovery:
{json.dumps(upcoming, indent=2)}

Adjust each day with these rules:
- "Rest" and "Active Recovery" days stay exactly as-is
- "Hard" intensity workouts → change to "Easy" intensity, swap workout_type to "Easy Run" or "Rest" as appropriate
- "Moderate" intensity workouts → reduce to "Easy" intensity, reduce distance_km by 20–25%
- "Easy" intensity workouts → keep the type but reduce distance_km by 10–15%
- Update each day's "notes" field with a brief one-sentence explanation of the change (e.g. "Reduced load for recovery after elevated HR signal")
- Do not change the "day" field

Return ONLY the modified days array as valid JSON — no explanation, no markdown fences."""

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=800,
        system="You are a conservative running coach prioritising athlete recovery. Return only valid JSON.",
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "text":
            modified_upcoming = json.loads(_extract_json_block(block.text))
            if not isinstance(modified_upcoming, list):
                raise ValueError("Claude returned non-list JSON for plan adjustment")
            # Validate day names before reconstructing to catch Claude typos
            invalid = [d.get("day") for d in modified_upcoming if d.get("day") not in _DAYS_ORDER]
            if invalid:
                raise ValueError(f"Claude returned invalid day names: {invalid}")
            past_and_today = [
                d for d in plan_json.get("days", [])
                if d.get("day") in _DAYS_ORDER and _DAYS_ORDER.index(d["day"]) <= today_idx
            ]
            plan_json = dict(plan_json)
            plan_json["days"] = past_and_today + modified_upcoming
            return plan_json
    raise ValueError("No text block returned by Claude for plan adjustment")


def _infer_workout_type(run: dict, recent_runs: list) -> str:
    """Infer workout type from run metrics when no plan is available."""
    effort = run.get("effort_level", 5)
    pace = run.get("pace_per_km", 6.0)
    notes = (run.get("notes") or "").lower()

    # Check notes for explicit keywords — long/lsd must precede easy/recovery
    if any(kw in notes for kw in ["tempo", "threshold"]):
        return "Tempo Run"
    if any(kw in notes for kw in ["interval", "repeat", "rep ", "x ", "400", "800", "1000m", "1km rep"]):
        return "Interval Training"
    if any(kw in notes for kw in ["long run", "lsd"]):
        return "Long Run"
    if any(kw in notes for kw in ["easy", "recovery"]):
        return "Easy Run"

    # Infer from effort and pace relative to recent average
    if recent_runs:
        avg_pace = sum(r["pace_per_km"] for r in recent_runs[:5]) / len(recent_runs[:5])
        pace_diff = avg_pace - pace  # positive = faster than usual
    else:
        avg_pace = pace
        pace_diff = 0

    if effort >= 8 and pace_diff > 0.5:
        return "Interval Training"
    if effort >= 6 and pace_diff > 0.3:
        return "Tempo Run"
    if effort <= 4:
        return "Easy Run"
    if run["distance_km"] >= 15:
        return "Long Run"
    return "Easy Run" if effort <= 5 else "Run"


def _fmt_time_min(time_min: float) -> str:
    """Format decimal minutes as h:mm:ss or mm:ss."""
    total_sec = round(time_min * 60)
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _personal_bests_context(bests: dict) -> str:
    """Format personal bests as a context block for AI prompts.
    Handles both computed bests (has pace_per_km + date) and manual bests (has race_date).
    """
    if not bests:
        return ""
    lines = ["\n## Personal Bests"]
    for race, data in bests.items():
        line = f"- {race}: {_fmt_time_min(data['time_min'])}"
        if data.get("pace_per_km"):
            line += f" (pace {_fmt_pace(data['pace_per_km'])}/km"
            date_val = data.get("date") or data.get("race_date")
            if date_val:
                line += f", achieved {str(date_val)[:10]}"
            line += ")"
        elif data.get("race_date"):
            line += f" (raced {str(data['race_date'])[:10]})"
        lines.append(line)
    return "\n".join(lines)


def generate_run_feedback(
    run: dict,
    recent_runs: list,
    goal: Optional[dict] = None,
    user_profile: Optional[dict] = None,
    assessment: Optional[dict] = None,
    planned_workout: Optional[dict] = None,
    personal_bests: Optional[dict] = None,
    coach_note: Optional[str] = None,
    athlete_summary: Optional[str] = None,
) -> str:
    """Generate AI coaching feedback for a completed run."""
    # Determine workout type context
    if planned_workout and planned_workout.get("workout_type") not in ("Rest", "Active Recovery", None):
        workout_type = planned_workout["workout_type"]
        workout_source = "planned"
    else:
        workout_type = _infer_workout_type(run, recent_runs)
        workout_source = "inferred"

    # Build workout context block
    workout_ctx = f"\n## Today's Workout\n- Type: {workout_type} ({workout_source})"
    if planned_workout:
        if planned_workout.get("title"):
            workout_ctx += f"\n- Planned title: {planned_workout['title']}"
        if planned_workout.get("description"):
            workout_ctx += f"\n- Planned description: {planned_workout['description']}"
        if planned_workout.get("distance_km"):
            workout_ctx += f"\n- Planned distance: {planned_workout['distance_km']:.1f} km"
        if planned_workout.get("duration_min"):
            workout_ctx += f"\n- Planned duration: {planned_workout['duration_min']:.0f} min"
        if planned_workout.get("intensity"):
            workout_ctx += f"\n- Planned intensity: {planned_workout['intensity']}"
        if planned_workout.get("notes"):
            workout_ctx += f"\n- Coach notes: {planned_workout['notes']}"

    is_quality_session = workout_type in ("Tempo Run", "Interval Training")
    notes = run.get("notes") or ""
    has_lap_data = any(kw in notes.lower() for kw in ["lap", "split", "rep", "x ", "400", "800", "1km"])
    coach_note_ctx = f"\n- Athlete note to coach: {coach_note}" if coach_note and coach_note.strip() else ""

    parts = []
    if athlete_summary and athlete_summary.strip():
        parts.append(f"## Athlete Background\n{athlete_summary.strip()}")

    parts.append(f"""## Current Run
- Date: {str(run.get("date", ""))[:10]}
- Workout Type: {workout_type}
- Distance: {run["distance_km"]:.2f} km
- Duration: {run["duration_min"]:.1f} minutes
- Pace: {_fmt_pace(run["pace_per_km"])} min/km
- Heart Rate: {run.get("heart_rate_avg") or "Not recorded"} bpm
- Effort Level: {run["effort_level"]}/10
- Notes: {notes or "None"}{coach_note_ctx}""")

    parts.append(workout_ctx)

    if recent_runs:
        history = "\n## Recent runs (last 5)\n"
        history += "\n".join(_run_to_context_line(r) for r in recent_runs[:5])
        parts.append(history)

    max_hr = (user_profile or {}).get("max_hr")

    zone = _hr_zone_compliance(run, workout_type, planned_workout, max_hr)
    zone_ctx = _hr_zone_context(zone, workout_type)
    if zone_ctx:
        parts.append(zone_ctx)

    trend = _trend_context(recent_runs, max_hr)
    if trend:
        parts.append(trend)

    if goal:
        race_date_str = str(goal["race_date"])[:10]
        try:
            race_date_obj = _date.fromisoformat(race_date_str)
            days_until = max(0, (race_date_obj - _date.today()).days)
            weeks_until = math.ceil(days_until / 7) if days_until > 0 else 0
            timing = f"{weeks_until} weeks ({days_until} days)"
        except Exception:
            timing = "unknown"
        goal_txt = f"\n## Current Goal\n- Race: {goal['race_type']}\n- Race date: {race_date_str}\n- Time until race: {timing}"
        if goal.get("target_time_min"):
            hrs = int(goal["target_time_min"] // 60)
            mins = int(goal["target_time_min"] % 60)
            goal_txt += f"\n- Target time: {hrs}h {mins}m" if hrs else f"\n- Target time: {mins} min"
        if goal.get("goal_description"):
            goal_txt += f"\n- Goal notes: {goal['goal_description']}"
        parts.append(goal_txt)

    if user_profile:
        profile = []
        if user_profile.get("age"):
            profile.append(f"- Age: {user_profile['age']} years")
        if user_profile.get("height_cm"):
            profile.append(f"- Height: {user_profile['height_cm']:.0f} cm")
        if user_profile.get("weight_kg"):
            profile.append(f"- Weight: {user_profile['weight_kg']:.1f} kg")
        if user_profile.get("max_hr"):
            profile.append(f"- Max HR: {user_profile['max_hr']} bpm")
        if profile:
            parts.append("\n## Athlete Profile\n" + "\n".join(profile))

    if assessment:
        parts.append(_assessment_context(assessment))

    if personal_bests:
        parts.append(_personal_bests_context(personal_bests))

    context = "\n".join(parts)

    # Build workout-type-aware prompt
    if workout_type == "Tempo Run":
        p1_instruction = (
            "Paragraph 1 — Tempo Performance: Evaluate this as a TEMPO RUN. "
            "Comment on whether the pace was in the correct threshold zone (typically 15–20 sec/km faster than easy pace), "
            "how the effort level matched tempo expectations, and compare to recent training."
        )
        p2_instruction = (
            "Paragraph 2 — Tempo Quality: Assess pace consistency and lactate threshold execution. "
            "Did they hold the pace well? Was the effort appropriate for a tempo session? "
            + ("Mention the lap/split data they provided." if has_lap_data else
               "Note that sharing lap times or splits in the notes next time will help give better feedback.")
        )
    elif workout_type == "Interval Training":
        p1_instruction = (
            "Paragraph 1 — Interval Performance: Evaluate this as an INTERVAL TRAINING session. "
            "Comment on the overall pace quality, effort consistency, and how it compares to recent training load."
        )
        p2_instruction = (
            "Paragraph 2 — Interval Quality: Assess the intensity and recovery quality. "
            + ("Analyse the split/rep data they provided." if has_lap_data else
               "Ask them to log their rep times and recovery splits in the notes next time — this is critical for tracking interval progression.")
        )
    elif workout_type == "Long Run":
        p1_instruction = (
            "Paragraph 1 — Long Run Performance: Evaluate this as a LONG RUN. "
            "Comment on whether the pace was appropriately easy (long runs should be 60–90 sec/km slower than race pace), "
            "total volume, and aerobic base building."
        )
        p2_instruction = (
            "Paragraph 2 — Endurance Quality: Was the effort sustainable throughout? "
            "Comment on pacing strategy and aerobic efficiency."
        )
    else:
        p1_instruction = (
            "Paragraph 1 — Performance: How did this run go compared to recent form? "
            "Comment on pace, effort level, and whether it matched the athlete's current fitness."
        )
        p2_instruction = (
            "Paragraph 2 — Observation: Call out one specific strength or one concern from this run "
            "(e.g. solid negative split, HR too high for easy pace, strong finish)."
        )

    hr_rule = ""
    if zone and zone["compliance"] in ("compliant", "near-zone"):
        hr_rule = (
            "\nHR EVALUATION RULE (mandatory): The HR Zone Assessment shows this athlete held their HR "
            "in the correct zone. HR compliance is the PRIMARY success metric for this workout type. "
            "If pace was below the planned target, DO NOT frame that as a failure or criticism — "
            "instead acknowledge their HR discipline and explain that pace at this HR will naturally "
            "improve as aerobic fitness develops. Never penalise an athlete for running slowly when "
            "they controlled their heart rate correctly.\n"
        )

    prompt = (
        f"{context}\n\n"
        f"{hr_rule}"
        f"This athlete completed a {workout_type}. Write coaching feedback in 3 short paragraphs — no headings, no bullet points:\n\n"
        f"{p1_instruction}\n\n"
        f"{p2_instruction} If the Pace & HR Trends section is present, reference it specifically — "
        "call out whether pace is trending in the right direction and whether HR is appropriate for the effort and proximity to the goal race date.\n\n"
        "Paragraph 3 — Recovery: Give concrete recovery advice for the next 24 hours "
        "based on the effort level and workout type "
        "(e.g. for tempo/intervals: protein within 30 min, legs-up rest, easy 20-min walk tomorrow; "
        "for easy runs: light stretching, hydration).\n\n"
        "IMPORTANT: Use the exact race date from the Current Goal section — do not reference any other goal or date. "
        "Do NOT suggest the next workout or training session — that is handled separately. "
        "Be direct, specific, and acknowledge the workout type explicitly. Target 120–160 words total."
    )

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=500,
        system=COACH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "text":
            return block.text
    return "Unable to generate feedback at this time."


def generate_workout_variation(
    day: dict,
    recent_runs: list = None,
    goal: Optional[dict] = None,
    assessment: Optional[dict] = None,
) -> Optional[dict]:
    """Generate an alternative workout with the same intensity but a different structure."""
    context = (
        f"Current scheduled workout for {day['day']}:\n"
        f"- Type: {day['workout_type']}\n"
        f"- Title: {day['title']}\n"
        f"- Description: {day['description']}\n"
        f"- Distance: {day['distance_km']} km\n"
        f"- Duration: {day['duration_min']} min\n"
        f"- Intensity: {day['intensity']}\n"
        f"- Notes: {day.get('notes') or 'None'}\n"
    )

    if recent_runs:
        context += "\nRecent training (last 5 runs):\n"
        for r in recent_runs[:5]:
            context += _run_to_context_line(r) + "\n"

    if goal:
        context += f"\nGoal race: {goal['race_type']}\n"

    if assessment:
        context += _assessment_context(assessment)

    day_schema = {
        "type": "object",
        "properties": {
            "workout_type": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "distance_km": {"type": "number"},
            "duration_min": {"type": "number"},
            "intensity": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["workout_type", "title", "description", "distance_km", "duration_min", "intensity", "notes"],
        "additionalProperties": False,
    }

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        system=COACH_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"{context}\n\n"
                "Generate an ALTERNATIVE version of this workout that:\n"
                "1. Keeps the SAME workout_type and intensity level\n"
                "2. Maintains approximately the same distance and duration (±10%)\n"
                "3. Uses a noticeably DIFFERENT structure or format\n"
                "   - e.g. if original is one continuous tempo block, try tempo intervals instead\n"
                "   - e.g. vary the warm-up/cool-down structure, segment lengths, or pace targets\n"
                "   - e.g. if original is track-style, suggest road or trail variation\n"
                "4. Is equally appropriate for this athlete's fitness and goals\n\n"
                "Respond with ONLY valid JSON matching this schema (no markdown, no explanation):\n"
                f"{json.dumps(day_schema, indent=2)}"
            ),
        }],
    )

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                break

    return None


def predict_race_times(
    run_logs: list,
    assessment: Optional[dict] = None,
    user_profile: Optional[dict] = None,
    manual_bests: Optional[dict] = None,
) -> dict:
    """Ask Claude to predict achievable race times based on training data."""
    if not run_logs:
        return {}

    # Build a training summary
    sorted_runs = sorted(run_logs, key=lambda r: r.get("date", ""), reverse=True)
    recent = sorted_runs[:20]

    paces = [r["pace_per_km"] for r in recent if r.get("pace_per_km")]
    avg_pace = sum(paces) / len(paces) if paces else None
    best_pace = min(paces) if paces else None
    total_runs = len(run_logs)
    total_km = sum(r["distance_km"] for r in run_logs)
    recent_km = sum(r["distance_km"] for r in recent)

    context = f"Total runs logged: {total_runs}\nTotal km logged: {total_km:.1f} km\nLast 20 runs total: {recent_km:.1f} km\n"
    if avg_pace:
        context += f"Average recent pace: {_fmt_pace(avg_pace)}/km\n"
    if best_pace:
        context += f"Best recent pace: {_fmt_pace(best_pace)}/km\n"

    context += "\nRecent runs (last 20, newest first):\n"
    for r in recent[:20]:
        context += _run_to_context_line(r) + "\n"

    if assessment:
        context += _assessment_context(assessment) + "\n"

    if user_profile:
        profile_lines = []
        if user_profile.get("age"):
            profile_lines.append(f"- Age: {user_profile['age']} years")
        if user_profile.get("weight_kg"):
            profile_lines.append(f"- Weight: {user_profile['weight_kg']:.1f} kg")
        if user_profile.get("max_hr"):
            profile_lines.append(f"- Max HR: {user_profile['max_hr']} bpm")
        if profile_lines:
            context += "\n## Athlete Profile\n" + "\n".join(profile_lines) + "\n"

    if manual_bests:
        lines = ["\n## User-Reported Personal Bests (official race results)"]
        for race, data in manual_bests.items():
            lines.append(
                f"- {race}: {_fmt_time_min(data['time_min'])}"
                + (f" (raced {data['race_date']})" if data.get("race_date") else "")
            )
        context += "\n".join(lines) + "\n"

    prediction_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "predictions": {
                "type": "object",
                "properties": {
                    "5K":            {"type": "object", "properties": {"time_min": {"type": "number"}, "confidence": {"type": "string"}, "note": {"type": "string"}}, "required": ["time_min", "confidence", "note"]},
                    "10K":           {"type": "object", "properties": {"time_min": {"type": "number"}, "confidence": {"type": "string"}, "note": {"type": "string"}}, "required": ["time_min", "confidence", "note"]},
                    "Half Marathon": {"type": "object", "properties": {"time_min": {"type": "number"}, "confidence": {"type": "string"}, "note": {"type": "string"}}, "required": ["time_min", "confidence", "note"]},
                    "Marathon":      {"type": "object", "properties": {"time_min": {"type": "number"}, "confidence": {"type": "string"}, "note": {"type": "string"}}, "required": ["time_min", "confidence", "note"]},
                },
                "required": ["5K", "10K", "Half Marathon", "Marathon"],
            },
        },
        "required": ["summary", "predictions"],
        "additionalProperties": False,
    }

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=800,
        system=COACH_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"{context}\n\n"
                "Based on this athlete's training history, predict their ACHIEVABLE race times for each standard distance "
                "— not current fitness, but a realistic target they could hit in the NEXT 3–6 months with consistent training.\n\n"
                "Use their best recent paces, volume, effort trends, and any reported personal bests to project times. "
                "Be specific and realistic. For each distance include:\n"
                "- time_min: predicted finish time in decimal minutes\n"
                "- confidence: 'high', 'moderate', or 'low' (based on how closely training aligns to that distance)\n"
                "- note: 1–2 sentences explaining the prediction\n\n"
                "confidence is 'high' only if they have runs close to that distance; 'low' for marathon if they only run short.\n\n"
                "Respond with ONLY valid JSON matching this schema (no markdown, no explanation):\n"
                f"{json.dumps(prediction_schema, indent=2)}"
            ),
        }],
    )

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                break

    return {}


def generate_program_skeleton(
    goal: dict,
    total_weeks: int,
    assessment: Optional[dict] = None,
    user_name: str = "Athlete",
    personal_bests: Optional[dict] = None,
) -> list:
    """Generate a multi-week periodization skeleton covering the full training duration.

    Returns a list of WeekSkeleton dicts (one per week), ordered by week_number.
    Each entry has: week_number, phase, focus, target_km, target_long_run_km, key_workout, notes.
    Does NOT generate day-by-day detail — that is left to generate_weekly_plan().
    """
    context = f"Athlete: {user_name}\n"
    if assessment:
        context += _assessment_context(assessment) + "\n"
    if personal_bests:
        context += _personal_bests_context(personal_bests) + "\n"

    context += f"\nGoal: {goal.get('race_type', 'Goal')} on {goal.get('end_date_str', goal.get('race_date', ''))}\n"
    context += f"Training duration: {total_weeks} weeks (starting this Monday)\n"
    if goal.get("target_time_min"):
        context += f"Target time: {_fmt_time_min(goal['target_time_min'])}\n"
    if goal.get("goal_description"):
        context += f"Goal description: {goal['goal_description']}\n"

    goal_type = goal.get("goal_type", "race")
    if goal_type != "race":
        context += f"Goal type: {goal_type}\n"

    target_value = goal.get("target_value")
    target_unit = goal.get("target_unit", "")
    target_weight_kg = goal.get("target_weight_kg")
    current_weight_kg = goal.get("current_weight_kg")

    if goal_type == "fitness":
        if target_value and target_unit == "km_per_week":
            context += f"Fitness target: build to {target_value:.0f} km/week by end of program\n"
        elif target_value and target_unit == "runs_per_week":
            context += f"Fitness target: run {target_value:.0f} times per week consistently\n"
        else:
            context += "Fitness target: establish consistent running habit and improve aerobic base\n"

    elif goal_type == "speed":
        if target_value and target_unit == "pace_per_km":
            m = int(target_value)
            s = int(round((target_value - m) * 60))
            context += f"Speed target: achieve {m}:{s:02d}/km pace at 5K distance\n"
        else:
            context += "Speed target: improve overall running pace through structured tempo and interval work\n"

    elif goal_type == "endurance":
        if target_value and target_unit == "long_run_km":
            context += f"Endurance target: complete a {target_value:.0f} km long run by end of program\n"
        else:
            context += "Endurance target: progressively build long run distance and weekly volume\n"

    elif goal_type == "weight_loss":
        if target_weight_kg and current_weight_kg:
            gap = current_weight_kg - target_weight_kg
            if gap > 0:
                weekly_deficit_kg = gap / total_weeks
                km_needed = (weekly_deficit_kg * 7700) / 60  # ~7700 kcal/kg fat, ~60 kcal/km
                context += (
                    f"Weight loss target: {current_weight_kg:.1f} kg → {target_weight_kg:.1f} kg "
                    f"({gap:.1f} kg over {total_weeks} weeks)\n"
                    f"Estimated running contribution to weekly deficit: ~{km_needed:.0f} km/week\n"
                    "Important: combine with diet changes; do not prescribe extreme mileage to compensate for diet alone\n"
                    "Plan emphasis: Zone 2 aerobic running (60–70% max HR), frequency over intensity\n"
                )
        else:
            context += "Weight loss target: build consistent aerobic running volume; Zone 2 emphasis for fat burning\n"

    # Phase guidance depends on goal type
    race_goals = {"race", "pb_attempt"}
    if goal.get("goal_type", "race") in race_goals:
        phase_instruction = (
            "Use standard race periodization phases in this order: "
            "Base Building → Build → Peak → Taper. "
            "Taper should be the final 1–2 weeks (lighter volume, sharpening quality). "
            "Peak is the highest-intensity block. "
            "Base Building for the first 30–40% of weeks."
        )
    else:
        phase_instruction = (
            "Use these phases in order: Foundation → Progression → Consolidation. "
            "Foundation: establish consistency and base aerobic fitness. "
            "Progression: steadily increase volume and introduce quality sessions. "
            "Consolidation: reinforce gains, maintain load, polish fitness."
        )

    skeleton_item_schema = {
        "type": "object",
        "properties": {
            "week_number":        {"type": "integer"},
            "phase":              {"type": "string"},
            "focus":              {"type": "string"},
            "target_km":         {"type": "number"},
            "target_long_run_km": {"type": "number"},
            "key_workout":       {"type": "string"},
            "notes":             {"type": "string"},
        },
        "required": ["week_number", "phase", "focus", "target_km", "target_long_run_km", "key_workout", "notes"],
        "additionalProperties": False,
    }
    skeleton_schema = json.dumps({"type": "array", "items": skeleton_item_schema}, indent=2)

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=1800,
        system=COACH_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"{context}\n\n"
                f"Create a {total_weeks}-week training program skeleton. {phase_instruction}\n\n"
                "For each week provide:\n"
                "- week_number: 1-based integer\n"
                "- phase: the periodization phase name\n"
                "- focus: one sentence describing the week's training intent\n"
                "- target_km: total weekly running distance in km (progressive overload — do NOT exceed 10% increase per week except in taper)\n"
                "- target_long_run_km: distance of the longest run that week in km\n"
                "- key_workout: name/description of the most important quality session (e.g. '5×1km intervals at 10K pace')\n"
                "- notes: any specific coaching cues or cautions for that week (empty string if none)\n\n"
                f"Respond with ONLY a valid JSON array of exactly {total_weeks} objects matching this schema (no markdown, no explanation):\n"
                f"{skeleton_schema}"
            ),
        }],
    )

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            try:
                skeleton = json.loads(text)
                if isinstance(skeleton, list) and len(skeleton) > 0:
                    return skeleton
            except json.JSONDecodeError:
                break

    raise ValueError("Skeleton generation failed — Claude returned invalid JSON")


def generate_weekly_plan(
    recent_runs: list,
    goal: Optional[dict] = None,
    user_name: str = "Athlete",
    assessment: Optional[dict] = None,
    coach_notes: Optional[str] = None,
    personal_bests: Optional[dict] = None,
    week_context: Optional[dict] = None,
    athlete_summary: Optional[str] = None,
) -> dict:
    """Generate a 7-day structured training plan as JSON."""
    total_km = sum(r["distance_km"] for r in recent_runs[-14:]) if recent_runs else 0
    avg_effort = (
        sum(r["effort_level"] for r in recent_runs[-7:]) / len(recent_runs[-7:])
        if recent_runs
        else 5
    )

    context = f"Athlete: {user_name}\n"

    if athlete_summary and athlete_summary.strip():
        context += f"\n## Athlete Background\n{athlete_summary.strip()}\n"

    if assessment:
        context += _assessment_context(assessment) + "\n"
    context += f"Total km in last 2 weeks: {total_km:.1f} km\n"
    context += f"Average recent effort: {avg_effort:.1f}/10\n"

    if recent_runs:
        context += "\nRecent training (last 4 weeks):\n"
        for r in sorted(recent_runs[-20:], key=lambda x: x.get("date", "")):
            context += _run_to_context_line(r) + "\n"

        # Extract qualitative notes and feedback from recent runs
        run_qual = []
        for r in recent_runs[:7]:
            date_s = str(r.get("date", ""))[:10]
            if r.get("notes"):
                run_qual.append(f"  {date_s} run notes: {str(r['notes'])[:200]}")
            if r.get("coach_note"):
                run_qual.append(f"  {date_s} pre-run note: {str(r['coach_note'])[:100]}")
            if r.get("ai_feedback"):
                run_qual.append(f"  {date_s} coaching feedback: {str(r['ai_feedback'])[:300]}")
        if run_qual:
            context += "\nRecent qualitative context:\n" + "\n".join(run_qual) + "\n"
    else:
        context += "\nNew athlete — no runs logged yet. Create a beginner-friendly base-building plan.\n"

    if goal:
        try:
            race_date_obj = _date.fromisoformat(str(goal["race_date"])[:10])
            weeks_until = max(0, math.ceil((race_date_obj - _date.today()).days / 7))
        except Exception:
            weeks_until = "unknown"
        context += f"\nGoal race: {goal['race_type']} in {weeks_until} weeks"
        if goal.get("target_time_min"):
            context += f" (target: {goal['target_time_min']:.0f} min)"

    if coach_notes:
        context += f"\n\n## Coach Notes (incorporate these into the plan)\n{coach_notes}\n"

    if personal_bests:
        context += _personal_bests_context(personal_bests) + "\n"

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

    schema_hint = json.dumps(plan_schema, indent=2)

    # If a program skeleton entry exists, prepend it as a hard constraint BEFORE the athlete context
    skeleton_prefix = ""
    if week_context:
        key_workout = week_context.get("key_workout", "")
        skeleton_prefix = (
            f"## MANDATORY PROGRAM CONSTRAINT — read this first\n"
            f"This is Week {week_context.get('week_number', '?')} of {week_context.get('total_weeks', '?')} "
            f"in a structured {week_context.get('total_weeks', '?')}-week training program.\n"
            f"- Phase: {week_context.get('phase', '')}\n"
            f"- Weekly focus: {week_context.get('focus', '')}\n"
            f"- Target total km: {week_context.get('target_km', '?')} km (stay within ±5% of this)\n"
            f"- Target long run: {week_context.get('target_long_run_km', '?')} km\n"
            f"- KEY WORKOUT (MANDATORY): {key_workout}\n"
        )
        if week_context.get("notes"):
            skeleton_prefix += f"- Coaching note: {week_context['notes']}\n"
        skeleton_prefix += (
            f"\nThe key workout '{key_workout}' MUST appear in the 7-day plan — do not omit or replace it.\n"
            "All workouts must reflect the phase and focus above. Weekly total km must respect the target.\n\n"
        )

    response = get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=2500,
        system=COACH_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"{skeleton_prefix}"
                f"## Athlete & Training Context\n{context}\n\n"
                "Create a 7-day training plan (Monday–Sunday). Include all 7 days including rest days.\n"
                "Workout types: Easy Run, Tempo Run, Interval Training, Long Run, Cross Training, Rest, Active Recovery.\n"
                "For Rest and Active Recovery days set distance_km and duration_min to 0.\n"
                "Intensity values: Easy, Moderate, Hard, Rest.\n\n"
                f"Respond with ONLY valid JSON matching this schema (no markdown, no explanation):\n{schema_hint}"
            ),
        }],
    )

    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                break

    return {"week_summary": "Plan generation failed", "total_km": 0, "focus": "", "days": []}
