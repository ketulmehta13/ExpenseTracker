import { supabase } from './supabaseClient';

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

/**
 * Get all transactions for the current user, with optional type filter.
 * Joins category name from categories table.
 */
export const getTransactions = async (filterType = '') => {
    let query = supabase
        .from('transactions')
        .select('*, categories(name)')
        .order('date', { ascending: false })
        .order('created_at', { ascending: false });

    if (filterType) {
        query = query.eq('type', filterType);
    }

    const { data, error } = await query;
    if (error) throw error;

    // Flatten category name for frontend compatibility
    return data.map(t => ({
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
        const d = new Date(t.date);
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
 * Generate and download a CSV file from transactions array.
 */
export const exportTransactionsCSV = (transactions) => {
    const headers = ['Date', 'Title', 'Category', 'Type', 'Amount', 'Notes', 'Is Recurring'];
    const rows = transactions.map(t => [
        t.date,
        `"${(t.title || '').replace(/"/g, '""')}"`,
        `"${(t.category_name || '').replace(/"/g, '""')}"`,
        t.type,
        t.amount,
        `"${(t.notes || '').replace(/"/g, '""')}"`,
        t.is_recurring ? 'Yes' : 'No',
    ]);

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
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