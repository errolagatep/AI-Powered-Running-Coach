-- Run this in your Supabase project: SQL Editor → New query
-- Adds Google Sign-In and Strava integration support

-- 1. Allow Google-only accounts (no password)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS google_id TEXT UNIQUE,
  ALTER COLUMN password_hash DROP NOT NULL;

-- 2. Store Strava OAuth tokens per user
CREATE TABLE IF NOT EXISTS strava_tokens (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  access_token  TEXT NOT NULL,
  refresh_token TEXT NOT NULL,
  expires_at    TIMESTAMPTZ NOT NULL,
  athlete_id    BIGINT UNIQUE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Track which run_logs came from Strava (prevents duplicate imports)
ALTER TABLE run_logs
  ADD COLUMN IF NOT EXISTS strava_activity_id BIGINT UNIQUE;

-- 4. Store encoded route polyline for Strava-imported runs
ALTER TABLE run_logs
  ADD COLUMN IF NOT EXISTS route_polyline TEXT;
