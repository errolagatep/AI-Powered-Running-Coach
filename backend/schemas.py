from pydantic import BaseModel, ConfigDict, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    name: str
    password: str
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    onboarding_complete: bool = False


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


# ── Runs ──────────────────────────────────────────────────────────────────────

class RunCreate(BaseModel):
    date: datetime
    distance_km: float
    duration_min: float
    heart_rate_avg: Optional[int] = None
    effort_level: int  # 1-10
    notes: Optional[str] = None


class RunUpdate(BaseModel):
    date: Optional[datetime] = None
    distance_km: Optional[float] = None
    duration_min: Optional[float] = None
    heart_rate_avg: Optional[int] = None
    effort_level: Optional[int] = None
    notes: Optional[str] = None


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    date: datetime
    distance_km: float
    duration_min: float
    pace_per_km: float
    heart_rate_avg: Optional[int] = None
    effort_level: int
    notes: Optional[str] = None
    ai_feedback: Optional[str] = None
    created_at: datetime
    strava_activity_id: Optional[int] = None
    route_polyline: Optional[str] = None
    new_achievements: Optional[List] = None
    plan_adjusted: Optional[bool] = None
    plan_adjustment_reason: Optional[str] = None


# ── Goals ─────────────────────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    race_type: str  # 5K, 10K, HM, Marathon
    race_date: datetime
    target_time_min: Optional[float] = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    race_type: str
    race_date: datetime
    target_time_min: Optional[float] = None
    created_at: datetime


# ── Assessment ────────────────────────────────────────────────

class AssessmentCreate(BaseModel):
    experience_level: str       # 'beginner' | 'intermediate' | 'advanced'
    years_running: float        # 0, 0.5, 1, 2, 5+
    weekly_runs: int            # runs per week currently
    weekly_km: float            # km/week currently
    primary_goal: str           # 'fitness' | 'speed' | 'endurance' | 'race_prep' | 'weight_loss'
    injury_history: Optional[str] = None
    available_days: int         # 1–7
    preferred_distance: str     # 'short' | 'medium' | 'long' | 'mixed'
    load_capacity: str          # 'low' | 'moderate' | 'high'
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    ai_followup_a: Optional[str] = None  # answer to Claude's follow-up question
    race_type: Optional[str] = None      # '5K' | '10K' | 'Half Marathon' | 'Marathon'
    race_date: Optional[str] = None      # ISO date string e.g. '2025-10-12'
    target_time_min: Optional[float] = None  # target finish time in minutes


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    experience_level: str
    years_running: float
    weekly_runs: int
    weekly_km: float
    primary_goal: str
    injury_history: Optional[str] = None
    available_days: int
    preferred_distance: str
    load_capacity: str
    ai_followup_q: Optional[str] = None
    ai_followup_a: Optional[str] = None
    completed_at: datetime


# ── Gamification ──────────────────────────────────────────────

class GamificationResponse(BaseModel):
    total_xp: int
    level: int
    xp_for_current_level: int  # XP threshold at start of this level
    xp_for_next_level: int     # XP threshold for next level
    current_streak: int
    longest_streak: int


class AchievementResponse(BaseModel):
    achievement_key: str
    title: str
    description: str
    icon: str
    unlocked_at: datetime
