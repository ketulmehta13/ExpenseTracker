import React, { useState } from 'react';
import { BookOpen, ChevronDown, ExternalLink, ThumbsDown, ThumbsUp } from 'lucide-react';
import { sendFeedback } from '../services/chatService';

/**
 * The chatbot's reply blocks. Figures are worked out by the server and shown here as text and
 * simple bars: nothing from the model is ever inserted as HTML.
 */

const TONES = { income: 'text-income', expense: 'text-expense' };

const Cards = ({ items }) => (
    <div className="grid w-full grid-cols-2 gap-1.5">
        {items.map((item) => (
            <div key={item.label} className="rounded-lg bg-muted/60 px-2.5 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{item.label}</p>
                <p className={`text-sm font-semibold tabular-nums ${TONES[item.tone] ?? 'text-foreground'}`}>{item.value}</p>
            </div>
        ))}
    </div>
);

const Bars = ({ title, points }) => {
    const largest = Math.max(...points.map((p) => p.value), 1);
    return (
        <figure className="w-full rounded-xl border border-border bg-card p-3">
            <figcaption className="mb-2 text-xs font-semibold text-muted-foreground">{title}</figcaption>
            <ul className="space-y-2">
                {points.map((point) => (
                    <li key={point.label} className="text-xs">
                        <div className="mb-0.5 flex justify-between gap-2">
                            <span className="truncate text-foreground">{point.label}</span>
                            <span className="tabular-nums text-muted-foreground">{point.display}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                            <div className="h-full rounded-full bg-expense" style={{ width: `${Math.max(2, (point.value / largest) * 100)}%` }} />
                        </div>
                    </li>
                ))}
            </ul>
        </figure>
    );
};

const Rows = ({ title, rows }) => (
    <div className="w-full rounded-xl border border-border bg-card text-xs">
        <p className="px-3 pt-2.5 pb-1 font-semibold text-muted-foreground">{title}</p>
        <table className="w-full">
            <tbody className="divide-y divide-border">
                {rows.map((row, i) => (
                    <tr key={`${row.a}${row.c}${i}`}>
                        <td className="px-3 py-1.5 text-foreground">{row.a}</td>
                        <td className="whitespace-nowrap px-1 py-1.5 text-right tabular-nums text-foreground">{row.b}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-right text-muted-foreground">{row.c}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

export const Blocks = ({ blocks }) => (blocks ?? []).map((block, i) => {
    if (block.type === 'cards') return <Cards key={i} items={block.items} />;
    if (block.type === 'bars') return <Bars key={i} title={block.title} points={block.points} />;
    if (block.type === 'rows') return <Rows key={i} title={block.title} rows={block.rows} />;
    return null;
});

export const Sources = ({ items }) => {
    const [open, setOpen] = useState(null);
    return (
        <div className="w-full rounded-xl border border-border bg-card text-xs">
            <p className="flex items-center gap-1.5 px-3 pt-2.5 pb-1 font-semibold text-muted-foreground">
                <BookOpen size={12} /> {items.length === 1 ? 'Source' : 'Sources'}
            </p>
            <ul className="divide-y divide-border">
                {items.map((source, i) => (
                    <li key={`${source.title}${source.section}`}>
                        <button
                            type="button"
                            onClick={() => setOpen(open === i ? null : i)}
                            aria-expanded={open === i}
                            className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-muted/50"
                        >
                            <span className="flex-1 text-foreground">
                                {source.title}{source.section ? ` › ${source.section}` : ''}
                            </span>
                            <ChevronDown size={13} className={`mt-0.5 text-muted-foreground transition-transform ${open === i ? 'rotate-180' : ''}`} />
                        </button>
                        {open === i && (
                            <div className="space-y-1.5 px-3 pb-2.5 text-muted-foreground">
                                <p className="whitespace-pre-line">{source.excerpt}</p>
                                <p className="flex flex-wrap items-center gap-x-2 text-[11px]">
                                    <span>{source.source}</span>
                                    {/^https:\/\//.test(source.url ?? '') && (
                                        <a href={source.url} target="_blank" rel="noopener noreferrer"
                                            className="inline-flex items-center gap-0.5 text-primary hover:underline">
                                            Reference <ExternalLink size={10} />
                                        </a>
                                    )}
                                </p>
                            </div>
                        )}
                    </li>
                ))}
            </ul>
        </div>
    );
};

/** Thumbs up or down. A failed save is ignored: feedback must never get in the way of the chat. */
export const Feedback = ({ messageId }) => {
    const [rating, setRating] = useState(null);
    const rate = (value) => {
        setRating(value);
        sendFeedback(messageId, value).catch(() => {});
    };
    const button = (value, Icon, label) => (
        <button
            type="button"
            onClick={() => rate(value)}
            aria-label={label}
            aria-pressed={rating === value}
            className={`rounded p-1 transition-colors hover:bg-muted ${rating === value ? 'text-primary' : 'text-muted-foreground/70'}`}
        >
            <Icon size={13} />
        </button>
    );
    return (
        <div className="flex items-center gap-0.5 pl-1">
            {button('up', ThumbsUp, 'Good answer')}
            {button('down', ThumbsDown, 'Bad answer')}
        </div>
    );
};
