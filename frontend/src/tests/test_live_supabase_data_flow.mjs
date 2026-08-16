import { createClient } from '@supabase/supabase-js';

const SUPABASE_URL = 'https://jpqugklwytdytznvvsjf.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable__Zsg-_OORoEXK7Clg7mCLQ_nxhU7Fz8';

const supabase1 = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { persistSession: false }
});
const supabase2 = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: { persistSession: false }
});

const timestamp = Date.now();
const user1Email = `test_user_1_${timestamp}@expensetracker.dev`;
const user2Email = `test_user_2_${timestamp}@expensetracker.dev`;
const testPassword = 'Password123!@#';

const results = {};

async function runVerification() {
    console.log('================================================================');
    console.log('EXPENSE TRACKER — SECTION 3: SUPABASE DATA & AUTH VERIFICATION');
    console.log('================================================================\n');

    try {
        // -------------------------------------------------------------
        // STEP 1: Create a fresh test account through Register flow
        // -------------------------------------------------------------
        console.log(`[Step 1] Registering User 1: ${user1Email}...`);
        const { data: authData1, error: authError1 } = await supabase1.auth.signUp({
            email: user1Email,
            password: testPassword,
            options: { data: { username: `user1_${timestamp}` } }
        });

        if (authError1) throw new Error(`Registration failed: ${authError1.message}`);
        const user1Id = authData1.user?.id;
        console.log(`✓ User 1 registered successfully (ID: ${user1Id})`);
        results['Step 1 - Register Fresh Account'] = { pass: true, detail: `User 1 created: ${user1Id}` };

        // -------------------------------------------------------------
        // STEP 2: Log in and confirm empty state on dashboard
        // -------------------------------------------------------------
        console.log(`\n[Step 2] Logging in as User 1 and checking empty state...`);
        const { data: loginData1, error: loginError1 } = await supabase1.auth.signInWithPassword({
            email: user1Email,
            password: testPassword,
        });
        if (loginError1) throw new Error(`Login failed: ${loginError1.message}`);

        const { data: initialTxs, error: initialTxsError } = await supabase1
            .from('transactions')
            .select('*');

        if (initialTxsError) throw new Error(`Fetch transactions failed: ${initialTxsError.message}`);
        const isEmpty = (initialTxs || []).length === 0;
        console.log(`✓ Initial transactions count: ${initialTxs.length} (Empty State: ${isEmpty})`);
        results['Step 2 - Login & Verify Empty State'] = {
            pass: isEmpty,
            detail: `User has 0 transactions on clean dashboard.`
        };

        // -------------------------------------------------------------
        // STEP 3: Add at least 3 transactions (income + expense, different categories)
        // -------------------------------------------------------------
        console.log(`\n[Step 3] Adding 3 test transactions for User 1...`);
        // Fetch available categories
        const { data: categories } = await supabase1.from('categories').select('*').limit(3);
        const cat1 = categories?.[0]?.id || null;
        const cat2 = categories?.[1]?.id || null;

        const txPayloads = [
            { user_id: user1Id, title: 'Freelance Design Payment', amount: 45000.00, type: 'INCOME', category_id: cat1, date: '2026-08-01', notes: 'Client invoice #101' },
            { user_id: user1Id, title: 'Monthly Grocery Run', amount: 3250.50, type: 'EXPENSE', category_id: cat2, date: '2026-08-05', notes: 'Supermarket' },
            { user_id: user1Id, title: 'High-speed Internet Bill', amount: 999.00, type: 'EXPENSE', category_id: cat2, date: '2026-08-10', notes: 'Broadband' },
        ];

        const createdTxs = [];
        for (const tx of txPayloads) {
            const { data: created, error: createError } = await supabase1
                .from('transactions')
                .insert(tx)
                .select()
                .single();
            if (createError) throw new Error(`Failed to create transaction "${tx.title}": ${createError.message}`);
            createdTxs.push(created);
            console.log(`  + Created: [${created.type}] ${created.title} - ₹${created.amount} (ID: ${created.id})`);
        }

        results['Step 3 - Add 3 Transactions (Income & Expense)'] = {
            pass: createdTxs.length === 3,
            detail: `Successfully created ${createdTxs.length} transactions across categories.`
        };

        // -------------------------------------------------------------
        // STEP 4: Refresh/Refetch and confirm all 3 transactions persist
        // -------------------------------------------------------------
        console.log(`\n[Step 4] Querying Supabase for User 1 transactions...`);
        const { data: refreshedTxs, error: refetchError } = await supabase1
            .from('transactions')
            .select('*, categories(name)')
            .order('date', { ascending: false });

        if (refetchError) throw new Error(`Refetch failed: ${refetchError.message}`);
        const allAttributed = refreshedTxs.every(t => t.user_id === user1Id);
        console.log(`✓ Retrieved ${refreshedTxs.length} transactions from Supabase database.`);
        console.log(`✓ All transactions attributed to User 1: ${allAttributed}`);
        results['Step 4 - Verify Transactions Persist & Scoped'] = {
            pass: refreshedTxs.length === 3 && allAttributed,
            detail: `Found ${refreshedTxs.length}/3 transactions, all user_id = ${user1Id}.`
        };

        // -------------------------------------------------------------
        // STEP 5: Log out, log back in, confirm data persists
        // -------------------------------------------------------------
        console.log(`\n[Step 5] Logging out and logging back in as User 1...`);
        await supabase1.auth.signOut();
        const { error: reLoginError } = await supabase1.auth.signInWithPassword({
            email: user1Email,
            password: testPassword,
        });
        if (reLoginError) throw new Error(`Re-login failed: ${reLoginError.message}`);

        const { data: recheckTxs, error: recheckError } = await supabase1
            .from('transactions')
            .select('*');
        if (recheckError) throw new Error(`Recheck query failed: ${recheckError.message}`);

        const persistsAcrossSessions = recheckTxs.length === 3;
        console.log(`✓ Transactions count after re-login: ${recheckTxs.length}`);
        results['Step 5 - Persistence Across Logout & Re-login'] = {
            pass: persistsAcrossSessions,
            detail: `Data persists across authentication sessions in Supabase database.`
        };

        // -------------------------------------------------------------
        // STEP 6: Create second account & verify RLS multi-tenant isolation
        // -------------------------------------------------------------
        console.log(`\n[Step 6] Creating User 2 (${user2Email}) & Testing RLS Isolation...`);
        const { data: authData2, error: authError2 } = await supabase2.auth.signUp({
            email: user2Email,
            password: testPassword,
            options: { data: { username: `user2_${timestamp}` } }
        });
        if (authError2) throw new Error(`User 2 signup failed: ${authError2.message}`);
        const user2Id = authData2.user?.id;

        // User 2 queries transactions table
        const { data: user2Txs, error: user2QueryError } = await supabase2
            .from('transactions')
            .select('*');
        if (user2QueryError) throw new Error(`User 2 query failed: ${user2QueryError.message}`);

        const user2SeesZero = (user2Txs || []).length === 0;
        console.log(`✓ User 2 query result count: ${user2Txs.length} (Expected 0)`);
        if (!user2SeesZero) {
            console.error(`🚨 CRITICAL SECURITY VULNERABILITY: User 2 can see ${user2Txs.length} transactions from User 1!`);
        } else {
            console.log(`✓ RLS Policy Verified: User 2 CANNOT see User 1's transactions!`);
        }

        results['Step 6 - RLS Isolation (User 2 Cannot See User 1 Data)'] = {
            pass: user2SeesZero,
            detail: user2SeesZero
                ? `100% data isolation confirmed: User 2 sees 0 transactions from User 1.`
                : `CRITICAL: User 2 was able to view User 1 data.`
        };

        // -------------------------------------------------------------
        // STEP 7: Edit a transaction and confirm persistence
        // -------------------------------------------------------------
        const txToEdit = createdTxs[0];
        console.log(`\n[Step 7] Editing transaction ${txToEdit.id}...`);
        const updatedTitle = 'Freelance UI/UX Retainer (Updated)';
        const updatedAmount = 52000.00;

        const { data: updatedTx, error: updateError } = await supabase1
            .from('transactions')
            .update({ title: updatedTitle, amount: updatedAmount })
            .eq('id', txToEdit.id)
            .select()
            .single();

        if (updateError) throw new Error(`Update failed: ${updateError.message}`);

        // Re-fetch to confirm update persisted in DB
        const { data: refetchedUpdatedTx } = await supabase1
            .from('transactions')
            .select('*')
            .eq('id', txToEdit.id)
            .single();

        const updateConfirmed = refetchedUpdatedTx.title === updatedTitle && parseFloat(refetchedUpdatedTx.amount) === updatedAmount;
        console.log(`✓ Updated title: "${refetchedUpdatedTx.title}", amount: ₹${refetchedUpdatedTx.amount}`);
        results['Step 7 - Edit Transaction & Verify Persistence'] = {
            pass: updateConfirmed,
            detail: `Transaction successfully updated and persisted in Supabase.`
        };

        // -------------------------------------------------------------
        // STEP 8: Delete a transaction and confirm removal from Supabase
        // -------------------------------------------------------------
        const txToDelete = createdTxs[1];
        console.log(`\n[Step 8] Deleting transaction ${txToDelete.id} (${txToDelete.title})...`);
        const { error: deleteError } = await supabase1
            .from('transactions')
            .delete()
            .eq('id', txToDelete.id);

        if (deleteError) throw new Error(`Delete failed: ${deleteError.message}`);

        // Query again to confirm it no longer exists
        const { data: remainingTxs } = await supabase1
            .from('transactions')
            .select('*');

        const deletedConfirmed = remainingTxs.length === 2 && !remainingTxs.some(t => t.id === txToDelete.id);
        console.log(`✓ Remaining transactions in DB: ${remainingTxs.length}/2 (Deleted item removed: ${deletedConfirmed})`);
        results['Step 8 - Delete Transaction & Verify Supabase Removal'] = {
            pass: deletedConfirmed,
            detail: `Transaction permanently removed from Supabase table.`
        };

        // Cleanup: remove remaining test records
        console.log(`\n[Cleanup] Removing test transactions...`);
        for (const t of remainingTxs) {
            await supabase1.from('transactions').delete().eq('id', t.id);
        }
        console.log(`✓ Test cleanup complete.\n`);

    } catch (err) {
        console.error('Test Execution Error:', err);
    }

    console.log('================================================================');
    console.log('FINAL SECTION 3 TEST REPORT');
    console.log('================================================================');
    console.table(results);
}

runVerification();
