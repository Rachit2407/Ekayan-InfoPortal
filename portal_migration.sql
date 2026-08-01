-- Ekayan Information Portal — Supabase Schema Migration Script
-- Run this in your Supabase Project SQL Editor (https://supabase.com)

CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    organization TEXT,
    deadline DATE,
    description TEXT,
    link TEXT,
    source_url TEXT,
    ai_found_on DATE DEFAULT CURRENT_DATE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS)
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_state ENABLE ROW LEVEL SECURITY;

-- Allow public read access to approved opportunities (so visitors can see them)
CREATE POLICY "Allow public read of approved opportunities" ON opportunities
    FOR SELECT TO public USING (status = 'approved');

-- Allow all operations for public (since it's a demo/prototype, or you can secure it later with Auth)
CREATE POLICY "Allow all operations for everyone" ON opportunities
    FOR ALL TO public USING (true);

-- Allow all operations for public on bot_state (since the bot accesses it anonymously/publicly)
CREATE POLICY "Allow all operations for bot_state" ON bot_state
    FOR ALL TO public USING (true);
