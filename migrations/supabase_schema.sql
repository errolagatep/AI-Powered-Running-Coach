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
