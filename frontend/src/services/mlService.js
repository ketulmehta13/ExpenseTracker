import { supabase } from './supabaseClient';
import { ML_API_URL, ML_ENABLED } from '../lib/features';

/**
 * Client for the self-hosted ML service (ml-service/).
 * Every function resolves to null when the service is off, slow or failing, and never
 * throws: ML features are extras and must never block the rest of the app.
 */

async function request(method, path, { body, signal, timeoutMs = 2000 } = {}) {
    if (!ML_ENABLED) return null;
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) return null;

    // Give up after timeoutMs, or as soon as the caller aborts (e.g. the user kept typing)
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    try {
        const response = await fetch(`${ML_API_URL}${path}`, {
            method,
            headers: {
                Authorization: `Bearer ${token}`,
                ...(body ? { 'Content-Type': 'application/json' } : {}),
            },
            body: body ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
        if (!response.ok) {
            console.warn(`[mlService] ${path} returned ${response.status}`);
            return null;
        }
        return await response.json();
    } catch (err) {
        if (err.name !== 'AbortError') console.warn(`[mlService] ${path} failed:`, err);
        return null;
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
    }
}

/**
 * Suggest a category for a transaction being entered.
 * @param {{ title: string, amount?: string|number, type?: 'INCOME'|'EXPENSE' }} input
 * @param {AbortSignal} [signal]
 * @returns {Promise<{ category_id: number|string|null, category_name: string, label: string|null,
 *                     confidence: number, source: 'history'|'model' } | null>}
 *   category_id is null when the user has no category for the suggested label yet.
 */
export async function suggestCategoryML({ title, amount, type }, signal) {
    const cleanTitle = title?.trim() ?? '';
    if (cleanTitle.length < 3) return null;
    const parsedAmount = parseFloat(amount);
    const result = await request('POST', '/v1/categorize', {
        body: {
            title: cleanTitle.slice(0, 200),
            amount: Number.isFinite(parsedAmount) && parsedAmount >= 0 ? parsedAmount : null,
            type: type === 'INCOME' ? 'INCOME' : 'EXPENSE',
        },
        signal,
    });
    return result?.suggestion ?? null;
}

/**
 * Turn one line ("swiggy 450 yesterday") into a transaction draft, with a category suggestion.
 * @param {string} text
 * @param {string} today - the user's local date, YYYY-MM-DD, for words like "yesterday"
 * @param {AbortSignal} [signal]
 * @returns {Promise<{ title: string, amount: number|null, date: string, type: 'INCOME'|'EXPENSE',
 *                     found: { amount: boolean, date: boolean, type: boolean },
 *                     suggestion: object|null } | null>}
 */
export async function parseQuickAdd(text, today, signal) {
    const clean = text?.trim() ?? '';
    if (!clean) return null;
    return request('POST', '/v1/parse', { body: { text: clean.slice(0, 300), today }, signal, timeoutMs: 4000 });
}

/**
 * Spending insights: unusual payments, recurring payments and the month-end forecast.
 * @param {string} today - the user's local date, YYYY-MM-DD
 * @param {AbortSignal} [signal]
 * @returns {Promise<{ as_of: string, unusual: object[], recurring: object[],
 *                     recurring_monthly_total: number, forecast: object|null } | null>}
 */
export async function getInsights(today, signal) {
    // The first call reads a year of history, so allow more time than for suggestions
    return request('GET', `/v1/insights?today=${encodeURIComponent(today)}`, { signal, timeoutMs: 8000 });
}
