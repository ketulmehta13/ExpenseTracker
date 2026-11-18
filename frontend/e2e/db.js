// Direct Supabase access as the TEST account, for seeding and cleaning up.
// Row level security limits it to that account's own rows.
import { createClient } from '@supabase/supabase-js';
import { loadEnv } from './env.js';

loadEnv();

/** Every row the suite creates starts with this, and cleanup deletes only these rows. */
export const PREFIX = 'E2E ';

export function assertTestAccount() {
    const email = process.env.E2E_EMAIL || '';
    if (!email || !process.env.E2E_PASSWORD) {
        throw new Error('Set E2E_EMAIL and E2E_PASSWORD in frontend/.env.e2e.local (see e2e/README.md).');
    }
    // A guard against pointing the suite at a real account by mistake
    if (!/e2e|test/i.test(email)) {
        throw new Error(`E2E_EMAIL must be a dedicated test account (its address must contain "e2e" or "test"): ${email}`);
    }
}

let clientPromise;

/** A signed-in Supabase client for the test account. */
export function testClient() {
    assertTestAccount();
    clientPromise ??= (async () => {
        const client = createClient(process.env.VITE_SUPABASE_URL, process.env.VITE_SUPABASE_ANON_KEY, {
            auth: { persistSession: false, autoRefreshToken: false },
        });
        const { data, error } = await client.auth.signInWithPassword({
            email: process.env.E2E_EMAIL.toLowerCase(),
            password: process.env.E2E_PASSWORD,
        });
        if (error) throw new Error(`Test account sign-in failed: ${error.message}`);
        return { client, userId: data.user.id };
    })();
    return clientPromise;
}

export async function categoryId(name) {
    const { client } = await testClient();
    const { data, error } = await client.from('categories').select('id,name').ilike('name', name).limit(1);
    if (error) throw error;
    return data[0]?.id ?? null;
}

/** Insert transactions; titles get the E2E prefix. */
export async function seed(rows) {
    const { client, userId } = await testClient();
    const { data, error } = await client
        .from('transactions')
        .insert(rows.map((r) => ({ notes: '', is_recurring: false, ...r, title: PREFIX + r.title, user_id: userId })))
        .select();
    if (error) throw error;
    return data;
}

/** Delete every transaction the suite created. */
export async function cleanup() {
    const { client } = await testClient();
    const { error } = await client.from('transactions').delete().like('title', `${PREFIX}%`);
    if (error) throw error;
}

/** Sum of every transaction of the account, by type, straight from the database. */
export async function dbTotals() {
    const { client } = await testClient();
    const totals = { income: 0, expense: 0, count: 0 };
    for (let from = 0; ; from += 1000) {
        const { data, error } = await client.from('transactions').select('type,amount').range(from, from + 999);
        if (error) throw error;
        for (const t of data) {
            totals[t.type === 'INCOME' ? 'income' : 'expense'] += Number(t.amount);
            totals.count += 1;
        }
        if (data.length < 1000) break;
    }
    return totals;
}

export async function getProfile() {
    const { client, userId } = await testClient();
    const { data, error } = await client.from('profiles').select('*').eq('id', userId).single();
    if (error) throw error;
    return data;
}

export async function updateProfile(updates) {
    const { client, userId } = await testClient();
    const { error } = await client.from('profiles').update(updates).eq('id', userId);
    if (error) throw error;
}

/** Today in the browser's time zone (Asia/Kolkata), as YYYY-MM-DD. */
export const todayIST = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());

/** "₹1,23,456.78" or "−₹50.00" -> number */
export const money = (text) => {
    const negative = /[-−]/.test(text);
    const value = Number(String(text).replace(/[^0-9.]/g, ''));
    return negative ? -value : value;
};
