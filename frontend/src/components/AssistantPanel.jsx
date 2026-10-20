import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Bot, Loader2, RotateCcw, Send, X } from 'lucide-react';
import { chatWithAssistant, confirmAssistantDraft, wakeMlService } from '../services/mlService';
import { formatCurrency, formatDate } from '../lib/formatters';
import { todayISODate } from '../lib/dates';

/**
 * AssistantPanel — a chat with the ML service's assistant: questions about your spending,
 * budget and subscriptions, help with the app, and adding transactions after you confirm.
 * Rendered only when the ML service is configured.
 */

const SUGGESTIONS = [
    'How much did I spend on food this month?',
    'Am I on track with my budget?',
    'What subscriptions do I have?',
    'Add 450 swiggy yesterday',
    'How do I export to PDF?',
];

const newThreadId = () => (crypto.randomUUID?.() ?? `${Date.now()}${Math.random()}`).replace(/[^A-Za-z0-9]/g, '').slice(0, 32);

const UNREACHABLE = "I can't reach the assistant right now. Please try again in a moment.";

const Message = ({ message, onConfirm, busy }) => {
    if (message.role === 'user') {
        return (
            <div className="flex justify-end">
                <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm text-primary-foreground">
                    {message.text}
                </p>
            </div>
        );
    }
    const { pending } = message;
    return (
        <div className="flex flex-col items-start gap-1.5">
            <p className="max-w-[90%] rounded-2xl rounded-bl-md bg-muted px-3.5 py-2 text-sm text-foreground whitespace-pre-line">
                {message.text}
            </p>
            {message.citations?.length > 0 && (
                <p className="pl-1 text-[11px] text-muted-foreground">
                    From help: {message.citations.map((c) => `${c.title} › ${c.section}`).join(' · ')}
                </p>
            )}
            {pending && (
                <div className="w-[90%] rounded-2xl border border-border bg-card p-3.5 text-sm">
                    <div className="flex items-baseline justify-between gap-3">
                        <span className="font-semibold text-foreground truncate">{pending.title}</span>
                        <span className={`font-bold tabular-nums ${pending.type === 'INCOME' ? 'text-income' : 'text-expense'}`}>
                            {pending.type === 'INCOME' ? '+' : '−'}{formatCurrency(pending.amount)}
                        </span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                        {formatDate(pending.date)} · {pending.category_name ?? 'No category'}
                    </p>
                    {message.awaiting && (
                        <div className="mt-3 flex gap-2">
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => onConfirm(false)}
                                className="flex-1 rounded-xl border border-border py-2 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                disabled={busy}
                                onClick={() => onConfirm(true)}
                                className="flex-1 rounded-xl bg-primary py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                            >
                                Save
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

const AssistantPanel = () => {
    const [open, setOpen] = useState(false);
    const [threadId, setThreadId] = useState(newThreadId);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const [slow, setSlow] = useState(false); // a reply is taking long: the server is probably waking up
    const inputRef = useRef(null);
    const endRef = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        wakeMlService(); // start waking a sleeping server while the user types
        setTimeout(() => inputRef.current?.focus(), 50);
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('keydown', onKey);
        return () => document.removeEventListener('keydown', onKey);
    }, [open]);

    useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [messages, busy]);

    useEffect(() => {
        if (!busy) return undefined;
        const timer = setTimeout(() => setSlow(true), 6000);
        return () => clearTimeout(timer);
    }, [busy]);

    // Only the latest pending draft can still be confirmed
    const settlePending = (list) => list.map((m) => (m.awaiting ? { ...m, awaiting: false } : m));

    const send = async (text) => {
        const message = text.trim();
        if (!message || busy) return;
        setInput('');
        setMessages((list) => [...settlePending(list), { role: 'user', text: message }]);
        setBusy(true);
        let result = await chatWithAssistant(message, threadId, todayISODate());
        // One retry: a dropped connection while the server woke up shouldn't need the user to resend
        if (!result) result = await chatWithAssistant(message, threadId, todayISODate());
        setBusy(false);
        setSlow(false);
        setMessages((list) => [...list, result
            ? { role: 'assistant', text: result.reply, citations: result.citations, pending: result.pending, awaiting: Boolean(result.pending) }
            : { role: 'assistant', text: UNREACHABLE }]);
    };

    const confirm = async (approve) => {
        setBusy(true);
        const result = await confirmAssistantDraft(threadId, approve, todayISODate());
        setBusy(false);
        setSlow(false);
        setMessages((list) => [...settlePending(list), { role: 'assistant', text: result?.reply ?? UNREACHABLE }]);
        if (result?.saved) window.dispatchEvent(new CustomEvent('transaction-updated'));
    };

    const reset = () => {
        setThreadId(newThreadId());
        setMessages([]);
        setInput('');
    };

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label="Open the assistant"
                className="fixed right-4 bottom-20 lg:bottom-6 lg:right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition"
            >
                <Bot size={22} />
            </button>

            {open && createPortal(
                <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Assistant">
                    <div className="absolute inset-0 bg-black/40 sm:bg-black/20" onClick={() => setOpen(false)} />
                    <div className="relative flex h-dvh w-full sm:w-[400px] flex-col bg-card border-l border-border shadow-2xl">
                        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
                            <Bot size={18} className="text-primary" />
                            <h2 className="font-semibold text-foreground">Assistant</h2>
                            <button
                                type="button"
                                onClick={reset}
                                className="ml-auto rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                                aria-label="New conversation"
                                title="New conversation"
                            >
                                <RotateCcw size={16} />
                            </button>
                            <button
                                type="button"
                                onClick={() => setOpen(false)}
                                className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                                aria-label="Close the assistant"
                            >
                                <X size={18} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
                            {messages.length === 0 && (
                                <div className="space-y-3">
                                    <p className="text-sm text-muted-foreground">
                                        Ask about your spending, your budget or the app. I'll never save anything without asking.
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {SUGGESTIONS.map((s) => (
                                            <button
                                                key={s}
                                                type="button"
                                                onClick={() => send(s)}
                                                className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted"
                                            >
                                                {s}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                            {messages.map((m, i) => <Message key={i} message={m} onConfirm={confirm} busy={busy} />)}
                            {busy && (
                                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <Loader2 size={13} className="animate-spin" />
                                    {slow ? 'Waking up the assistant, this can take up to a minute the first time…' : 'Thinking…'}
                                </p>
                            )}
                            <div ref={endRef} />
                        </div>

                        <form
                            onSubmit={(e) => { e.preventDefault(); send(input); }}
                            className="flex items-center gap-2 border-t border-border p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
                        >
                            <input
                                ref={inputRef}
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                maxLength={300}
                                placeholder="Ask anything about your money…"
                                className="flex-1 rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/30"
                            />
                            <button
                                type="submit"
                                disabled={busy || !input.trim()}
                                aria-label="Send"
                                className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50"
                            >
                                <Send size={16} />
                            </button>
                        </form>
                    </div>
                </div>,
                document.body,
            )}
        </>
    );
};

export default AssistantPanel;
