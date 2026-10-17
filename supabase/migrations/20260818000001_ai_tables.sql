-- ==============================================================================
-- Expense Tracker — AI Feature Support Tables
-- Migration Version: 20260818000001
-- ==============================================================================

-- 1. Rate limiting table (per-user, rolling 1-hour window)
CREATE TABLE IF NOT EXISTS public.ai_rate_limits (
    user_id      UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    call_count   INTEGER NOT NULL DEFAULT 0,
    window_start TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);

-- 2. Usage log (append-only; one row per AI feature call)
CREATE TABLE IF NOT EXISTS public.ai_usage_log (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feature    TEXT NOT NULL,  -- 'categorize' | 'parse_transaction' | 'monthly_insight'
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_log_user ON public.ai_usage_log(user_id, created_at DESC);

-- 3. Cached monthly AI insights (keyed by user + YYYY-MM)
CREATE TABLE IF NOT EXISTS public.ai_insights (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id      UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    month        TEXT NOT NULL,          -- Format: 'YYYY-MM'
    insight      TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    CONSTRAINT ai_insights_user_month_unique UNIQUE (user_id, month)
);

-- 4. Enable RLS on all three tables
ALTER TABLE public.ai_rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_usage_log   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_insights    ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies

-- ai_rate_limits: Edge Function uses service role, no client-side policy needed,
-- but add a self-read policy in case we want to expose quota to the UI later.
DROP POLICY IF EXISTS "Users can view their own rate limit" ON public.ai_rate_limits;
CREATE POLICY "Users can view their own rate limit"
    ON public.ai_rate_limits FOR SELECT
    USING (auth.uid() = user_id);

-- ai_usage_log: read-only from client (write happens via Edge Function service role)
DROP POLICY IF EXISTS "Users can view their own usage log" ON public.ai_usage_log;
CREATE POLICY "Users can view their own usage log"
    ON public.ai_usage_log FOR SELECT
    USING (auth.uid() = user_id);

-- ai_insights: users can read and write their own cached insights from the client
DROP POLICY IF EXISTS "Users can view their own insights" ON public.ai_insights;
CREATE POLICY "Users can view their own insights"
    ON public.ai_insights FOR SELECT
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own insights" ON public.ai_insights;
CREATE POLICY "Users can insert their own insights"
    ON public.ai_insights FOR INSERT
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own insights" ON public.ai_insights;
CREATE POLICY "Users can update their own insights"
    ON public.ai_insights FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own insights" ON public.ai_insights;
CREATE POLICY "Users can delete their own insights"
    ON public.ai_insights FOR DELETE
    USING (auth.uid() = user_id);
