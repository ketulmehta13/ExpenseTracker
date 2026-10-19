-- Bill scanning: scanned bills are kept privately and linked to the transactions made from them.
--
-- On Save, the app uploads the photo or PDF to receipts/<user id>/<random name> and sets
-- transactions.receipt_path on every transaction created from that bill (a bill split by
-- category shares one file). The bucket is private: users can add, read and delete files only
-- in their own folder, and the app shows a bill through a short-lived signed URL. Deleting the
-- account removes the folder (supabase/functions/delete-account).
-- Re-runnable.

ALTER TABLE public.transactions
    ADD COLUMN IF NOT EXISTS receipt_path text
    CHECK (receipt_path IS NULL OR char_length(receipt_path) BETWEEN 3 AND 300);

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('receipts', 'receipts', false, 10485760,
        ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])
ON CONFLICT (id) DO UPDATE
    SET public = false,
        file_size_limit = EXCLUDED.file_size_limit,
        allowed_mime_types = EXCLUDED.allowed_mime_types;

-- storage.objects already has ROW LEVEL SECURITY enabled by Supabase (and is owned by its storage
-- service, so it isn't altered here); these policies decide who may do what in this bucket.
DROP POLICY IF EXISTS "Users add bills to their own folder" ON storage.objects;
CREATE POLICY "Users add bills to their own folder" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'receipts' AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS "Users read their own bills" ON storage.objects;
CREATE POLICY "Users read their own bills" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'receipts' AND (storage.foldername(name))[1] = auth.uid()::text);

DROP POLICY IF EXISTS "Users delete their own bills" ON storage.objects;
CREATE POLICY "Users delete their own bills" ON storage.objects
    FOR DELETE TO authenticated
    USING (bucket_id = 'receipts' AND (storage.foldername(name))[1] = auth.uid()::text);
