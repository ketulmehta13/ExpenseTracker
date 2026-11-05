-- The RAG chatbot replaces the Financial Copilot.
--
-- The knowledge base now lives in a FAISS index inside the ML service's image, and the chatbot
-- no longer writes transactions, so the copilot's knowledge and action tables go. Chat history
-- stays: each user reads and writes only their own conversations, and deleting the account
-- deletes them. Works whether or not 20261022000000_copilot.sql was ever applied.
-- Re-runnable.

DROP FUNCTION IF EXISTS public.match_kb_chunks(extensions.vector, integer, text[]);
DROP TABLE IF EXISTS public.kb_chunks;
DROP TABLE IF EXISTS public.kb_documents;
DROP TABLE IF EXISTS public.copilot_actions;
DROP EXTENSION IF EXISTS vector;

CREATE TABLE IF NOT EXISTS public.chat_threads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    title text NOT NULL DEFAULT 'New conversation' CHECK (char_length(title) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id uuid NOT NULL REFERENCES public.chat_threads (id) ON DELETE CASCADE,
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant')),
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 8000),
    blocks jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(blocks) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_threads_user_updated ON public.chat_threads (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_created ON public.chat_messages (thread_id, created_at);

ALTER TABLE public.chat_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.chat_threads, public.chat_messages FROM anon;
REVOKE UPDATE ON public.chat_messages FROM authenticated;  -- messages are never edited

DROP POLICY IF EXISTS "Users read their own threads" ON public.chat_threads;
CREATE POLICY "Users read their own threads" ON public.chat_threads
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users start their own threads" ON public.chat_threads;
CREATE POLICY "Users start their own threads" ON public.chat_threads
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users rename their own threads" ON public.chat_threads;
CREATE POLICY "Users rename their own threads" ON public.chat_threads
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users delete their own threads" ON public.chat_threads;
CREATE POLICY "Users delete their own threads" ON public.chat_threads
    FOR DELETE TO authenticated USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users read their own messages" ON public.chat_messages;
CREATE POLICY "Users read their own messages" ON public.chat_messages
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
-- A message can only be added to a thread the same user owns
DROP POLICY IF EXISTS "Users add messages to their own threads" ON public.chat_messages;
CREATE POLICY "Users add messages to their own threads" ON public.chat_messages
    FOR INSERT TO authenticated WITH CHECK (
        auth.uid() = user_id
        AND EXISTS (SELECT 1 FROM public.chat_threads t WHERE t.id = thread_id AND t.user_id = auth.uid())
    );
DROP POLICY IF EXISTS "Users delete their own messages" ON public.chat_messages;
CREATE POLICY "Users delete their own messages" ON public.chat_messages
    FOR DELETE TO authenticated USING (auth.uid() = user_id);
