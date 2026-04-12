# Takbo Running Coach — Claude Reference

## Stack
- **Backend**: FastAPI (Python), Supabase (PostgreSQL), Claude API (`claude-opus-4-6`)
- **Frontend**: Vanilla JS + HTML, Flatpickr for date pickers, CSS variables (`var(--accent)`, `var(--text)`, `var(--text-sec)`)
- **Auth**: JWT via `backend/auth.py` — all API endpoints use `Depends(get_current_user)`
- **Start**: `python run.py`

## Key Files
| File | Purpose |
|---|---|
| `backend/coach.py` | All Claude AI calls: plan gen, feedback, program skeleton |
| `backend/routers/plans.py` | Training plan endpoints |
| `backend/routers/runs.py` | Run log endpoints + gamification |
| `backend/routers/integrations.py` | Strava OAuth + sync |
| `backend/routers/goals.py` | Goal CRUD |
| `backend/schemas.py` | All Pydantic models |
| `migrations/supabase_schema.sql` | Full DB schema (run in Supabase SQL editor) |

## Database Tables
- **users** — id, email, name, password_hash, weight_kg, max_hr, age, height_cm, birthdate, avatar_url
- **run_logs** — id, user_id, date (local date, not UTC), distance_km, duration_min, pace_per_km, heart_rate_avg, effort_level, notes, ai_feedback, strava_activity_id, route_polyline
- **goals** — id, user_id, race_type, race_date, target_time_min, goal_type ('race'|'fitness'|'weight_loss'|'pb_attempt'|'custom'), goal_description
- **training_programs** — id, user_id, goal_id, total_weeks, start_date, end_date, skeleton_json, status ('active'|'completed'|'abandoned')
- **training_plans** — id, user_id, week_start, plan_json, generated_at, program_id (FK → training_programs), week_number
- **runner_assessments** — experience_level, weekly_runs, weekly_km, primary_goal, available_days, load_capacity, injury_history, medications, ai_followup_q/a
- **strava_tokens** — user_id, access_token, refresh_token, expires_at, athlete_id

## Training Program System
- A **training_program** is the parent: full-duration periodization skeleton from today → goal end date
- Each **training_plan** is a weekly child, linked via `program_id` + `week_number`
- `skeleton_json`: JSON array of `{week_number, phase, focus, target_km, target_long_run_km, key_workout, notes}`
- Standard phases — race goals: Base Building → Build → Peak → Taper; non-race: Foundation → Progression → Consolidation
- Week generation is **on-demand** (not all at once): POST `/api/plans/next-week` uses the skeleton entry for that week as context
- Only one program is `active` at a time; creating a new one marks previous as `abandoned`

## Critical Rules
- **Strava dates**: always use `start_date_local` (not `start_date`) to avoid UTC→local date shift
- **Plan dates**: compare as `YYYY-MM-DD` strings, never parse as `Date()` without specifying local components, to avoid timezone shifts
- **Week start**: always the Monday of the current UTC week (`_current_monday()` in plans.py)
- **Backwards compatibility**: `program_id` and `week_number` are nullable on `training_plans` — legacy weekly plans (no program) must keep working
- **Idempotency**: generating next-week checks for existing plan with same `program_id + week_number` before calling Claude

## AI Coaching Functions (`backend/coach.py`)
| Function | Purpose |
|---|---|
| `generate_program_skeleton(goal, total_weeks, assessment, user_name, personal_bests)` | Multi-week periodization outline |
| `generate_weekly_plan(..., week_context)` | 7-day detailed plan; `week_context` from skeleton guides Claude |
| `generate_run_feedback(run, recent_runs, ...)` | Per-run coaching feedback |
| `should_adjust_plan(run, recent_runs, ...)` | Returns `{adjust: bool, reason: str}` |
| `generate_workout_variation(day, ...)` | Alternative workout same intensity |

## Frontend Patterns
- API calls via `api.get/post/patch/delete` in `frontend/js/api.js`
- Auth check: `requireAuth()` at page load; user data from `getUser()`
- Modal pattern: backdrop div with `hidden` class, `onclick="closeModal(event)"` on backdrop, check `e.target === backdrop` inside handler
- Loading state: show `#plan-loading` div, hide `#plan-container`, then swap after response
- `escapeHtml(str)` must be used for any user-generated content rendered as innerHTML
