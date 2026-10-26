import { supabase } from './supabaseClient';
import { ML_API_URL, ML_ENABLED } from '../lib/features';

/**
 * Client for the Financial Copilot (ml-service /v1/copilot).
 * Every call carries the user's Supabase access token; the service reads and writes their data
 * with it, so row level security applies. Errors are thrown as Error objects whose message can
 * be shown to the user; `err.retryable` says whether trying again makes sense.
 */

// The free server can take about a minute to wake up; a streamed answer then arrives quickly
const STREAM_TIMEOUT_MS = 90_000;

class CopilotError extends Error {
    constructor(message, { retryable = true, status = 0 } = {}) {
        super(message);
        this.retryable = retryable;
        this.status = status;
    }
}

async function token() {
    const { data } = await supabase.auth.getSession();
    const value = data.session?.access_token;
    if (!value) throw new CopilotError('Please sign in again.', { retryable: false });
    return value;
}

async function errorFrom(response) {
    const detail = await response.json().then((json) => json.detail).catch(() => null);
    if (response.status === 429) {
        const wait = response.headers.get('retry-after');
        return new CopilotError(`You're sending messages quickly. Try again in ${wait || 'a few'} seconds.`, { status: 429 });
    }
    if (response.status === 401) return new CopilotError('Your session has expired. Please sign in again.', { retryable: false, status: 401 });
    if (response.status === 404) return new CopilotError('That conversation no longer exists.', { retryable: false, status: 404 });
    if (response.status === 422) return new CopilotError(typeof detail === 'string' ? detail : 'Those details aren\'t valid.', { retryable: false, status: 422 });
    return new CopilotError(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.', { status: response.status });
}

async function call(method, path, { body, signal, timeoutMs = 20_000 } = {}) {
    if (!ML_ENABLED) throw new CopilotError('The copilot is not available.', { retryable: false });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    try {
        const response = await fetch(`${ML_API_URL}${path}`, {
            method,
            headers: { Authorization: `Bearer ${await token()}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
            body: body ? JSON.stringify(body) : undefined,
            signal: controller.signal,
        });
        if (!response.ok) throw await errorFrom(response);
        return response.status === 204 ? null : await response.json();
    } catch (err) {
        if (err instanceof CopilotError) throw err;
        if (signal?.aborted) throw new CopilotError('Stopped.', { retryable: true });
        if (err.name === 'AbortError') throw new CopilotError('That took too long. Please try again.');
        throw new CopilotError("Couldn't reach the copilot. Check your connection and try again.");
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
    }
}

/** Parse "event: x\ndata: {...}\n\n" blocks from a text buffer; returns [events, rest]. */
function parseEvents(buffer) {
    const events = [];
    const blocks = buffer.split('\n\n');
    const rest = blocks.pop();
    for (const block of blocks) {
        const event = /^event: (.+)$/m.exec(block)?.[1];
        const data = /^data: (.+)$/m.exec(block)?.[1];
        if (event && data) {
            try { events.push({ event, data: JSON.parse(data) }); } catch { /* ignore a malformed event */ }
        }
    }
    return [events, rest];
}

/**
 * Ask the copilot, streaming the answer.
 * @param {{ message: string, threadId?: string|null, today: string, signal?: AbortSignal,
 *           onMeta?: (meta: {thread_id: string|null}) => void, onDelta?: (text: string) => void }} options
 * @returns {Promise<object>} the final reply: { thread_id, route, reply, blocks, grounded, answered_by, history_saved }
 */
export async function streamCopilot({ message, threadId, today, signal, onMeta, onDelta }) {
    if (!ML_ENABLED) throw new CopilotError('The copilot is not available.', { retryable: false });
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    try {
        const response = await fetch(`${ML_API_URL}/v1/copilot/chat/stream`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${await token()}`, 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, thread_id: threadId || null, today }),
            signal: controller.signal,
        });
        if (!response.ok) throw await errorFrom(response);
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let final = null;
        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const [events, rest] = parseEvents(buffer);
            buffer = rest;
            for (const { event, data } of events) {
                if (event === 'meta') onMeta?.(data);
                else if (event === 'delta') onDelta?.(data.text);
                else if (event === 'final') final = data;
                else if (event === 'error') throw new CopilotError(data.message);
            }
        }
        if (!final) throw new CopilotError('The answer was cut off. Please try again.');
        return final;
    } catch (err) {
        if (err instanceof CopilotError) throw err;
        if (signal?.aborted) throw new CopilotError('Stopped.', { retryable: true });
        if (err.name === 'AbortError') throw new CopilotError('That took too long. The server may be waking up; please try again.');
        throw new CopilotError("Couldn't reach the copilot. Check your connection and try again.");
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
    }
}

/** Run a proposed action the user confirmed (possibly edited). Safe to retry: the key makes it run once. */
export const confirmCopilotAction = ({ action, idempotencyKey, fields, threadId, today }) =>
    call('POST', '/v1/copilot/actions/confirm', {
        body: { action, idempotency_key: idempotencyKey, fields, thread_id: threadId || null, today },
    });

export const listCopilotThreads = () => call('GET', '/v1/copilot/threads');
export const getCopilotThread = (id) => call('GET', `/v1/copilot/threads/${encodeURIComponent(id)}`);
export const deleteCopilotThread = (id) => call('DELETE', `/v1/copilot/threads/${encodeURIComponent(id)}`);
