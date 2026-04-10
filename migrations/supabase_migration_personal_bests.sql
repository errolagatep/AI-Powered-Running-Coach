-- Personal Bests & AI Predictions migration
-- Run this in Supabase SQL Editor

-- User-entered personal bests (official race results)
CREATE TABLE IF NOT EXISTS user_personal_bests (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  race        TEXT        NOT NULL,          -- '5K' | '10K' | 'Half Marathon' | 'Marathon'
  time_min    FLOAT       NOT NULL,          -- finish time in decimal minutes
  race_date   DATE,                          -- optional: date of the race
  updated_at  TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, race)
);

CREATE INDEX IF NOT EXISTS idx_user_personal_bests_user ON user_personal_bests (user_id);

-- Cached AI race time predictions (one row per user, overwritten on regenerate)
CREATE TABLE IF NOT EXISTS user_race_predictions (
  user_id      UUID        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  predictions  JSONB       NOT NULL,
  generated_at TIMESTAMPTZ DEFAULT NOW()
);
