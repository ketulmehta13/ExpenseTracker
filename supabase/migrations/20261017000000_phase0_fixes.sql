-- ==============================================================================
-- Expense Tracker — Phase 0 fixes: categories, signup, subscriptions
-- Migration Version: 20261017000000
-- ==============================================================================

-- 1. CATEGORIES

-- The app inserts categories without user_id; default it to the caller so the
-- insert policy (auth.uid() = user_id) accepts the row.
ALTER TABLE public.categories ALTER COLUMN user_id SET DEFAULT auth.uid();

-- A plain UNIQUE (name, user_id) never conflicts on NULL user_id, so re-running the
-- default seed duplicated the global categories. Merge duplicates into the oldest row.
CREATE TEMP TABLE category_dupes AS
SELECT id, keep_id
FROM (
    SELECT id, FIRST_VALUE(id) OVER (PARTITION BY name ORDER BY created_at, id) AS keep_id
    FROM public.categories
    WHERE user_id IS NULL
) ranked
WHERE id <> keep_id;

UPDATE public.transactions t
SET category_id = d.keep_id
FROM category_dupes d
WHERE t.category_id = d.id;

DELETE FROM public.categories c
USING category_dupes d
WHERE c.id = d.id;

DROP TABLE category_dupes;

ALTER TABLE public.categories DROP CONSTRAINT IF EXISTS categories_name_user_unique;
ALTER TABLE public.categories
    ADD CONSTRAINT categories_name_user_unique UNIQUE NULLS NOT DISTINCT (name, user_id);

-- 2. SIGNUP: USERNAMES

-- Lets the register form check a username before signing up (profiles is not
-- readable by anonymous users).
CREATE OR REPLACE FUNCTION public.is_username_available(p_username TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT NOT EXISTS (
        SELECT 1 FROM public.profiles WHERE username = LOWER(TRIM(p_username))
    );
$$;

REVOKE ALL ON FUNCTION public.is_username_available(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_username_available(TEXT) TO anon, authenticated;

-- A username collision used to abort the whole signup ("Database error saving new
-- user"). Keep the account and fall back to a suffixed username instead.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    base_username TEXT := LOWER(COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)));
BEGIN
    BEGIN
        INSERT INTO public.profiles (id, username, first_name, last_name)
        VALUES (
            NEW.id,
            base_username,
            NEW.raw_user_meta_data->>'first_name',
            NEW.raw_user_meta_data->>'last_name'
        )
        ON CONFLICT (id) DO NOTHING;
    EXCEPTION WHEN unique_violation THEN
        INSERT INTO public.profiles (id, username, first_name, last_name)
        VALUES (
            NEW.id,
            base_username || '_' || SUBSTR(MD5(NEW.id::TEXT), 1, 6),
            NEW.raw_user_meta_data->>'first_name',
            NEW.raw_user_meta_data->>'last_name'
        )
        ON CONFLICT (id) DO NOTHING;
    END;
    RETURN NEW;
END;
$$;

-- 3. SUBSCRIPTIONS

-- Cancelling now schedules the end of the subscription instead of revoking Pro
-- immediately; the subscription.cancelled webhook flips the status later.
ALTER TABLE public.subscriptions
    ADD COLUMN IF NOT EXISTS cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE;

-- The return type changes, so the function must be dropped first.
DROP FUNCTION IF EXISTS public.get_user_plan(UUID);

CREATE FUNCTION public.get_user_plan(uid UUID)
RETURNS TABLE (
    plan                 TEXT,
    status               TEXT,
    is_pro               BOOLEAN,
    trial_end            TIMESTAMPTZ,
    period_end           TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT
        s.plan,
        s.status,
        COALESCE(
            s.plan IN ('pro_monthly', 'pro_yearly')
            AND (
                s.status IN ('active', 'trialing')
                -- Payment failed: keep Pro during the grace period
                OR (s.status = 'past_due' AND s.grace_period_end > NOW())
                -- Cancelled: keep Pro until the paid (or trial) period ends
                OR (s.status = 'canceled' AND s.current_period_end > NOW())
            ),
            FALSE
        ) AS is_pro,
        s.trial_end,
        s.current_period_end,
        s.cancel_at_period_end
    FROM public.subscriptions s
    WHERE s.user_id = uid;
$$;

-- Only Edge Functions (service role) look up plans; users must not be able to
-- query another user's plan by passing an arbitrary uid.
REVOKE ALL ON FUNCTION public.get_user_plan(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_user_plan(UUID) TO service_role;

ALTER FUNCTION public.handle_new_subscription() SET search_path = public;

-- The plan context listens for realtime changes on the user's subscription row,
-- which only works if the table is part of the realtime publication.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime')
       AND NOT EXISTS (
           SELECT 1 FROM pg_publication_tables
           WHERE pubname = 'supabase_realtime'
             AND schemaname = 'public'
             AND tablename = 'subscriptions'
       ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.subscriptions;
    END IF;
END $$;

-- 4. WEBHOOK EVENTS LOG

-- The webhook skips events it has already processed (Razorpay retries deliveries).
CREATE INDEX IF NOT EXISTS idx_webhook_events_event_id
    ON public.webhook_events_log(razorpay_event_id)
    WHERE razorpay_event_id IS NOT NULL;

-- 5. ROW LEVEL SECURITY stays enabled on every table touched above
ALTER TABLE public.categories         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webhook_events_log ENABLE ROW LEVEL SECURITY;
