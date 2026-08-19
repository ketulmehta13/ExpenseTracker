-- ==============================================================================
-- Expense Tracker — Razorpay Subscriptions Schema
-- Migration Version: 20260819000001
-- ==============================================================================

-- 1. SUBSCRIPTIONS TABLE
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id                        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                   UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    plan                      TEXT NOT NULL DEFAULT 'free'
                                CHECK (plan IN ('free', 'pro_monthly', 'pro_yearly')),
    status                    TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'pending')),
    razorpay_subscription_id  TEXT UNIQUE,
    current_period_end        TIMESTAMPTZ,
    trial_end                 TIMESTAMPTZ,
    grace_period_end          TIMESTAMPTZ,   -- set when payment fails; downgrade after this
    created_at                TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW()),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_razorpay_id ON public.subscriptions(razorpay_subscription_id)
    WHERE razorpay_subscription_id IS NOT NULL;

-- 2. WEBHOOK EVENTS LOG (append-only; never delete — needed for debugging)
CREATE TABLE IF NOT EXISTS public.webhook_events_log (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type       TEXT NOT NULL,
    razorpay_event_id TEXT,
    payload          JSONB,
    processed_at     TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_type ON public.webhook_events_log(event_type, processed_at DESC);

-- 3. UPDATED_AT TRIGGER for subscriptions
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc', NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_subscriptions_updated_at ON public.subscriptions;
CREATE TRIGGER set_subscriptions_updated_at
    BEFORE UPDATE ON public.subscriptions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 4. HELPER FUNCTION: get_user_plan(uid)
-- Returns the effective plan info for a user. Used by Edge Functions and can
-- be called server-side in RLS policies for future use.
CREATE OR REPLACE FUNCTION public.get_user_plan(uid UUID)
RETURNS TABLE (
    plan        TEXT,
    status      TEXT,
    is_pro      BOOLEAN,
    trial_end   TIMESTAMPTZ,
    period_end  TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.plan,
        s.status,
        -- A user is "pro" if they have an active/trialing pro plan, OR are in grace period
        (
            s.plan IN ('pro_monthly', 'pro_yearly')
            AND s.status IN ('active', 'trialing', 'past_due')
            AND (s.status != 'past_due' OR (s.grace_period_end IS NOT NULL AND s.grace_period_end > NOW()))
        ) AS is_pro,
        s.trial_end,
        s.current_period_end
    FROM public.subscriptions s
    WHERE s.user_id = uid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

-- 5. TRIGGER: auto-create Free plan row on new user signup
CREATE OR REPLACE FUNCTION public.handle_new_subscription()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.subscriptions (user_id, plan, status)
    VALUES (NEW.id, 'free', 'active')
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_subscription ON auth.users;
CREATE TRIGGER on_auth_user_subscription
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_subscription();

-- 6. BACKFILL: create Free plan rows for any existing users who don't have one
INSERT INTO public.subscriptions (user_id, plan, status)
SELECT id, 'free', 'active'
FROM auth.users
WHERE id NOT IN (SELECT user_id FROM public.subscriptions)
ON CONFLICT (user_id) DO NOTHING;

-- 7. RLS ENFORCEMENT
ALTER TABLE public.subscriptions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_events_log ENABLE ROW LEVEL SECURITY;

-- Subscriptions: users can only SELECT their own row.
-- All writes go through Edge Functions using the service role key (bypasses RLS).
DROP POLICY IF EXISTS "Users can view their own subscription" ON public.subscriptions;
CREATE POLICY "Users can view their own subscription"
    ON public.subscriptions FOR SELECT
    USING (auth.uid() = user_id);

-- Webhook events log: no client access at all (service role only)
-- No SELECT policy = no client access.
