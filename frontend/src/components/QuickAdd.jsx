import React, { useState, useRef } from 'react';
import { Sparkles, Loader2, X, Zap } from 'lucide-react';
import { parseTransaction } from '../services/aiService';

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
            const result = await parseTransaction(trimmed);

            if (!result) {
                setError("AI isn't available right now — please add the transaction manually.");
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
                <div className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground/60 font-medium">
                    <Sparkles size={9} className="text-primary/60" />
                    Powered by AI
                </div>
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
