-- Feedback on ML suggestions, for monitoring and retraining.
--
-- Each row records one category suggestion shown in the transaction form and what the user
-- saved: accepted (the suggested category) or overridden (another one). It's an append-only
-- log: users can insert and read their own rows, nobody can edit them, and deleting the
-- account removes them. Retraining (ml-service/training/retrain_categorizer.py) only uses
-- rows from users who opted in with profiles.ai_training_opt_in.
-- Re-runnable.

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS ai_training_opt_in boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS public.ml_feedback (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('category_suggestion')),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    amount numeric(12, 2) CHECK (amount >= 0),
    type text CHECK (type IN ('INCOME', 'EXPENSE')),
    source text NOT NULL CHECK (source IN ('history', 'model', 'llm')),
    suggested_category text,
    suggested_label text,  -- the model's canonical label; null for history matches
    confidence numeric(5, 4) CHECK (confidence BETWEEN 0 AND 1),
    chosen_category text,  -- what the user saved; null for no category
    accepted boolean NOT NULL,
    model_version text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ml_feedback_user_created ON public.ml_feedback (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ml_feedback_kind_created ON public.ml_feedback (kind, created_at DESC);

ALTER TABLE public.ml_feedback ENABLE ROW LEVEL SECURITY;
REVOKE UPDATE, DELETE ON public.ml_feedback FROM anon, authenticated;

DROP POLICY IF EXISTS "Users can insert their own feedback" ON public.ml_feedback;
CREATE POLICY "Users can insert their own feedback" ON public.ml_feedback
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can read their own feedback" ON public.ml_feedback;
CREATE POLICY "Users can read their own feedback" ON public.ml_feedback
    FOR SELECT TO authenticated USING (auth.uid() = user_id);

-- Weekly acceptance rate of suggestions by source. security_invoker: a user sees only their
-- own rows; the dashboard and the service role see everyone's.
CREATE OR REPLACE VIEW public.ml_suggestion_quality WITH (security_invoker = true) AS
SELECT
    date_trunc('week', created_at)::date AS week,
    source,
    count(*) AS shown,
    round(avg(accepted::int), 3) AS acceptance_rate
FROM public.ml_feedback
WHERE kind = 'category_suggestion'
GROUP BY 1, 2;
