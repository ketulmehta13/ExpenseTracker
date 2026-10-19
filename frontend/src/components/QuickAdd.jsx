import React, { useState, useRef } from 'react';
import { Sparkles, Loader2, X, Zap, ScanLine } from 'lucide-react';
import { toast } from 'sonner';
import { parseTransaction } from '../services/aiService';
import { parseQuickAdd } from '../services/mlService';
import { ML_ENABLED } from '../lib/features';
import { todayISODate } from '../lib/dates';
import { openReceiptScanner } from '../lib/receipts';

/**
 * Parse with the ML service when it's configured (rules + the user's own categories),
 * otherwise with the LLM proxy. Both resolve to { type, amount, description, category, date }.
 */
async function parseText(text) {
    if (!ML_ENABLED) return parseTransaction(text);
    const draft = await parseQuickAdd(text, todayISODate());
    if (!draft) return null;
    if (draft.llm_filled?.length) {
        // An LLM's numbers are checked against the text, but a date can only be checked for plausibility
        toast.info(`Filled with AI help: please check the ${draft.llm_filled.join(' and ')}.`);
    }
    return {
        type: draft.type,
        amount: draft.amount,
        description: draft.title,
        category: draft.suggestion?.category_name ?? '',
        date: draft.date,
    };
}

/**
 * QuickAdd — natural language transaction entry bar.
 *
 * Props:
 *   onParsed({ type, amount, description, category, date }) — called with
 *       parsed data so parent can open TransactionModal pre-filled.
 */
const QuickAdd = ({ onParsed }) => {
    const [text, setText] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [focused, setFocused] = useState(false);
    const inputRef = useRef(null);

    const examples = [
        'spent 450 on groceries',
        'uber to airport 280',
        'received 20000 salary',
        'coffee 80 today',
    ];

    const handleSubmit = async (e) => {
        e?.preventDefault();
        const trimmed = text.trim();
        if (!trimmed) return;

        setError('');
        setLoading(true);

        try {
            const result = await parseText(trimmed);

            if (!result) {
                setError("Quick add isn't available right now. Please add the transaction manually.");
                return;
            }

            if (result.error) {
                setError(result.error);
                return;
            }

            // All good — pass parsed data up to parent
            onParsed(result);
            setText('');
            setError('');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') handleSubmit(e);
        if (e.key === 'Escape') {
            setText('');
            setError('');
            inputRef.current?.blur();
        }
    };

    const tryExample = (ex) => {
        setText(ex);
        inputRef.current?.focus();
    };

    return (
        <div className="rounded-2xl border border-border bg-card shadow-sm overflow-hidden">
            {/* Header */}
            <div className="flex items-center gap-2.5 px-4 py-3 border-b border-border bg-gradient-to-r from-primary/5 to-transparent">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
                    <Zap size={14} className="text-primary" />
                </div>
                <div>
                    <p className="text-sm font-semibold text-foreground leading-none">Quick Add</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Describe a transaction in plain English</p>
                </div>
                {!ML_ENABLED && (
                    <div className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground/60 font-medium">
                        <Sparkles size={9} className="text-primary/60" />
                        Powered by AI
                    </div>
                )}
            </div>

            {/* Input area */}
            <div className="px-4 py-3">
                <form onSubmit={handleSubmit} className="flex gap-2">
                    <div className="relative flex-1">
                        <input
                            ref={inputRef}
                            type="text"
                            value={text}
                            onChange={(e) => { setText(e.target.value); setError(''); }}
                            onKeyDown={handleKeyDown}
                            onFocus={() => setFocused(true)}
                            onBlur={() => setFocused(false)}
                            placeholder='Try: "spent 450 on groceries yesterday"'
                            disabled={loading}
                            className={`w-full rounded-xl border px-3.5 py-2.5 text-sm bg-background text-foreground placeholder:text-muted-foreground outline-none focus:ring-2 transition disabled:opacity-60 pr-8 ${
                                error
                                    ? 'border-destructive focus:ring-destructive/30'
                                    : focused
                                    ? 'border-primary/60 focus:ring-primary/20'
                                    : 'border-border focus:ring-ring/30'
                            }`}
                        />
                        {text && !loading && (
                            <button
                                type="button"
                                onClick={() => { setText(''); setError(''); inputRef.current?.focus(); }}
                                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                            >
                                <X size={13} />
                            </button>
                        )}
                    </div>
                    {ML_ENABLED && (
                        <button
                            type="button"
                            onClick={openReceiptScanner}
                            aria-label="Scan a bill"
                            title="Scan a bill"
                            className="flex items-center justify-center rounded-xl border border-border px-3 text-muted-foreground hover:text-primary hover:border-primary/40 transition"
                        >
                            <ScanLine size={16} />
                        </button>
                    )}
                    <button
                        type="submit"
                        disabled={loading || !text.trim()}
                        className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:opacity-90 transition active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                    >
                        {loading ? (
                            <>
                                <Loader2 size={13} className="animate-spin" />
                                Parsing…
                            </>
                        ) : (
                            <>
                                <Sparkles size={13} />
                                Add
                            </>
                        )}
                    </button>
                </form>

                {/* Error message */}
                {error && (
                    <p className="mt-2 text-xs text-destructive flex items-start gap-1.5">
                        <span className="mt-0.5 flex-shrink-0">⚠</span>
                        {error}
                    </p>
                )}

                {/* Example chips — only show when input is empty and focused */}
                {!text && focused && !loading && (
                    <div className="mt-2 flex flex-wrap gap-1.5 animate-in fade-in duration-150">
                        <span className="text-[10px] text-muted-foreground/60 font-medium self-center">Try:</span>
                        {examples.map((ex) => (
                            <button
                                key={ex}
                                type="button"
                                onMouseDown={(e) => { e.preventDefault(); tryExample(ex); }}
                                className="rounded-full border border-border px-2.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:border-foreground/30 transition-colors"
                            >
                                {ex}
                            </button>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default QuickAdd;
