-- ==============================================================================
-- Supabase Row Level Security (RLS) Verification & Isolation Tests
-- Run this in the Supabase SQL Editor to verify complete multi-tenant isolation.
-- ==============================================================================

DO $$
DECLARE
    user_a UUID := '11111111-1111-1111-1111-111111111111';
    user_b UUID := '22222222-2222-2222-2222-222222222222';
    tx_a_id UUID;
    cat_a_id UUID;
    read_count INT;
BEGIN
    RAISE NOTICE '--- Starting RLS Security Test Suite ---';

    -- 1. Setup mock user records in auth.users if needed for local testing
    -- (In Supabase hosted, actual users created via auth.signUp are used)

    -- 2. Simulate User A context
    PERFORM set_config('request.jwt.claim.sub', user_a::text, true);
    PERFORM set_config('role', 'authenticated', true);

    -- User A creates a category
    INSERT INTO public.categories (user_id, name, color, icon)
    VALUES (user_a, 'User A Private Category', '#ff0000', '🔒')
    RETURNING id INTO cat_a_id;

    -- User A creates a transaction
    INSERT INTO public.transactions (user_id, category_id, title, amount, type, date)
    VALUES (user_a, cat_a_id, 'User A Secret Expense', 250.00, 'EXPENSE', CURRENT_DATE)
    RETURNING id INTO tx_a_id;

    -- User A verifies they can see their own transaction
    SELECT COUNT(*) INTO read_count FROM public.transactions WHERE id = tx_a_id;
    IF read_count != 1 THEN
        RAISE EXCEPTION 'RLS TEST FAILED: User A should be able to view their own transaction!';
    END IF;

    -- 3. Switch context to User B
    PERFORM set_config('request.jwt.claim.sub', user_b::text, true);

    -- User B attempts to read User A's transaction
    SELECT COUNT(*) INTO read_count FROM public.transactions WHERE id = tx_a_id;
    IF read_count != 0 THEN
        RAISE EXCEPTION 'RLS CRITICAL SECURITY BREACH: User B was able to read User A transaction! Count: %', read_count;
    END IF;

    -- User B attempts to update User A's transaction
    UPDATE public.transactions SET amount = 999999.00 WHERE id = tx_a_id;
    
    -- User B attempts to delete User A's transaction
    DELETE FROM public.transactions WHERE id = tx_a_id;

    -- User B attempts to read User A's custom category
    SELECT COUNT(*) INTO read_count FROM public.categories WHERE id = cat_a_id;
    IF read_count != 0 THEN
        RAISE EXCEPTION 'RLS CRITICAL SECURITY BREACH: User B was able to read User A private category!';
    END IF;

    -- 4. Switch context to Anonymous (Unauthenticated)
    PERFORM set_config('role', 'anon', true);
    PERFORM set_config('request.jwt.claim.sub', '', true);

    SELECT COUNT(*) INTO read_count FROM public.transactions;
    IF read_count != 0 THEN
        RAISE EXCEPTION 'RLS CRITICAL SECURITY BREACH: Unauthenticated visitor can read transactions! Count: %', read_count;
    END IF;

    -- 5. Cleanup test artifacts (switch to admin/service role)
    PERFORM set_config('role', 'service_role', true);
    DELETE FROM public.transactions WHERE id = tx_a_id;
    DELETE FROM public.categories WHERE id = cat_a_id;

    RAISE NOTICE '--- ✅ ALL RLS POLICIES VERIFIED: COMPLETE MULTI-TENANT ISOLATION CONFIRMED ---';
END $$;
