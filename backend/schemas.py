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

    id: int
    email: str
    name: str
    weight_kg: Optional[float] = None
    max_hr: Optional[int] = None
    created_at: datetime


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


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date: datetime
    distance_km: float
    duration_min: float
    pace_per_km: float
    heart_rate_avg: Optional[int] = None
    effort_level: int
    notes: Optional[str] = None
    ai_feedback: Optional[str] = None
    created_at: datetime


# ── Goals ─────────────────────────────────────────────────────────────────────

class GoalCreate(BaseModel):
    race_type: str  # 5K, 10K, HM, Marathon
    race_date: datetime
    target_time_min: Optional[float] = None


class GoalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    race_type: str
    race_date: datetime
    target_time_min: Optional[float] = None
    created_at: datetime
