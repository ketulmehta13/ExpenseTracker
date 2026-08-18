import { supabase } from './supabaseClient';

/**
 * Thin, safe wrapper around the ai-proxy Supabase Edge Function.
 * All functions return null / { error } on failure — never throw.
 * This ensures every AI feature degrades gracefully.
 */

async function invokeAI(type, payload) {
    try {
        const { data, error } = await supabase.functions.invoke('ai-proxy', {
            body: { type, payload },
        });

        if (error) {
            console.warn(`[aiService] ${type} error:`, error.message);
            return null;
        }

        return data;
    } catch (err) {
        console.warn(`[aiService] ${type} exception:`, err);
        return null;
    }
}

/**
 * Suggest a category for a transaction title.
 * @param {string} title - transaction description typed by user
 * @param {string[]} categories - names of the user's existing categories
 * @returns {{ category: string, confidence: string } | null}
 */
export async function suggestCategory(title, categories = []) {
    if (!title || title.trim().length < 3) return null;
    const result = await invokeAI('categorize', { title, categories });
    if (!result || result.error || !result.category) return null;
    return result;
}

/**
 * Parse a natural-language string into structured transaction data.
 * @param {string} text - e.g. "spent 450 on groceries yesterday"
 * @returns {{ type, amount, description, category, date, confidence } | { error: string } | null}
 */
export async function parseTransaction(text) {
    if (!text || text.trim().length < 3) return null;
    const result = await invokeAI('parse_transaction', { text });
    return result ?? null;
}

/**
 * Generate a plain-English monthly insight from aggregated summary data.
 * Only passes totals — NOT raw transaction records — to keep payload small and private.
 * @param {{ currentMonth, previousMonth, month }} summaryData
 * @returns {{ insight: string } | null}
 */
export async function getMonthlyInsight(summaryData) {
    const result = await invokeAI('monthly_insight', summaryData);
    if (!result || result.error || !result.insight) return null;
    return result;
}
