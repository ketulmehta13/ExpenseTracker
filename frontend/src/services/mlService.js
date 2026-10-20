import { supabase } from './supabaseClient';
import { ML_API_URL, ML_ENABLED } from '../lib/features';

/**
 * Client for the self-hosted ML service (ml-service/).
 * Every function resolves to null when the service is off, slow or failing, and never
 * throws: ML features are extras and must never block the rest of the app.
 */

// `raise`: throw an Error with a message to show the user, instead of quietly returning null
async function request(method, path, { body, signal, timeoutMs = 2000, raise = false } = {}) {
    if (!ML_ENABLED) return null;
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) return null;

    // Give up after timeoutMs, or as soon as the caller aborts (e.g. the user kept typing)
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    const isForm = body instanceof FormData; // the browser sets the multipart boundary itself
    try {
        const response = await fetch(`${ML_API_URL}${path}`, {
            method,
            headers: {
                Authorization: `Bearer ${token}`,
                ...(body && !isForm ? { 'Content-Type': 'application/json' } : {}),
            },
            body: isForm ? body : body ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
        if (!response.ok) {
            console.warn(`[mlService] ${path} returned ${response.status}`);
            if (raise) {
                const detail = await response.json().then((json) => json.detail).catch(() => null);
                throw new Error(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.');
            }
            return null;
        }
        return await response.json();
    } catch (err) {
        if (err.name !== 'AbortError') console.warn(`[mlService] ${path} failed:`, err);
        if (raise) {
            if (signal?.aborted) throw new Error('Cancelled.');
            if (err.name === 'AbortError') throw new Error('That took too long. Please try again in a moment.');
            if (err instanceof TypeError) throw new Error("Couldn't reach the server. Check your connection and try again.");
            throw err;
        }
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
    return result?.suggestion ? { ...result.suggestion, model_version: result.model_version } : null;
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
 * The month in two or three sentences: { text, source: 'llm' | 'template' }. Numbers in it are
 * always computed by the service; an LLM, if configured, only words them.
 * @param {string} today - the user's local date, YYYY-MM-DD
 * @param {AbortSignal} [signal]
 */
export async function getInsightsSummary(today, signal) {
    // An LLM may write it, so allow it longer than the cards; the service falls back to a template
    return request('GET', `/v1/insights/summary?today=${encodeURIComponent(today)}`, { signal, timeoutMs: 25000 });
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

/**
 * Send a message to the assistant. Replies: { thread_id, intent, reply, citations,
 * pending: draft transaction waiting for confirmation | null, saved: row | null }.
 * @param {string} message
 * @param {string} threadId - the conversation, so follow-ups like "and last month?" work
 * @param {string} today - the user's local date, YYYY-MM-DD
 */
export async function chatWithAssistant(message, threadId, today, signal) {
    return request('POST', '/v1/assistant/chat', {
        body: { message: message.trim().slice(0, 300), thread_id: threadId, today },
        signal,
        // The free server can take about a minute to wake up; answers are quick once it's awake
        timeoutMs: 75000,
    });
}

/** Answer the assistant's "Should I add this?": approve = true saves the pending transaction. */
export async function confirmAssistantDraft(threadId, approve, today) {
    return request('POST', '/v1/assistant/confirm', {
        body: { thread_id: threadId, approve, today },
        timeoutMs: 10000,
    });
}

/**
 * Read a bill (a photo or a PDF). Resolves to { merchant, date, total, items, groups,
 * suggestion, warnings, lines, ... } for the user to review; nothing is saved. Throws an Error
 * whose message can be shown to the user (unreadable file, no text found, too slow...).
 * @param {File} file - from prepareReceiptFile()
 * @param {string} today - the user's local date, YYYY-MM-DD
 */
export async function scanReceipt(file, today, signal) {
    const form = new FormData();
    form.append('file', file, file.name || 'bill');
    form.append('today', today);
    // Generous: reading a bill is the slowest thing the service does, more so after it wakes up
    return request('POST', '/v1/receipts/scan', { body: form, signal, timeoutMs: 120000, raise: true });
}

/** Wake a sleeping free-plan server ahead of a slow request (fire and forget). */
export function wakeMlService() {
    if (ML_ENABLED) fetch(`${ML_API_URL}/health`).catch(() => {});
}
