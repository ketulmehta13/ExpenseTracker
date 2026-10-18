import { supabase } from './supabaseClient';
import { ML_API_URL, ML_ENABLED } from '../lib/features';

/**
 * Client for the self-hosted ML service (ml-service/).
 * Every function resolves to null when the service is off, slow or failing, and never
 * throws: a suggestion is a nice-to-have and must never block the form.
 */

const TIMEOUT_MS = 2000;

async function postJson(path, body, signal) {
    if (!ML_ENABLED) return null;
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) return null;

    // Give up after TIMEOUT_MS, or as soon as the caller aborts (e.g. the user kept typing)
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    try {
        const response = await fetch(`${ML_API_URL}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify(body),
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
    const result = await postJson(
        '/v1/categorize',
        {
            title: cleanTitle.slice(0, 200),
            amount: Number.isFinite(parsedAmount) && parsedAmount >= 0 ? parsedAmount : null,
            type: type === 'INCOME' ? 'INCOME' : 'EXPENSE',
        },
        signal,
    );
    return result?.suggestion ?? null;
}
