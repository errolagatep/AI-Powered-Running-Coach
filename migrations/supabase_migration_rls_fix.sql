-- RLS hardening migration
-- Fixes: strava_tokens, user_personal_bests, user_race_predictions all missing RLS
-- Run this in the Supabase SQL Editor

-- Enable RLS (service role key used by FastAPI bypasses these automatically)
ALTER TABLE strava_tokens          ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_personal_bests    ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_race_predictions  ENABLE ROW LEVEL SECURITY;

-- strava_tokens: owner-only access
CREATE POLICY "strava_tokens: owner only"
    ON strava_tokens
    FOR ALL
    USING (user_id = auth.uid());

-- user_personal_bests: owner-only access
CREATE POLICY "user_personal_bests: owner only"
    ON user_personal_bests
    FOR ALL
    USING (user_id = auth.uid());

-- user_race_predictions: owner-only access
CREATE POLICY "user_race_predictions: owner only"
    ON user_race_predictions
    FOR ALL
    USING (user_id = auth.uid());
