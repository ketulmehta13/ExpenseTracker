import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { ArrowLeft, Bot, History, Loader2, MessageSquarePlus, RotateCcw, Send, Square, Trash2, X } from 'lucide-react';
import { wakeMlService } from '../../services/mlService';
import {
    deleteCopilotThread, getCopilotThread, listCopilotThreads, streamCopilot,
} from '../../services/copilotService';
import { todayISODate } from '../../lib/dates';
import { formatDate } from '../../lib/formatters';
import { ActionCard, CopilotChart, DataView, MessageText, Sources } from './CopilotBlocks';

/**
 * CopilotPanel — the Financial Copilot: questions about your own spending (answered from your
 * data with exact figures), money topics (answered from the knowledge base, with sources), both
 * together, and actions you confirm before anything is saved. Rendered only when the ML service
 * is configured.
 */

const SUGGESTIONS = [
    { group: 'Your money', items: ['Where did my money go this month?', 'Compare this month with last month', 'Am I on track with my budget?'] },
    { group: 'Learn', items: ['Explain the 50/30/20 budgeting rule', 'How big should my emergency fund be?'] },
    { group: 'Do', items: ['Add 450 swiggy yesterday', 'Set my budget to 30000'] },
];

let nextId = 0;
const id = () => `m${(nextId += 1)}`;

const AssistantMessage = ({ message, threadId, onRetry }) => {
    const [openSource, setOpenSource] = useState(null);
    const [doneReply, setDoneReply] = useState('');
    const blocks = message.blocks ?? [];
    const sources = blocks.find((b) => b.type === 'citations');
    if (message.status === 'error') {
        return (
            <div className="flex flex-col items-start gap-1.5" role="alert">
                <p className="max-w-[92%] rounded-2xl rounded-bl-md border border-expense/30 bg-expense/5 px-3.5 py-2 text-sm text-foreground">
                    {message.text}
                </p>
                {message.retryable && (
                    <button type="button" onClick={onRetry}
                        className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-primary hover:bg-primary/10">
                        <RotateCcw size={12} /> Try again
                    </button>
                )}
            </div>
        );
    }
    return (
        <div className="flex flex-col items-start gap-2">
            <div className="max-w-[92%] rounded-2xl rounded-bl-md bg-muted px-3.5 py-2 text-sm text-foreground">
                {message.text
                    ? <MessageText text={message.text} onCite={setOpenSource} />
                    : <span className="flex items-center gap-2 text-muted-foreground"><Loader2 size={13} className="animate-spin" />{message.slow ? 'Waking up the copilot, this can take up to a minute the first time…' : 'Thinking…'}</span>}
                {message.status === 'streaming' && message.text && <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-foreground/40 align-middle" aria-hidden />}
            </div>
            {blocks.map((block, i) => {
                if (block.type === 'chart') return <CopilotChart key={i} block={block} />;
                if (block.type === 'data') return <DataView key={i} block={block} />;
                if (block.type === 'action') {
                    return message.fromHistory
                        ? <p key={i} className="text-xs text-muted-foreground">Proposed: {block.summary}</p>
                        : <ActionCard key={i} block={block} threadId={threadId} onDone={setDoneReply} />;
                }
                return null;
            })}
            {doneReply && <p className="max-w-[92%] rounded-2xl rounded-bl-md bg-muted px-3.5 py-2 text-sm text-foreground">{doneReply}</p>}
            {sources?.items?.length > 0 && <Sources items={sources.items} openSource={openSource} setOpenSource={setOpenSource} />}
        </div>
    );
};

const CopilotPanel = () => {
    const [open, setOpen] = useState(false);
    const [view, setView] = useState('chat'); // chat | history
    const [threadId, setThreadId] = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [busy, setBusy] = useState(false);
    const [threads, setThreads] = useState(null); // null = loading
    const [historyError, setHistoryError] = useState('');
    const controllerRef = useRef(null);
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

    useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }); }, [messages]);

    const update = (messageId, patch) =>
        setMessages((list) => list.map((m) => (m.id === messageId ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)));

    const send = useCallback(async (text) => {
        const question = text.trim();
        if (!question || busy) return;
        setInput('');
        const answerId = id();
        setMessages((list) => [...list, { id: id(), role: 'user', text: question },
            { id: answerId, role: 'assistant', text: '', status: 'streaming', question }]);
        setBusy(true);
        const controller = new AbortController();
        controllerRef.current = controller;
        const slowTimer = setTimeout(() => update(answerId, { slow: true }), 6000);
        try {
            const final = await streamCopilot({
                message: question,
                threadId,
                today: todayISODate(),
                signal: controller.signal,
                onMeta: (meta) => { if (meta.thread_id) setThreadId(meta.thread_id); },
                onDelta: (delta) => update(answerId, (m) => ({ text: m.text + delta, slow: false })),
            });
            // The final text is the checked one: it replaces whatever was streamed
            update(answerId, { text: final.reply, blocks: final.blocks, status: 'done' });
            if (final.thread_id) setThreadId(final.thread_id);
        } catch (err) {
            update(answerId, { text: err.message, status: 'error', retryable: err.retryable !== false });
        } finally {
            clearTimeout(slowTimer);
            controllerRef.current = null;
            setBusy(false);
            setTimeout(() => inputRef.current?.focus(), 0);
        }
    }, [busy, threadId]);

    const retry = (message) => {
        setMessages((list) => list.filter((m, i) => m.id !== message.id && list[i + 1]?.id !== message.id));
        send(message.question);
    };

    const stop = () => controllerRef.current?.abort();

    const newConversation = () => {
        stop();
        setThreadId(null);
        setMessages([]);
        setInput('');
        setView('chat');
    };

    const showHistory = async () => {
        setView('history');
        setThreads(null);
        setHistoryError('');
        try {
            setThreads(await listCopilotThreads());
        } catch (err) {
            setThreads([]);
            setHistoryError(err.message);
        }
    };

    const openThread = async (thread) => {
        setHistoryError('');
        try {
            const stored = await getCopilotThread(thread.id);
            setMessages(stored.map((m) => ({ id: id(), role: m.role, text: m.content, blocks: m.blocks, status: 'done', fromHistory: true })));
            setThreadId(thread.id);
            setView('chat');
        } catch (err) {
            setHistoryError(err.message);
        }
    };

    const removeThread = async (thread) => {
        try {
            await deleteCopilotThread(thread.id);
            setThreads((list) => list.filter((t) => t.id !== thread.id));
            if (thread.id === threadId) newConversation();
        } catch (err) {
            setHistoryError(err.message);
        }
    };

    const iconButton = 'rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground';

    return (
        <>
            <button
                type="button"
                onClick={() => setOpen(true)}
                aria-label="Open the Financial Copilot"
                className="fixed right-4 bottom-20 lg:bottom-6 lg:right-6 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg hover:opacity-90 transition"
            >
                <Bot size={22} />
            </button>

            {open && createPortal(
                <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Financial Copilot">
                    <div className="absolute inset-0 bg-black/40 sm:bg-black/20" onClick={() => setOpen(false)} />
                    <div className="relative flex h-dvh w-full sm:w-[440px] flex-col bg-card border-l border-border shadow-2xl">
                        <div className="flex items-center gap-1 border-b border-border px-3 py-3">
                            {view === 'history' ? (
                                <button type="button" onClick={() => setView('chat')} className={iconButton} aria-label="Back to the conversation">
                                    <ArrowLeft size={17} />
                                </button>
                            ) : <Bot size={18} className="ml-1 text-primary" />}
                            <h2 className="ml-1.5 font-semibold text-foreground">{view === 'history' ? 'Conversations' : 'Financial Copilot'}</h2>
                            <div className="ml-auto flex items-center">
                                {view === 'chat' && (
                                    <button type="button" onClick={showHistory} className={iconButton} aria-label="Past conversations" title="Past conversations">
                                        <History size={16} />
                                    </button>
                                )}
                                <button type="button" onClick={newConversation} className={iconButton} aria-label="New conversation" title="New conversation">
                                    <MessageSquarePlus size={16} />
                                </button>
                                <button type="button" onClick={() => setOpen(false)} className={iconButton} aria-label="Close the copilot">
                                    <X size={18} />
                                </button>
                            </div>
                        </div>

                        {view === 'history' ? (
                            <div className="flex-1 overflow-y-auto p-3">
                                {historyError && <p role="alert" className="mb-2 rounded-lg bg-expense/5 px-3 py-2 text-xs text-expense">{historyError}</p>}
                                {threads === null ? (
                                    <p className="flex items-center gap-2 p-2 text-sm text-muted-foreground"><Loader2 size={14} className="animate-spin" /> Loading…</p>
                                ) : threads.length === 0 ? (
                                    <p className="p-2 text-sm text-muted-foreground">No saved conversations yet.</p>
                                ) : (
                                    <ul className="space-y-1">
                                        {threads.map((thread) => (
                                            <li key={thread.id} className="group flex items-center gap-1 rounded-xl hover:bg-muted">
                                                <button type="button" onClick={() => openThread(thread)} className="flex-1 truncate px-3 py-2.5 text-left">
                                                    <span className="block truncate text-sm text-foreground">{thread.title}</span>
                                                    <span className="text-[11px] text-muted-foreground">{formatDate(thread.updated_at)}</span>
                                                </button>
                                                <button type="button" onClick={() => removeThread(thread)} className={`${iconButton} mr-1.5`} aria-label={`Delete "${thread.title}"`}>
                                                    <Trash2 size={14} />
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </div>
                        ) : (
                            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3" role="log" aria-live="polite" aria-relevant="additions text">
                                {messages.length === 0 && (
                                    <div className="space-y-4">
                                        <p className="text-sm text-muted-foreground">
                                            Ask about your spending, budgeting or the app. Figures come from your own data, explanations
                                            cite their sources, and nothing is saved until you confirm it.
                                        </p>
                                        {SUGGESTIONS.map(({ group, items }) => (
                                            <div key={group}>
                                                <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</p>
                                                <div className="flex flex-wrap gap-2">
                                                    {items.map((s) => (
                                                        <button key={s} type="button" onClick={() => send(s)}
                                                            className="rounded-full border border-border px-3 py-1.5 text-xs text-foreground hover:bg-muted">
                                                            {s}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {messages.map((m) => (m.role === 'user' ? (
                                    <div key={m.id} className="flex justify-end">
                                        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 text-sm text-primary-foreground whitespace-pre-line">{m.text}</p>
                                    </div>
                                ) : (
                                    <AssistantMessage key={m.id} message={m} threadId={threadId} onRetry={() => retry(m)} />
                                )))}
                                <div ref={endRef} />
                            </div>
                        )}

                        {view === 'chat' && (
                            <form
                                onSubmit={(e) => { e.preventDefault(); send(input); }}
                                className="flex items-center gap-2 border-t border-border p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
                            >
                                <label htmlFor="copilot-input" className="sr-only">Message the copilot</label>
                                <input
                                    id="copilot-input"
                                    ref={inputRef}
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    maxLength={1000}
                                    placeholder="Ask anything about your money…"
                                    className="flex-1 rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 focus:ring-ring/30"
                                />
                                {busy ? (
                                    <button type="button" onClick={stop} aria-label="Stop the answer"
                                        className="flex h-10 w-10 items-center justify-center rounded-xl border border-border text-foreground hover:bg-muted">
                                        <Square size={14} />
                                    </button>
                                ) : (
                                    <button type="submit" disabled={!input.trim()} aria-label="Send"
                                        className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
                                        <Send size={16} />
                                    </button>
                                )}
                            </form>
                        )}
                    </div>
                </div>,
                document.body,
            )}
        </>
    );
};

export default CopilotPanel;
