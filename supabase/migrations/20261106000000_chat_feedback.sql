-- Thumbs up or down on the chatbot's answers, to see where it falls short.
--
-- Each user can rate only their own answers, once per answer (a later rating replaces the earlier
-- one). Deleting the conversation or the account deletes the rating.
-- Re-runnable.

CREATE TABLE IF NOT EXISTS public.chat_feedback (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    message_id bigint NOT NULL REFERENCES public.chat_messages (id) ON DELETE CASCADE,
    rating text NOT NULL CHECK (rating IN ('up', 'down')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_feedback_message ON public.chat_feedback (message_id);

ALTER TABLE public.chat_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_feedback FROM anon;

DROP POLICY IF EXISTS "Users read their own feedback" ON public.chat_feedback;
CREATE POLICY "Users read their own feedback" ON public.chat_feedback
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users rate their own answers" ON public.chat_feedback;
CREATE POLICY "Users rate their own answers" ON public.chat_feedback
    FOR INSERT TO authenticated WITH CHECK (
        auth.uid() = user_id
        AND EXISTS (SELECT 1 FROM public.chat_messages m WHERE m.id = message_id AND m.user_id = auth.uid())
    );
DROP POLICY IF EXISTS "Users change their own ratings" ON public.chat_feedback;
CREATE POLICY "Users change their own ratings" ON public.chat_feedback
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
