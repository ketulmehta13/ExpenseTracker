-- Financial Copilot: a public knowledge base with vector search, per-user chat history, and an
-- idempotency log for the actions the copilot can take.
--
-- Knowledge base (kb_documents, kb_chunks): financial-education articles and app help, split
-- into chunks with a 384-dimension gte-small embedding each. It holds public material only,
-- never anyone's financial records. Everyone can read it; only the ingestion job writes it,
-- with the service-role key (ml-service/training/ingest_kb.py), so there are no write policies.
--
-- Chat history (chat_threads, chat_messages): each user reads and writes only their own
-- conversations. Deleting the account deletes them (ON DELETE CASCADE from auth.users).
--
-- Actions (copilot_actions): before the copilot saves a transaction or changes the budget it
-- claims the request's idempotency key here, so a retried or double-clicked confirmation can't
-- run twice.
-- Re-runnable.

CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;
GRANT USAGE ON SCHEMA extensions TO anon, authenticated, service_role;  -- Supabase's default, made explicit

-- ── Knowledge base ─────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.kb_documents (
    id text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9/_-]{1,119}$'),  -- e.g. 'finance/budgeting-methods'
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 200),
    source text NOT NULL CHECK (char_length(source) BETWEEN 1 AND 200),  -- who wrote or published it
    source_url text CHECK (source_url IS NULL OR source_url ~ '^https://'),
    topic text NOT NULL CHECK (topic ~ '^[a-z0-9-]{1,40}$'),  -- 'budgeting', 'app-help', ...
    version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.kb_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id text NOT NULL REFERENCES public.kb_documents (id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    section text NOT NULL DEFAULT '' CHECK (char_length(section) <= 200),
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 4000),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    embedding extensions.vector(384) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

-- Cosine distance; at a few hundred chunks an exact scan is just as fast, but this keeps
-- search fast if the knowledge base grows to many thousands
CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding
    ON public.kb_chunks USING hnsw (embedding extensions.vector_cosine_ops);

ALTER TABLE public.kb_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.kb_chunks ENABLE ROW LEVEL SECURITY;
REVOKE INSERT, UPDATE, DELETE ON public.kb_documents, public.kb_chunks FROM anon, authenticated;

DROP POLICY IF EXISTS "Anyone can read the knowledge base" ON public.kb_documents;
CREATE POLICY "Anyone can read the knowledge base" ON public.kb_documents
    FOR SELECT TO anon, authenticated USING (true);

DROP POLICY IF EXISTS "Anyone can read knowledge chunks" ON public.kb_chunks;
CREATE POLICY "Anyone can read knowledge chunks" ON public.kb_chunks
    FOR SELECT TO anon, authenticated USING (true);

-- The chunks closest in meaning to a query embedding, optionally within some topics.
-- SECURITY INVOKER, so the select policies above still apply.
CREATE OR REPLACE FUNCTION public.match_kb_chunks(
    query_embedding extensions.vector(384),
    match_count integer DEFAULT 8,
    topics text[] DEFAULT NULL
)
RETURNS TABLE (
    id bigint,
    document_id text,
    chunk_index integer,
    section text,
    content text,
    metadata jsonb,
    title text,
    source text,
    source_url text,
    topic text,
    version integer,
    similarity double precision
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = ''
AS $$
    SELECT c.id, c.document_id, c.chunk_index, c.section, c.content, c.metadata,
           d.title, d.source, d.source_url, d.topic, d.version,
           1 - (c.embedding OPERATOR(extensions.<=>) query_embedding) AS similarity
    FROM public.kb_chunks c
    JOIN public.kb_documents d ON d.id = c.document_id
    WHERE topics IS NULL OR d.topic = ANY (topics)
    ORDER BY c.embedding OPERATOR(extensions.<=>) query_embedding
    LIMIT least(greatest(match_count, 1), 50);
$$;

GRANT EXECUTE ON FUNCTION public.match_kb_chunks(extensions.vector, integer, text[]) TO anon, authenticated;

-- ── Chat history ───────────────────────────────────────────────────────────────────────────

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

-- ── Idempotent actions ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.copilot_actions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL DEFAULT auth.uid() REFERENCES auth.users (id) ON DELETE CASCADE,
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[A-Za-z0-9_-]{16,64}$'),
    action text NOT NULL CHECK (action IN ('create_transaction', 'update_budget')),
    status text NOT NULL DEFAULT 'started' CHECK (status IN ('started', 'done', 'failed')),
    result jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, idempotency_key)
);

ALTER TABLE public.copilot_actions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.copilot_actions FROM anon;
REVOKE DELETE ON public.copilot_actions FROM authenticated;

DROP POLICY IF EXISTS "Users read their own actions" ON public.copilot_actions;
CREATE POLICY "Users read their own actions" ON public.copilot_actions
    FOR SELECT TO authenticated USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users claim their own actions" ON public.copilot_actions;
CREATE POLICY "Users claim their own actions" ON public.copilot_actions
    FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id AND status = 'started');
DROP POLICY IF EXISTS "Users finish their own actions" ON public.copilot_actions;
CREATE POLICY "Users finish their own actions" ON public.copilot_actions
    FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
