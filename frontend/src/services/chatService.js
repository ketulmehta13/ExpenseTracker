import { supabase } from './supabaseClient';
import { ML_API_URL, ML_ENABLED } from '../lib/features';

/**
 * Client for the chatbot (ml-service /chat). Every call carries the user's Supabase access
 * token; the Groq key stays on the server. Errors are thrown with a message to show the user,
 * and `err.retryable` says whether trying again makes sense.
 */

// The free server can take about a minute to wake up; after that, answers arrive quickly
const STREAM_TIMEOUT_MS = 90_000;
const CALL_TIMEOUT_MS = 20_000;

class ChatError extends Error {
    constructor(message, retryable = true) {
        super(message);
        this.retryable = retryable;
    }
}

async function authHeader() {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new ChatError('Please sign in again.', false);
    return { Authorization: `Bearer ${token}` };
}

async function errorFrom(response) {
    const detail = await response.json().then((json) => json.detail).catch(() => null);
    if (response.status === 429) {
        const wait = response.headers.get('retry-after');
        return new ChatError(`You're sending messages quickly. Try again in ${wait || 'a few'} seconds.`);
    }
    if (response.status === 401) return new ChatError('Your session has expired. Please sign in again.', false);
    if (response.status === 404) return new ChatError('That conversation no longer exists.', false);
    return new ChatError(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.');
}

/** Run fetch with a timeout and the caller's abort signal, turning failures into ChatErrors. */
async function withTimeout(timeoutMs, signal, run) {
    if (!ML_ENABLED) throw new ChatError('The chatbot is not available.', false);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const abort = () => controller.abort();
    signal?.addEventListener('abort', abort);
    try {
        return await run(controller.signal);
    } catch (err) {
        if (err instanceof ChatError) throw err;
        if (signal?.aborted) throw new ChatError('Stopped.');
        if (err.name === 'AbortError') throw new ChatError('That took too long. The server may be waking up; please try again.');
        throw new ChatError("Couldn't reach the chatbot. Check your connection and try again.");
    } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
    }
}

async function call(method, path) {
    return withTimeout(CALL_TIMEOUT_MS, null, async (signal) => {
        const response = await fetch(`${ML_API_URL}${path}`, { method, headers: await authHeader(), signal });
        if (!response.ok) throw await errorFrom(response);
        return response.status === 204 ? null : response.json();
    });
}

/**
 * Ask a question, streaming the answer.
 * @returns {Promise<object>} { thread_id, reply, sources, blocks, suggestions, answered_by, message_id, history_saved }
 */
export function streamChat({ message, threadId, today, signal, onDelta, onReset }) {
    return withTimeout(STREAM_TIMEOUT_MS, signal, async (abortSignal) => {
        const response = await fetch(`${ML_API_URL}/chat/stream`, {
            method: 'POST',
            headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, thread_id: threadId || null, today }),
            signal: abortSignal,
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
            const blocks = buffer.split('\n\n');
            buffer = blocks.pop();
            for (const block of blocks) {
                const event = /^event: (.+)$/m.exec(block)?.[1];
                const data = /^data: (.+)$/m.exec(block)?.[1];
                if (!event || !data) continue;
                const payload = JSON.parse(data);
                if (event === 'delta') onDelta?.(payload.text);
                else if (event === 'reset') onReset?.();
                else if (event === 'final') final = payload;
                else if (event === 'error') throw new ChatError(payload.message);
            }
        }
        if (!final) throw new ChatError('The answer was cut off. Please try again.');
        return final;
    });
}

/** A thumbs up or down on one of the user's own answers. */
export const sendFeedback = (messageId, rating) => withTimeout(CALL_TIMEOUT_MS, null, async (signal) => {
    const response = await fetch(`${ML_API_URL}/chat/feedback`, {
        method: 'POST',
        headers: { ...(await authHeader()), 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId, rating }),
        signal,
    });
    if (!response.ok) throw await errorFrom(response);
});

export const listThreads = () => call('GET', '/chat/threads');
export const getThread = (id) => call('GET', `/chat/threads/${encodeURIComponent(id)}`);
export const deleteThread = (id) => call('DELETE', `/chat/threads/${encodeURIComponent(id)}`);
