import { supabase } from './supabaseClient';
import { historyCutoffISODate, parseDate } from '../lib/dates';

// ============================================================
// EDGE FUNCTIONS
// ============================================================

/**
 * Invoke a Supabase Edge Function. Functions answer errors with JSON { error },
 * so surface that message instead of the client's generic "non-2xx status" one.
 */
const invokeFunction = async (name, body = {}) => {
    const { data, error } = await supabase.functions.invoke(name, { body });
    if (error) {
        const details = typeof error.context?.json === 'function'
            ? await error.context.json().catch(() => null)
            : null;
        throw new Error(details?.error || error.message);
    }
    if (data?.error) throw new Error(data.error);
    return data;
};

// ============================================================
// AUTH SERVICES
// ============================================================

/**
 * Register a new user with email, password, and username.
 * Username is stored in user_metadata and auto-copied to profiles table via DB trigger.
 */
export const authRegister = async (username, email, password) => {
    const { data, error } = await supabase.auth.signUp({
        email: email.toLowerCase(),
        password,
        options: {
            data: { username: username.toLowerCase() },
        },
    });
    if (error) throw error;
    return data;
};

/**
 * Sign in with email + password.
 */
export const authLogin = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({
        email: email.toLowerCase(),
        password,
    });
    if (error) throw error;
    return data;
};

/**
 * Sign out the current user.
 */
export const authLogout = async () => {
    const { error } = await supabase.auth.signOut();
    if (error) throw error;
};

/**
 * Permanently delete the current user's account via the delete-account Edge Function:
 * it cancels any Razorpay subscription first, then deletes the auth user, which
 * cascades to profile, categories, transactions and subscription rows.
 * The caller should then clear the local session.
 */
export const deleteAccount = () => invokeFunction('delete-account');

/**
 * Check whether a username is free before signing up.
 * Returns null if the check itself fails, so signup can still proceed.
 */
export const checkUsernameAvailable = async (username) => {
    const { data, error } = await supabase.rpc('is_username_available', {
        p_username: username.trim().toLowerCase(),
    });
    if (error) {
        console.warn('Username availability check failed:', error.message);
        return null;
    }
    return data;
};

/**
 * Update the current user's password (Supabase handles old-password verification internally via session).
 */
export const authChangePassword = async (newPassword) => {
    const { data, error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw error;
    return data;
};

// ============================================================
// PROFILE SERVICES
// ============================================================

/**
 * Get the current user's profile from the profiles table.
 */
export const getProfile = async (userId) => {
    const { data, error } = await supabase
        .from('profiles')
        .select('*')
        .eq('id', userId)
        .single();
    if (error) throw error;
    return data;
};

/**
 * Record what happened to a category suggestion (accepted or overridden), for monitoring and,
 * if the user opted in, retraining. Best-effort: a failure never affects saving.
 */
export const logSuggestionFeedback = async (row) => {
    try {
        await supabase.from('ml_feedback').insert({ kind: 'category_suggestion', ...row });
    } catch {
        // Feedback is optional; ignore network errors or a database without the table yet
    }
};

/**
 * Update the current user's profile.
 */
export const updateProfile = async (userId, updates) => {
    const { data, error } = await supabase
        .from('profiles')
        .update(updates)
        .eq('id', userId)
        .select()
        .single();
    if (error) throw error;
    return data;
};

// ============================================================
// TRANSACTION SERVICES
// ============================================================

// PostgREST caps every response at the project's "max rows" setting (1000 by default)
const FETCH_PAGE_SIZE = 1000;

/**
 * Get all transactions for the current user, with optional type and historyMonths filter.
 * Joins category name from categories table.
 * Fetches in pages: a single request is silently truncated at the max-rows limit.
 */
export const getTransactions = async (filterType = '', historyMonths = null) => {
    const buildQuery = (withCount) => {
        let query = supabase
            .from('transactions')
            .select('*, categories(name)', withCount ? { count: 'exact' } : undefined)
            .order('date', { ascending: false })
            .order('created_at', { ascending: false })
            // Unique tiebreaker so rows sharing a timestamp aren't skipped between pages
            .order('id', { ascending: false });

        if (filterType) {
            query = query.eq('type', filterType);
        }
        if (historyMonths) {
            query = query.gte('date', historyCutoffISODate(historyMonths));
        }
        return query;
    };

    const rows = [];
    let total = Infinity;
    while (rows.length < total) {
        const { data, count, error } = await buildQuery(rows.length === 0)
            .range(rows.length, rows.length + FETCH_PAGE_SIZE - 1);
        if (error) throw error;
        if (typeof count === 'number') total = count;
        if (!data.length) break;
        rows.push(...data);
    }

    // Flatten category name for frontend compatibility
    return rows.map(t => ({
        ...t,
        category_name: t.categories?.name || null,
    }));
};

/**
 * Server-side paginated & filtered transactions query using Supabase .range().
 * Enables high performance for large datasets (>10,000 transactions).
 */
export const getTransactionsPaginated = async ({
    page = 1,
    pageSize = 25,
    type = '',
    categoryId = '',
    startDate = '',
    endDate = '',
    minAmount = null,
    maxAmount = null,
    search = '',
    sortBy = 'date',
    sortAsc = false,
    historyMonths = null,
} = {}) => {
    const from = (page - 1) * pageSize;
    const to = from + pageSize - 1;

    let query = supabase
        .from('transactions')
        .select('*, categories(name)', { count: 'exact' });

    if (type) query = query.eq('type', type);
    if (categoryId) query = query.eq('category_id', categoryId);

    // Apply cutoff limit if user is on restricted plan
    let effectiveStartDate = startDate;
    if (historyMonths) {
        const cutoffStr = historyCutoffISODate(historyMonths);
        if (!effectiveStartDate || effectiveStartDate < cutoffStr) {
            effectiveStartDate = cutoffStr;
        }
    }

    if (effectiveStartDate) query = query.gte('date', effectiveStartDate);
    if (endDate) query = query.lte('date', endDate);
    if (minAmount !== null && minAmount !== '') query = query.gte('amount', parseFloat(minAmount));
    if (maxAmount !== null && maxAmount !== '') query = query.lte('amount', parseFloat(maxAmount));
    if (search) query = query.ilike('title', `%${search}%`);

    query = query
        .order(sortBy, { ascending: sortAsc })
        .range(from, to);

    const { data, count, error } = await query;
    if (error) throw error;

    const formattedData = (data || []).map(t => ({
        ...t,
        category_name: t.categories?.name || null,
    }));

    return {
        data: formattedData,
        count: count || 0,
        page,
        pageSize,
        totalPages: count ? Math.ceil(count / pageSize) : 1,
    };
};

/**
 * Fetch filtered transactions directly from Supabase for date-range CSV exports.
 */
export const getTransactionsFiltered = async ({ startDate = '', endDate = '', type = '', categoryId = '' } = {}) => {
    let query = supabase
        .from('transactions')
        .select('*, categories(name)')
        .order('date', { ascending: false });

    if (type) query = query.eq('type', type);
    if (categoryId) query = query.eq('category_id', categoryId);
    if (startDate) query = query.gte('date', startDate);
    if (endDate) query = query.lte('date', endDate);

    const { data, error } = await query;
    if (error) throw error;

    return (data || []).map(t => ({
        ...t,
        category_name: t.categories?.name || null,
    }));
};

/**
 * Create a new transaction.
 */
export const createTransaction = async (userId, transactionData) => {
    const { data, error } = await supabase
        .from('transactions')
        .insert({ ...transactionData, user_id: userId })
        .select()
        .single();
    if (error) throw error;
    return data;
};

/**
 * Update an existing transaction.
 */
export const updateTransaction = async (id, transactionData) => {
    const { data, error } = await supabase
        .from('transactions')
        .update(transactionData)
        .eq('id', id)
        .select()
        .single();
    if (error) throw error;
    return data;
};

/**
 * Delete a transaction.
 */
export const deleteTransaction = async (id) => {
    const { error } = await supabase
        .from('transactions')
        .delete()
        .eq('id', id);
    if (error) throw error;
};

// ============================================================
// CATEGORY SERVICES
// ============================================================

/**
 * Get all categories (user's own + global defaults).
 * RLS policy handles the filtering.
 */
export const getCategories = async () => {
    const { data, error } = await supabase
        .from('categories')
        .select('*')
        .order('name');
    if (error) throw error;
    return data;
};

/**
 * Create a new category owned by the current user.
 * RLS only accepts rows whose user_id is the caller, so it must be sent.
 */
export const createCategory = async ({ name, color, icon }) => {
    const { data: { session } } = await supabase.auth.getSession();
    const { data, error } = await supabase
        .from('categories')
        .insert({ name, color: color || null, icon: icon || null, user_id: session?.user?.id })
        .select()
        .single();
    if (error) throw error;
    return data;
};

/**
 * Update an existing category.
 */
export const updateCategory = async (id, updates) => {
    const { data, error } = await supabase
        .from('categories')
        .update(updates)
        .eq('id', id)
        .select()
        .single();
    if (error) throw error;
    return data;
};

/**
 * Delete a category.
 * Call getTransactionCountByCategory first to check for linked transactions.
 */
export const deleteCategory = async (id) => {
    const { error } = await supabase
        .from('categories')
        .delete()
        .eq('id', id);
    if (error) throw error;
};

/**
 * Get the count of transactions linked to a category.
 */
export const getTransactionCountByCategory = async (categoryId) => {
    const { count, error } = await supabase
        .from('transactions')
        .select('id', { count: 'exact', head: true })
        .eq('category_id', categoryId);
    if (error) throw error;
    return count ?? 0;
};

/**
 * Reassign all transactions from one category to another.
 * Used before deleting a category that has linked transactions.
 */
export const reassignTransactionsCategory = async (oldCategoryId, newCategoryId) => {
    const { error } = await supabase
        .from('transactions')
        .update({ category_id: newCategoryId })
        .eq('category_id', oldCategoryId);
    if (error) throw error;
};

// ============================================================
// SUMMARY / ANALYTICS (Client-side computation)
// ============================================================

/**
 * Compute a dashboard summary from raw transactions — replaces the Django /transactions/summary/ endpoint.
 * Returns the same shape the frontend expects.
 */
export const computeSummary = (transactions, monthlyBudget = 0) => {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth(); // 0-indexed

    const prevMonth = currentMonth === 0 ? 11 : currentMonth - 1;
    const prevYear = currentMonth === 0 ? currentYear - 1 : currentYear;

    let curIncome = 0, curExpense = 0;
    let prevIncome = 0, prevExpense = 0;
    const categoryTotals = {};

    transactions.forEach(t => {
        const d = parseDate(t.date);
        const amount = parseFloat(t.amount);
        const tMonth = d.getMonth();
        const tYear = d.getFullYear();

        if (tYear === currentYear && tMonth === currentMonth) {
            if (t.type === 'INCOME') curIncome += amount;
            else curExpense += amount;

            // Category breakdown (expenses only, current month)
            if (t.type === 'EXPENSE') {
                const catName = t.category_name || 'Uncategorized';
                categoryTotals[catName] = (categoryTotals[catName] || 0) + amount;
            }
        } else if (tYear === prevYear && tMonth === prevMonth) {
            if (t.type === 'INCOME') prevIncome += amount;
            else prevExpense += amount;
        }
    });

    const budgetLimit = parseFloat(monthlyBudget) || 0;
    const budgetRemaining = budgetLimit - curExpense;

    // Generate insights text
    let insights = '';
    if (prevExpense > 0) {
        const pctChange = ((curExpense - prevExpense) / prevExpense * 100).toFixed(1);
        if (curExpense > prevExpense) {
            insights = `You spent ${pctChange}% more this month compared to last month.`;
        } else if (curExpense < prevExpense) {
            insights = `Great job! You spent ${Math.abs(pctChange)}% less this month compared to last month.`;
        } else {
            insights = 'Your spending is the same as last month.';
        }
    } else if (curExpense > 0) {
        insights = 'This is your first month tracking expenses. Keep it up!';
    }

    const category_breakdown = Object.entries(categoryTotals).map(([name, total]) => ({
        category__name: name,
        total,
    }));

    return {
        current_month: {
            income: curIncome,
            expense: curExpense,
            balance: curIncome - curExpense,
        },
        previous_month: {
            income: prevIncome,
            expense: prevExpense,
        },
        budget: {
            limit: budgetLimit,
            remaining: budgetRemaining,
            exceeded: budgetLimit > 0 && curExpense > budgetLimit,
        },
        insights,
        category_breakdown,
    };
};

// ============================================================
// CSV EXPORT (Client-side)
// ============================================================

/**
 * Quote a CSV text cell. Values starting with = + - @ would run as formulas when
 * the file is opened in Excel/Sheets, so they are prefixed with an apostrophe.
 */
const csvTextCell = (value) => {
    let text = String(value ?? '');
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return `"${text.replace(/"/g, '""')}"`;
};

/**
 * Generate and download a CSV file from transactions array.
 */
// ============================================================
// AI INSIGHTS CACHE
// ============================================================

/**
 * Get cached AI insight for a given user + month ('YYYY-MM').
 * Returns null if not found.
 */
export const getAIInsight = async (userId, month) => {
    const { data, error } = await supabase
        .from('ai_insights')
        .select('insight, generated_at')
        .eq('user_id', userId)
        .eq('month', month)
        .maybeSingle();
    if (error) throw error;
    return data;
};

/**
 * Upsert a cached AI insight for a user + month.
 */
export const saveAIInsight = async (userId, month, insight) => {
    const { error } = await supabase
        .from('ai_insights')
        .upsert({
            user_id: userId,
            month,
            insight,
            generated_at: new Date().toISOString(),
        }, { onConflict: 'user_id,month' });
    if (error) throw error;
};

export const exportTransactionsCSV = (transactions) => {

    const headers = ['Date', 'Title', 'Category', 'Type', 'Amount', 'Notes', 'Is Recurring'];
    const rows = transactions.map(t => [
        t.date,
        csvTextCell(t.title),
        csvTextCell(t.category_name),
        t.type,
        t.amount,
        csvTextCell(t.notes),
        t.is_recurring ? 'Yes' : 'No',
    ]);

    // The byte-order mark makes Excel read the file as UTF-8 (₹, Hindi text, emoji)
    const csv = '\uFEFF' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'transactions.csv');
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
};

// ============================================================
// SUBSCRIPTION SERVICES
// ============================================================

/**
 * Fetch subscription record for the given user.
 */
export const getSubscription = async (userId) => {
    const { data, error } = await supabase
        .from('subscriptions')
        .select('*')
        .eq('user_id', userId)
        .maybeSingle();

    if (error) throw error;
    return data;
};

/**
 * Call razorpay-checkout Edge Function to create a subscription and get subscriptionId + keyId.
 */
export const createCheckoutSubscription = (plan = 'monthly') => invokeFunction('razorpay-checkout', { plan });

/**
 * Call razorpay-cancel Edge Function to cancel subscription at cycle end.
 */
export const cancelSubscription = () => invokeFunction('razorpay-cancel');

/**
 * Call check-plan Edge Function for server-side verification of features and limits.
 */
export const checkUserPlan = () => invokeFunction('check-plan');
