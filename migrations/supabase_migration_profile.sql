-- Profile page migration
-- Run this in Supabase SQL Editor

ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS height_cm FLOAT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
