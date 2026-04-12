-- ============================================================
-- AI Powered Running Coach — Supabase Schema
-- Run this entire file in the Supabase SQL Editor
-- ============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ── Users ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    email        TEXT        UNIQUE NOT NULL,
    name         TEXT        NOT NULL,
    password_hash TEXT       NOT NULL,
    weight_kg    FLOAT,
    max_hr       INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Run Logs ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS run_logs (
    id             UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id        UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date           TIMESTAMPTZ NOT NULL,
    distance_km    FLOAT       NOT NULL,
    duration_min   FLOAT       NOT NULL,
    pace_per_km    FLOAT       NOT NULL,
    heart_rate_avg INTEGER,
    effort_level   INTEGER     NOT NULL CHECK (effort_level BETWEEN 1 AND 10),
    notes          TEXT,
    ai_feedback    TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_run_logs_user_date ON run_logs (user_id, date DESC);

-- ── Goals ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    race_type       TEXT        NOT NULL,
    race_date       TIMESTAMPTZ NOT NULL,
    target_time_min FLOAT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id, created_at DESC);

-- ── Training Plans ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS training_plans (
    id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id      UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start   TIMESTAMPTZ NOT NULL,
    plan_json    TEXT        NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_plans_user ON training_plans (user_id, generated_at DESC);


-- ============================================================
-- Row Level Security (RLS)
-- The FastAPI backend uses the service role key which bypasses
-- RLS. These policies are for future direct client access or
-- if you switch to Supabase Auth.
-- ============================================================

ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE run_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals          ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_plans ENABLE ROW LEVEL SECURITY;

-- Service role (used by FastAPI) bypasses RLS automatically.
-- No policies needed for the backend.


-- ============================================================
-- Onboarding & Gamification Tables
-- ============================================================

-- Runner assessment (1 row per user, upsert on re-assessment)
CREATE TABLE IF NOT EXISTS runner_assessments (
    id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id              UUID        NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    experience_level     TEXT        NOT NULL,  -- 'beginner' | 'intermediate' | 'advanced'
    years_running        FLOAT       NOT NULL,  -- 0, 0.5, 1, 2, 5+
    weekly_runs          INTEGER     NOT NULL,  -- current runs per week
    weekly_km            FLOAT       NOT NULL,  -- current km/week estimate
    primary_goal         TEXT        NOT NULL,  -- 'fitness' | 'speed' | 'endurance' | 'race_prep' | 'weight_loss'
    injury_history       TEXT,                  -- free text, optional
    available_days       INTEGER     NOT NULL,  -- 1–7 days/week
    preferred_distance   TEXT        NOT NULL,  -- 'short' | 'medium' | 'long' | 'mixed'
    load_capacity        TEXT        NOT NULL,  -- 'low' | 'moderate' | 'high'
    ai_followup_q        TEXT,                  -- Claude's clarifying question (may be null)
    ai_followup_a        TEXT,                  -- user's answer to follow-up
    completed_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Gamification state (1 row per user)
CREATE TABLE IF NOT EXISTS user_gamification (
    id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id              UUID        NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    total_xp             INTEGER     DEFAULT 0,
    level                INTEGER     DEFAULT 1,
    current_streak       INTEGER     DEFAULT 0,
    longest_streak       INTEGER     DEFAULT 0,
    last_run_date        DATE,
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Achievements (many per user)
CREATE TABLE IF NOT EXISTS achievements (
    id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id              UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_key      TEXT        NOT NULL,
    title                TEXT        NOT NULL,
    description          TEXT        NOT NULL,
    icon                 TEXT        NOT NULL,
    unlocked_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, achievement_key)
);

CREATE INDEX IF NOT EXISTS idx_achievements_user ON achievements(user_id);
ALTER TABLE runner_assessments  ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_gamification   ENABLE ROW LEVEL SECURITY;
ALTER TABLE achievements        ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- Incremental migrations (run these after the initial schema)
-- ============================================================

-- Fields added after initial schema (skip if already present):
ALTER TABLE users ADD COLUMN IF NOT EXISTS age        INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS height_cm  FLOAT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate  DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id  TEXT;

-- Health info in assessments
ALTER TABLE runner_assessments ADD COLUMN IF NOT EXISTS medications TEXT;

-- Strava integration
ALTER TABLE run_logs ADD COLUMN IF NOT EXISTS strava_activity_id BIGINT;
ALTER TABLE run_logs ADD COLUMN IF NOT EXISTS route_polyline     TEXT;

CREATE TABLE IF NOT EXISTS strava_tokens (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id       UUID        NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    access_token  TEXT        NOT NULL,
    refresh_token TEXT        NOT NULL,
    expires_at    TIMESTAMPTZ NOT NULL,
    athlete_id    BIGINT,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ── Training Programs (full-duration periodized plans) ───────────────────────
CREATE TABLE IF NOT EXISTS training_programs (
    id            UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id       UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    goal_id       UUID        REFERENCES goals(id) ON DELETE SET NULL,
    total_weeks   INTEGER     NOT NULL,
    start_date    DATE        NOT NULL,
    end_date      DATE        NOT NULL,
    skeleton_json TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_training_programs_user
    ON training_programs (user_id, created_at DESC);

ALTER TABLE training_programs ENABLE ROW LEVEL SECURITY;

-- Link weekly plans to their parent program
ALTER TABLE training_plans ADD COLUMN IF NOT EXISTS program_id   UUID REFERENCES training_programs(id) ON DELETE SET NULL;
ALTER TABLE training_plans ADD COLUMN IF NOT EXISTS week_number  INTEGER;

CREATE INDEX IF NOT EXISTS idx_training_plans_program
    ON training_plans (program_id, week_number);

-- Expand goals to support non-race goal types
ALTER TABLE goals ADD COLUMN IF NOT EXISTS goal_type        TEXT NOT NULL DEFAULT 'race';
ALTER TABLE goals ADD COLUMN IF NOT EXISTS goal_description TEXT;

-- Non-race goal quantification targets
-- target_unit: 'km_per_week' | 'pace_per_km' | 'long_run_km' | 'runs_per_week'
ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_value      FLOAT;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_unit       TEXT;
ALTER TABLE goals ADD COLUMN IF NOT EXISTS target_weight_kg  FLOAT;
