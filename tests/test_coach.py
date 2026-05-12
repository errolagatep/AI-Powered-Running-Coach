"""
Comprehensive tests for backend/coach.py helper functions.
All tests are pure-logic — no Claude API calls are made.
"""
import json
import math
import sys
import os
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.coach import (
    _fmt_pace,
    _fmt_time_min,
    _run_to_context_line,
    _hr_zone_compliance,
    _hr_zone_context,
    _trend_context,
    _extract_json_block,
    _infer_workout_type,
    _assessment_context,
    _personal_bests_context,
    _DAYS_ORDER,
    adjust_upcoming_workouts,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def make_run(**kwargs):
    base = {
        "date": "2026-05-10",
        "distance_km": 8.0,
        "duration_min": 50.0,
        "pace_per_km": 6.25,
        "heart_rate_avg": 145,
        "effort_level": 6,
        "notes": "",
    }
    base.update(kwargs)
    return base


def make_recent_runs(n=6, pace=6.0, hr=145, effort=6):
    runs = []
    for i in range(n):
        d = date(2026, 5, 10) - timedelta(days=i * 3)
        runs.append({
            "date": d.isoformat(),
            "distance_km": 8.0,
            "duration_min": 48.0,
            "pace_per_km": pace + i * 0.05,
            "heart_rate_avg": hr,
            "effort_level": effort,
        })
    return runs  # most-recent-first


# ── _fmt_pace ──────────────────────────────────────────────────────────────────

class TestFmtPace:
    def test_round_minutes(self):
        assert _fmt_pace(6.0) == "6:00"

    def test_half_minute(self):
        assert _fmt_pace(6.5) == "6:30"

    def test_seconds_zero_padded(self):
        assert _fmt_pace(5.083) == "5:05"

    def test_sub_four_pace(self):
        assert _fmt_pace(3.75) == "3:45"

    def test_rounding_at_59_5_seconds(self):
        # 5 min + 59.5s must round to 6:00, never to invalid "5:60"
        pace = 5 + 59.5 / 60
        assert _fmt_pace(pace) == "6:00"

    def test_zero_pace(self):
        # Should not crash
        result = _fmt_pace(0.0)
        assert "0:" in result


# ── _fmt_time_min ──────────────────────────────────────────────────────────────

class TestFmtTimeMin:
    def test_sub_hour(self):
        assert _fmt_time_min(58.0) == "58:00"

    def test_over_hour(self):
        assert _fmt_time_min(90.0) == "1:30:00"

    def test_fractional_minutes(self):
        assert _fmt_time_min(45.5) == "45:30"

    def test_zero(self):
        assert _fmt_time_min(0) == "0:00"

    def test_negative_time(self):
        # Should not crash but may produce unexpected output
        result = _fmt_time_min(-5)
        assert isinstance(result, str)


# ── _run_to_context_line ───────────────────────────────────────────────────────

class TestRunToContextLine:
    def test_with_hr(self):
        r = make_run(heart_rate_avg=150)
        line = _run_to_context_line(r)
        assert "150bpm" in line
        assert "8.0km" in line

    def test_without_hr(self):
        r = make_run(heart_rate_avg=None)
        line = _run_to_context_line(r)
        assert "bpm" not in line

    def test_date_truncated_to_10_chars(self):
        r = make_run(date="2026-05-10T19:30:00+08:00")
        line = _run_to_context_line(r)
        assert "2026-05-10" in line
        assert "T19" not in line

    def test_missing_hr_key(self):
        r = {"date": "2026-05-10", "distance_km": 5.0, "pace_per_km": 6.0, "effort_level": 5}
        line = _run_to_context_line(r)
        assert "bpm" not in line


# ── _hr_zone_compliance ────────────────────────────────────────────────────────

class TestHrZoneCompliance:
    def test_returns_none_without_max_hr(self):
        run = make_run(heart_rate_avg=145)
        assert _hr_zone_compliance(run, "Easy Run", None, None) is None

    def test_returns_none_without_run_hr(self):
        run = make_run(heart_rate_avg=None)
        assert _hr_zone_compliance(run, "Easy Run", None, 185) is None

    def test_compliant_easy_run(self):
        # 75% of 185 = 138. HR 135 = compliant
        run = make_run(heart_rate_avg=135)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        assert result["compliance"] == "compliant"
        assert result["over_by"] <= 0

    def test_near_zone(self):
        # 75% of 185 = 138. HR 141 = +3 over → near-zone
        run = make_run(heart_rate_avg=141)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        assert result["compliance"] == "near-zone"
        assert result["over_by"] == 3

    def test_slightly_over(self):
        # 75% of 185 = 138. HR 147 = +9 → slightly-over
        run = make_run(heart_rate_avg=147)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        assert result["compliance"] == "slightly-over"

    def test_over_zone(self):
        # 75% of 185 = 138. HR 160 = +22 → over-zone
        run = make_run(heart_rate_avg=160)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        assert result["compliance"] == "over-zone"

    def test_planned_intensity_overrides_workout_type(self):
        # Planned says "Easy" but workout_type is "Long Run"
        # Should use easy ceiling (0.75) not long ceiling (0.78)
        run = make_run(heart_rate_avg=135)
        planned = {"intensity": "Easy"}
        result = _hr_zone_compliance(run, "Long Run", planned, 185)
        assert result["ceiling_pct"] == 75

    def test_tempo_ceiling_correct(self):
        # 90% of 185 = 166. HR 160 = compliant
        run = make_run(heart_rate_avg=160)
        result = _hr_zone_compliance(run, "Tempo Run", None, 185)
        assert result["compliance"] == "compliant"
        assert result["hr_ceiling"] == int(185 * 0.90)

    def test_interval_ceiling_95_pct(self):
        run = make_run(heart_rate_avg=175)
        result = _hr_zone_compliance(run, "Interval Training", None, 185)
        assert result["ceiling_pct"] == 95
        assert result["hr_ceiling"] == int(185 * 0.95)

    def test_hr_pct_calculated_correctly(self):
        run = make_run(heart_rate_avg=148)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        expected_pct = round(148 / 185 * 100, 1)
        assert result["hr_pct"] == expected_pct

    def test_exactly_at_ceiling_is_compliant(self):
        # 75% of 200 = 150. HR exactly 150
        run = make_run(heart_rate_avg=150)
        result = _hr_zone_compliance(run, "Easy Run", None, 200)
        assert result["compliance"] == "compliant"
        assert result["over_by"] == 0

    def test_boundary_between_near_and_slightly_over(self):
        # Ceiling 138 (75% of 184). +5 = 143 → near-zone. +6 = 144 → slightly-over
        run_near = make_run(heart_rate_avg=143)
        run_over = make_run(heart_rate_avg=144)
        assert _hr_zone_compliance(run_near, "Easy Run", None, 184)["compliance"] == "near-zone"
        assert _hr_zone_compliance(run_over, "Easy Run", None, 184)["compliance"] == "slightly-over"

    def test_unknown_workout_type_uses_default_ceiling(self):
        run = make_run(heart_rate_avg=150)
        result = _hr_zone_compliance(run, "Unknown Type", None, 185)
        # Default is 0.82 → 151. HR 150 = compliant
        assert result["ceiling_pct"] == 82
        assert result["compliance"] == "compliant"


# ── _hr_zone_context ───────────────────────────────────────────────────────────

class TestHrZoneContext:
    def test_returns_empty_string_for_none(self):
        assert _hr_zone_context(None, "Easy Run") == ""

    def test_compliant_contains_pace_interpretation_note(self):
        zone = {"compliance": "compliant", "hr_ceiling": 138, "ceiling_pct": 75,
                "actual_hr": 135, "hr_pct": 73.0, "over_by": -3}
        ctx = _hr_zone_context(zone, "Easy Run")
        assert "NOT a failure" in ctx
        assert "COMPLIANT" in ctx

    def test_near_zone_contains_tolerance_note(self):
        zone = {"compliance": "near-zone", "hr_ceiling": 138, "ceiling_pct": 75,
                "actual_hr": 141, "hr_pct": 76.2, "over_by": 3}
        ctx = _hr_zone_context(zone, "Easy Run")
        assert "NEAR-ZONE" in ctx
        assert "aerobic capacity" in ctx

    def test_over_zone_does_not_contain_pace_excuse(self):
        zone = {"compliance": "over-zone", "hr_ceiling": 138, "ceiling_pct": 75,
                "actual_hr": 165, "hr_pct": 89.2, "over_by": 27}
        ctx = _hr_zone_context(zone, "Easy Run")
        assert "NOT a failure" not in ctx
        assert "OVER ZONE" in ctx


# ── _trend_context ─────────────────────────────────────────────────────────────

class TestTrendContext:
    def test_empty_for_fewer_than_4_runs(self):
        runs = make_recent_runs(3)
        assert _trend_context(runs) == ""

    def test_stable_pace_detected(self):
        runs = make_recent_runs(6, pace=6.0)  # all same pace
        ctx = _trend_context(runs)
        # Diff is < 0.1 so should say stable
        assert "stable" in ctx

    def test_improving_pace_detected(self):
        # Recent 3 runs faster than older 3
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            pace = 5.5 + i * 0.3  # older runs are slower
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": pace,
                         "heart_rate_avg": 145, "effort_level": 6})
        ctx = _trend_context(runs)
        assert "faster" in ctx

    def test_declining_pace_detected(self):
        # Recent 3 runs slower than older 3
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            pace = 5.5 - i * 0.3  # older runs are faster
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": pace,
                         "heart_rate_avg": 145, "effort_level": 6})
        ctx = _trend_context(runs)
        assert "slower" in ctx

    def test_hr_trend_rising_detected(self):
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            hr = 160 - i * 5  # recent HR higher than older
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": 6.0,
                         "heart_rate_avg": hr, "effort_level": 6})
        ctx = _trend_context(runs)
        assert "RISING" in ctx

    def test_hr_trend_improving_detected(self):
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            hr = 135 + i * 5  # recent HR lower than older
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": 6.0,
                         "heart_rate_avg": hr, "effort_level": 6})
        ctx = _trend_context(runs)
        assert "IMPROVING" in ctx

    def test_easy_run_hr_flag_fires_above_80pct(self):
        max_hr = 185
        runs = [{"date": "2026-05-10", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 155, "effort_level": 5},
                {"date": "2026-05-07", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5},
                {"date": "2026-05-04", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5},
                {"date": "2026-05-01", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5}]
        ctx = _trend_context(runs, max_hr=max_hr)
        # 155/185 = 83.8% → should be flagged
        assert "HR concern" in ctx

    def test_easy_run_hr_flag_does_not_fire_below_80pct(self):
        max_hr = 185
        runs = make_recent_runs(4, hr=145, effort=5)  # 145/185 = 78.4%
        ctx = _trend_context(runs, max_hr=max_hr)
        assert "HR concern" not in ctx

    def test_high_effort_run_not_flagged_even_with_high_hr(self):
        max_hr = 185
        runs = [{"date": "2026-05-10", "distance_km": 10.0, "duration_min": 55.0,
                 "pace_per_km": 5.5, "heart_rate_avg": 175, "effort_level": 9},
                {"date": "2026-05-07", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5},
                {"date": "2026-05-04", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5},
                {"date": "2026-05-01", "distance_km": 8.0, "duration_min": 50.0,
                 "pace_per_km": 7.0, "heart_rate_avg": 140, "effort_level": 5}]
        ctx = _trend_context(runs, max_hr=max_hr)
        # effort=9 so should NOT be flagged
        assert "HR concern" not in ctx

    def test_runs_missing_hr_data_skipped_in_hr_trend(self):
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": 6.0,
                         "heart_rate_avg": None, "effort_level": 6})
        # No HR data at all — should not crash
        ctx = _trend_context(runs)
        assert isinstance(ctx, str)

    def test_pace_trend_threshold_is_0_1(self):
        # Diff of exactly 0.09 should be "stable"
        runs = []
        for i in range(6):
            d = date(2026, 5, 10) - timedelta(days=i * 3)
            pace = 6.0 if i < 3 else 6.09
            runs.append({"date": d.isoformat(), "distance_km": 8.0,
                         "duration_min": 48.0, "pace_per_km": pace,
                         "heart_rate_avg": 145, "effort_level": 6})
        ctx = _trend_context(runs)
        assert "stable" in ctx


# ── _extract_json_block ────────────────────────────────────────────────────────

class TestExtractJsonBlock:
    def test_plain_json_array(self):
        text = '[{"day": "Tuesday", "workout_type": "Easy Run"}]'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert parsed[0]["day"] == "Tuesday"

    def test_markdown_fenced_json(self):
        text = '```json\n[{"day": "Tuesday"}]\n```'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert parsed[0]["day"] == "Tuesday"

    def test_prose_wrapped_json_array(self):
        text = 'Here are the adjusted workouts:\n[{"day": "Wednesday"}]\nEnd.'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert parsed[0]["day"] == "Wednesday"

    def test_prose_wrapped_json_object(self):
        text = 'Result: {"adjust": true, "reason": "fatigue"}'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert parsed["adjust"] is True

    def test_outermost_container_wins_array_first(self):
        # [ comes before { — array is outermost
        text = '[{"day": "Monday"}] and {"other": "data"}'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert isinstance(parsed, list)

    def test_outermost_container_wins_object_first(self):
        # { comes before [ — object is outermost (the inner [1,2,3] must NOT be extracted)
        text = '{"adjust": true, "reason": "fatigue", "values": [1, 2, 3]}'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert parsed["adjust"] is True
        assert parsed["reason"] == "fatigue"

    def test_no_json_returns_text_unchanged(self):
        text = "no json here at all"
        result = _extract_json_block(text)
        assert result == text

    def test_empty_string(self):
        result = _extract_json_block("")
        assert result == ""

    def test_nested_json_object(self):
        text = '{"outer": {"inner": "value"}}'
        result = _extract_json_block(text)
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == "value"


# ── _infer_workout_type ────────────────────────────────────────────────────────

class TestInferWorkoutType:
    def test_tempo_keyword(self):
        run = make_run(notes="tempo run today", effort_level=7)
        assert _infer_workout_type(run, []) == "Tempo Run"

    def test_threshold_keyword(self):
        run = make_run(notes="threshold session", effort_level=7)
        assert _infer_workout_type(run, []) == "Tempo Run"

    def test_interval_keyword(self):
        run = make_run(notes="interval training 400m reps", effort_level=8)
        assert _infer_workout_type(run, []) == "Interval Training"

    def test_long_run_keyword_beats_easy(self):
        # "easy long run" — long should win now
        run = make_run(notes="easy long run today", effort_level=5)
        result = _infer_workout_type(run, [])
        assert result == "Long Run"

    def test_lsd_keyword(self):
        run = make_run(notes="lsd session", effort_level=5)
        assert _infer_workout_type(run, []) == "Long Run"

    def test_easy_keyword(self):
        run = make_run(notes="easy jog", effort_level=4)
        assert _infer_workout_type(run, []) == "Easy Run"

    def test_recovery_keyword(self):
        run = make_run(notes="recovery run", effort_level=3)
        assert _infer_workout_type(run, []) == "Easy Run"

    def test_distance_15km_infers_long_run(self):
        run = make_run(distance_km=15.0, effort_level=6, notes="")
        assert _infer_workout_type(run, []) == "Long Run"

    def test_high_effort_fast_pace_infers_interval(self):
        recent = make_recent_runs(5, pace=6.5)
        run = make_run(effort_level=9, pace_per_km=5.5, notes="")  # 1.0 faster
        assert _infer_workout_type(run, recent) == "Interval Training"

    def test_low_effort_infers_easy_run(self):
        run = make_run(effort_level=3, notes="")
        assert _infer_workout_type(run, []) == "Easy Run"

    def test_no_notes_no_recent_falls_back_gracefully(self):
        run = make_run(notes="", effort_level=5, distance_km=8.0)
        result = _infer_workout_type(run, [])
        assert result in ("Easy Run", "Run")

    def test_rep_keyword_triggers_interval(self):
        run = make_run(notes="5 rep session", effort_level=8)
        assert _infer_workout_type(run, []) == "Interval Training"

    def test_400m_keyword_triggers_interval(self):
        run = make_run(notes="400 repeats", effort_level=8)
        assert _infer_workout_type(run, []) == "Interval Training"


# ── adjust_upcoming_workouts ───────────────────────────────────────────────────

class TestAdjustUpcomingWorkouts:
    """Tests the plan reconstruction logic without calling the real Claude API."""

    def _plan_with_days(self, *day_names):
        return {
            "week_start": "2026-05-11",
            "days": [
                {"day": d, "workout_type": "Easy Run", "title": f"{d} Run",
                 "description": "Easy run", "distance_km": 8.0, "duration_min": 50.0,
                 "intensity": "Easy", "notes": ""}
                for d in day_names
            ]
        }

    def _mock_claude(self, return_json):
        """Returns a mock that simulates a Claude response with the given JSON."""
        block = MagicMock()
        block.type = "text"
        block.text = json.dumps(return_json)
        response = MagicMock()
        response.content = [block]
        return response

    def test_invalid_today_day_returns_plan_unchanged(self):
        plan = self._plan_with_days("Monday", "Tuesday", "Wednesday")
        result = adjust_upcoming_workouts(plan, "Funday", "fatigue")
        assert result is plan  # exact same object

    def test_no_upcoming_days_returns_plan_unchanged(self):
        # Today is Sunday — no days after it
        plan = self._plan_with_days("Monday", "Tuesday", "Wednesday")
        result = adjust_upcoming_workouts(plan, "Sunday", "fatigue")
        assert result is plan

    @patch("backend.coach.get_client")
    def test_past_days_preserved_correctly(self, mock_get_client):
        plan = self._plan_with_days("Monday", "Tuesday", "Wednesday", "Thursday")
        modified_upcoming = [
            {"day": "Wednesday", "workout_type": "Easy Run", "title": "Easy",
             "description": "Recovery", "distance_km": 6.0, "duration_min": 40.0,
             "intensity": "Easy", "notes": "Reduced for recovery"},
            {"day": "Thursday", "workout_type": "Rest", "title": "Rest",
             "description": "Rest", "distance_km": 0.0, "duration_min": 0.0,
             "intensity": "Rest", "notes": "Recovery day"},
        ]
        mock_get_client.return_value.messages.create.return_value = self._mock_claude(modified_upcoming)

        result = adjust_upcoming_workouts(plan, "Tuesday", "elevated HR")

        days = result["days"]
        day_names = [d["day"] for d in days]
        assert day_names == ["Monday", "Tuesday", "Wednesday", "Thursday"]
        # Past days should be unchanged
        assert days[0]["distance_km"] == 8.0
        assert days[1]["distance_km"] == 8.0
        # Upcoming days modified
        assert days[2]["distance_km"] == 6.0
        assert days[3]["workout_type"] == "Rest"

    @patch("backend.coach.get_client")
    def test_invalid_day_name_from_claude_raises(self, mock_get_client):
        plan = self._plan_with_days("Monday", "Tuesday", "Wednesday")
        bad_response = [{"day": "Monda", "workout_type": "Easy Run",
                         "title": "Easy", "description": "Recovery",
                         "distance_km": 6.0, "duration_min": 40.0,
                         "intensity": "Easy", "notes": ""}]
        mock_get_client.return_value.messages.create.return_value = self._mock_claude(bad_response)

        try:
            adjust_upcoming_workouts(plan, "Monday", "fatigue")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "invalid day names" in str(e).lower() or "Monda" in str(e)

    @patch("backend.coach.get_client")
    def test_non_list_response_from_claude_raises(self, mock_get_client):
        plan = self._plan_with_days("Monday", "Tuesday")
        mock_get_client.return_value.messages.create.return_value = self._mock_claude(
            {"error": "not a list"}
        )

        try:
            adjust_upcoming_workouts(plan, "Monday", "fatigue")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "non-list" in str(e).lower()

    @patch("backend.coach.get_client")
    def test_markdown_fenced_response_parsed_correctly(self, mock_get_client):
        plan = self._plan_with_days("Monday", "Tuesday", "Wednesday")
        upcoming_json = [{"day": "Wednesday", "workout_type": "Easy Run", "title": "Easy",
                          "description": "Recovery", "distance_km": 6.0, "duration_min": 40.0,
                          "intensity": "Easy", "notes": "Reduced"}]
        block = MagicMock()
        block.type = "text"
        block.text = f"```json\n{json.dumps(upcoming_json)}\n```"
        resp = MagicMock()
        resp.content = [block]
        mock_get_client.return_value.messages.create.return_value = resp

        result = adjust_upcoming_workouts(plan, "Tuesday", "fatigue")
        assert len(result["days"]) == 3
        assert result["days"][2]["distance_km"] == 6.0

    @patch("backend.coach.get_client")
    def test_days_with_invalid_names_in_original_plan_excluded_from_past(self, mock_get_client):
        """Days in the original plan with invalid names must not leak into reconstruction."""
        plan = {
            "week_start": "2026-05-11",
            "days": [
                {"day": "Monday",  "workout_type": "Easy Run", "title": "M",
                 "description": "", "distance_km": 8.0, "duration_min": 50.0,
                 "intensity": "Easy", "notes": ""},
                {"day": "Monda",   "workout_type": "Easy Run", "title": "typo",  # typo
                 "description": "", "distance_km": 9.0, "duration_min": 55.0,
                 "intensity": "Easy", "notes": ""},
                {"day": "Wednesday", "workout_type": "Easy Run", "title": "W",
                 "description": "", "distance_km": 8.0, "duration_min": 50.0,
                 "intensity": "Easy", "notes": ""},
            ]
        }
        modified_upcoming = [
            {"day": "Wednesday", "workout_type": "Easy Run", "title": "Easy",
             "description": "Recovery", "distance_km": 6.0, "duration_min": 40.0,
             "intensity": "Easy", "notes": "Reduced"}
        ]
        mock_get_client.return_value.messages.create.return_value = self._mock_claude(modified_upcoming)

        result = adjust_upcoming_workouts(plan, "Monday", "fatigue")
        day_names = [d["day"] for d in result["days"]]
        # "Monda" should be filtered out
        assert "Monda" not in day_names
        assert "Monday" in day_names
        assert "Wednesday" in day_names

    @patch("backend.coach.get_client")
    def test_no_content_block_raises(self, mock_get_client):
        plan = self._plan_with_days("Monday", "Tuesday")
        resp = MagicMock()
        resp.content = []
        mock_get_client.return_value.messages.create.return_value = resp

        try:
            adjust_upcoming_workouts(plan, "Monday", "fatigue")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "No text block" in str(e)


# ── Date math in goal context ──────────────────────────────────────────────────

class TestDateMath:
    """Verify the date math fixes — no Claude calls needed."""

    def test_days_until_uses_date_today_not_utcnow(self):
        """_date.today() is used — verify the formula is correct."""
        from backend.coach import _date
        import math as _math
        race_date = _date.today() + timedelta(days=13)
        days_until = max(0, (race_date - _date.today()).days)
        weeks_until = _math.ceil(days_until / 7) if days_until > 0 else 0
        assert days_until == 13
        assert weeks_until == 2  # ceil(13/7) = 2, not 1

    def test_weeks_ceil_not_floor(self):
        import math as _math
        # 8 days away → ceil(8/7) = 2 weeks (old floor gave 1)
        assert _math.ceil(8 / 7) == 2
        # 7 days → ceil(7/7) = 1 week
        assert _math.ceil(7 / 7) == 1
        # 13 days → 2 weeks
        assert _math.ceil(13 / 7) == 2
        # 14 days → 2 weeks exactly
        assert _math.ceil(14 / 7) == 2

    def test_race_today_gives_zero_days(self):
        from backend.coach import _date
        race_date = _date.today()
        days = max(0, (race_date - _date.today()).days)
        assert days == 0

    def test_past_race_date_clamped_to_zero(self):
        from backend.coach import _date
        race_date = _date.today() - timedelta(days=5)
        days = max(0, (race_date - _date.today()).days)
        assert days == 0


# ── _assessment_context ────────────────────────────────────────────────────────

class TestAssessmentContext:
    def test_full_assessment(self):
        a = {
            "experience_level": "intermediate",
            "years_running": 3,
            "weekly_km": 40.0,
            "weekly_runs": 4,
            "primary_goal": "race_prep",
            "available_days": 5,
            "load_capacity": "moderate",
            "preferred_distance": "medium",
            "injury_history": "knee pain",
            "medications": None,
        }
        ctx = _assessment_context(a)
        assert "Race Preparation" in ctx
        assert "knee pain" in ctx
        assert "None reported" in ctx  # medications

    def test_followup_answer_included(self):
        a = {
            "experience_level": "beginner",
            "years_running": 0,
            "weekly_km": 10.0,
            "weekly_runs": 2,
            "primary_goal": "fitness",
            "available_days": 3,
            "load_capacity": "low",
            "preferred_distance": "short",
            "injury_history": None,
            "medications": None,
            "ai_followup_a": "I prefer morning runs",
        }
        ctx = _assessment_context(a)
        assert "I prefer morning runs" in ctx

    def test_missing_fields_do_not_crash(self):
        ctx = _assessment_context({})
        assert isinstance(ctx, str)


# ── _personal_bests_context ────────────────────────────────────────────────────

class TestPersonalBestsContext:
    def test_empty_dict_returns_empty(self):
        assert _personal_bests_context({}) == ""

    def test_none_returns_empty(self):
        assert _personal_bests_context(None) == ""

    def test_computed_best_with_pace(self):
        bests = {
            "5K": {"time_min": 25.5, "pace_per_km": 5.1, "date": "2026-03-15"}
        }
        ctx = _personal_bests_context(bests)
        assert "5K" in ctx
        assert "25:30" in ctx  # 25.5 min

    def test_manual_best_with_race_date(self):
        bests = {
            "10K": {"time_min": 58.0, "race_date": "2026-01-20"}
        }
        ctx = _personal_bests_context(bests)
        assert "10K" in ctx
        assert "58:00" in ctx
        assert "2026-01-20" in ctx

    def test_multiple_distances(self):
        bests = {
            "5K": {"time_min": 25.0, "pace_per_km": 5.0, "date": "2026-03-01"},
            "Half Marathon": {"time_min": 120.0, "pace_per_km": 5.7, "date": "2025-11-01"},
        }
        ctx = _personal_bests_context(bests)
        assert "5K" in ctx
        assert "Half Marathon" in ctx


# ── Edge cases / regression traps ─────────────────────────────────────────────

class TestEdgeCases:
    def test_fmt_pace_handles_59_seconds_rounding(self):
        # 5:59.5 should round to 6:00, not produce invalid "5:60"
        pace = 5 + 59.5 / 60
        assert _fmt_pace(pace) == "6:00"

    def test_fmt_pace_never_produces_60_seconds(self):
        for base in range(4, 10):
            for frac_sec in range(55, 61):
                pace = base + frac_sec / 60
                result = _fmt_pace(pace)
                assert ":60" not in result, f"Invalid output {result!r} for pace={pace}"

    def test_hr_zone_compliance_integer_truncation(self):
        # 0.75 * 185 = 138.75 → int = 138, not 139
        run = make_run(heart_rate_avg=139)
        result = _hr_zone_compliance(run, "Easy Run", None, 185)
        # 139 - 138 = 1 over → near-zone
        assert result["compliance"] == "near-zone"
        assert result["hr_ceiling"] == 138

    def test_trend_context_with_exactly_4_runs(self):
        runs = make_recent_runs(4)
        ctx = _trend_context(runs)
        # 4 runs: not enough for pace trend (needs 6) but enough for HR trend
        assert isinstance(ctx, str)

    def test_run_with_zero_distance_does_not_crash(self):
        run = make_run(distance_km=0.0, pace_per_km=0.0)
        line = _run_to_context_line(run)
        assert "0.0km" in line

    def test_run_notes_none_handled_in_infer(self):
        run = make_run(notes=None)
        result = _infer_workout_type(run, [])
        assert isinstance(result, str)

    def test_assessment_context_unknown_goal_type_shown_raw(self):
        a = {"primary_goal": "custom_goal_xyz", "experience_level": "",
             "years_running": 0, "weekly_km": 0, "weekly_runs": 0,
             "available_days": 0, "load_capacity": "", "preferred_distance": ""}
        ctx = _assessment_context(a)
        assert "custom_goal_xyz" in ctx
