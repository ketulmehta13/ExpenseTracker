import React, { useEffect, useState } from 'react';
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts';
import { BookOpen, Check, ChevronDown, ExternalLink, Loader2, X } from 'lucide-react';
import { formatCurrency, formatDate } from '../../lib/formatters';
import { getCategories } from '../../services/api';
import { confirmCopilotAction } from '../../services/copilotService';
import { todayISODate } from '../../lib/dates';

/**
 * Renderers for the copilot's typed reply blocks (see ml-service/app/copilot/schemas.py).
 * Everything is rendered as React text: nothing from the model or the knowledge base is ever
 * inserted as HTML.
 */

/* ── Answer text with [S1] citation markers ── */
export const MessageText = ({ text, onCite }) => {
    const parts = text.split(/(\[S\d+\])/g);
    return (
        <p className="whitespace-pre-line">
            {parts.map((part, i) => {
                const match = /^\[S(\d+)\]$/.exec(part);
                if (!match) return <React.Fragment key={i}>{part}</React.Fragment>;
                return (
                    <button
                        key={i}
                        type="button"
                        onClick={() => onCite?.(Number(match[1]))}
                        className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded bg-primary/15 px-1 text-[10px] font-semibold text-primary hover:bg-primary/25"
                        aria-label={`Source ${match[1]}`}
                    >
                        {match[1]}
                    </button>
                );
            })}
        </p>
    );
};

/* ── Sources ── */
export const Sources = ({ items, openSource, setOpenSource }) => (
    <div className="w-full rounded-xl border border-border bg-card text-xs">
        <p className="flex items-center gap-1.5 px-3 pt-2.5 pb-1 font-semibold text-muted-foreground">
            <BookOpen size={12} /> Sources
        </p>
        <ul className="divide-y divide-border">
            {items.map((s) => {
                const open = openSource === s.n;
                return (
                    <li key={s.n}>
                        <button
                            type="button"
                            onClick={() => setOpenSource(open ? null : s.n)}
                            aria-expanded={open}
                            className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-muted/50"
                        >
                            <span className="mt-px flex h-4 min-w-4 items-center justify-center rounded bg-primary/15 px-1 text-[10px] font-semibold text-primary">
                                {s.n}
                            </span>
                            <span className="flex-1 text-foreground">
                                {s.title}{s.section ? ` › ${s.section}` : ''}
                            </span>
                            <ChevronDown size={13} className={`mt-0.5 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
                        </button>
                        {open && (
                            <div className="space-y-1.5 px-3 pb-2.5 pl-9 text-muted-foreground">
                                <p className="whitespace-pre-line">{s.excerpt}</p>
                                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
                                    <span>{s.source} · v{s.version}</span>
                                    {s.source_url && /^https:\/\//.test(s.source_url) && (
                                        <a href={s.source_url} target="_blank" rel="noopener noreferrer"
                                            className="inline-flex items-center gap-0.5 text-primary hover:underline">
                                            Reference <ExternalLink size={10} />
                                        </a>
                                    )}
                                </p>
                            </div>
                        )}
                    </li>
                );
            })}
        </ul>
    </div>
);

/* ── Charts ── */
const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs shadow">
            <p className="font-semibold text-foreground">{label}</p>
            {payload.map((p) => (
                <p key={p.dataKey} className="text-muted-foreground">
                    {p.dataKey === 'previous' ? 'Before' : 'Now'}: {formatCurrency(p.value)}
                </p>
            ))}
        </div>
    );
};

export const CopilotChart = ({ block }) => {
    const data = block.points.slice(0, 8).map((p) => ({ label: p.label, value: p.value, previous: p.previous ?? 0 }));
    if (!data.length) return null;
    const comparison = block.chart === 'comparison';
    return (
        <figure className="w-full rounded-xl border border-border bg-card p-3">
            <figcaption className="mb-2 text-xs font-semibold text-muted-foreground">{block.title}</figcaption>
            <div style={{ height: Math.max(120, data.length * (comparison ? 44 : 30)) }}>
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
                        <XAxis type="number" hide />
                        <YAxis type="category" dataKey="label" width={92} tickLine={false} axisLine={false}
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
                        <RTooltip content={<ChartTooltip />} cursor={{ fill: 'hsl(var(--muted)/0.4)' }} />
                        {comparison && <Bar dataKey="previous" fill="hsl(var(--muted-foreground)/0.45)" radius={[0, 4, 4, 0]} maxBarSize={14} />}
                        <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={16}>
                            {data.map((d) => (
                                <Cell key={d.label} fill={comparison && d.value < d.previous ? 'hsl(var(--income))' : 'hsl(var(--expense))'} />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </div>
            {comparison && (
                <p className="mt-1.5 flex gap-3 text-[11px] text-muted-foreground">
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-muted-foreground/45" /> Before</span>
                    <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-expense" /> Now</span>
                </p>
            )}
        </figure>
    );
};

/* ── Tool results ── */
const Stat = ({ label, value, tone }) => (
    <div className="rounded-lg bg-muted/60 px-2.5 py-1.5">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`text-sm font-semibold tabular-nums ${tone ?? 'text-foreground'}`}>{value}</p>
    </div>
);

export const DataView = ({ block }) => {
    const r = block.result;
    if (block.tool === 'get_expense_summary' && !r.category && !r.merchant && r.income > 0) {
        return (
            <div className="grid w-full grid-cols-2 gap-1.5">
                <Stat label="Spent" value={formatCurrency(r.expenses)} tone="text-expense" />
                <Stat label="Earned" value={formatCurrency(r.income)} tone="text-income" />
                <Stat label="Net" value={formatCurrency(r.net)} />
                {r.savings_rate != null && <Stat label="Savings rate" value={`${(r.savings_rate * 100).toFixed(1)}%`} />}
            </div>
        );
    }
    if (block.tool === 'get_budget_status' && r.budget) {
        const used = Math.min(100, (r.spent_to_date / r.budget) * 100);
        return (
            <div className="w-full rounded-xl border border-border bg-card p-3 text-xs">
                <div className="flex justify-between text-muted-foreground">
                    <span>{formatCurrency(r.spent_to_date)} of {formatCurrency(r.budget)}</span>
                    <span>{used.toFixed(0)}%</span>
                </div>
                <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} aria-label="Budget used">
                    <div className={`h-full rounded-full ${r.status === 'over' ? 'bg-expense' : r.status === 'at_risk' ? 'bg-amber-500' : 'bg-income'}`} style={{ width: `${used}%` }} />
                </div>
                {r.projected_total != null && (
                    <p className="mt-1.5 text-muted-foreground">Forecast: {formatCurrency(r.projected_total)} this month</p>
                )}
            </div>
        );
    }
    const rows = block.tool === 'detect_recurring_expenses'
        ? r.items.map((i) => [i.title, `${formatCurrency(i.amount)} · ${i.period}`, `next ${formatDate(i.next_date)}`])
        : block.tool === 'get_unusual_payments'
            ? r.items.map((i) => [i.title, formatCurrency(i.amount), formatDate(i.date)])
            : [];
    if (!rows.length) return null;
    return (
        <table className="w-full overflow-hidden rounded-xl border border-border bg-card text-xs">
            <tbody className="divide-y divide-border">
                {rows.map(([a, b, c]) => (
                    <tr key={`${a}${c}`}>
                        <td className="px-2.5 py-1.5 text-foreground">{a}</td>
                        <td className="px-2.5 py-1.5 text-right tabular-nums text-foreground">{b}</td>
                        <td className="px-2.5 py-1.5 text-right text-muted-foreground">{c}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
};

/* ── A proposed action: editable, confirmed explicitly, run once ── */
const inputClass = 'w-full rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm text-foreground outline-none focus:ring-2 focus:ring-ring/30';

export const ActionCard = ({ block, threadId, onDone }) => {
    const [fields, setFields] = useState(block.fields);
    const [state, setState] = useState(block.done ? 'done' : 'idle'); // idle | saving | done | discarded
    const [error, setError] = useState('');
    const [categories, setCategories] = useState([]);
    const isTransaction = block.action === 'create_transaction';
    const locked = state === 'saving' || state === 'done' || state === 'discarded';

    useEffect(() => {
        if (!isTransaction) return;
        getCategories().then(setCategories).catch(() => setCategories([]));
    }, [isTransaction]);

    const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

    const confirm = async () => {
        setState('saving');
        setError('');
        const payload = isTransaction
            ? { ...fields, amount: Number(fields.amount), category_id: fields.category_id === '' ? null : fields.category_id }
            : { monthly_budget: Number(fields.monthly_budget), previous_budget: fields.previous_budget ?? null };
        try {
            const result = await confirmCopilotAction({
                action: block.action, idempotencyKey: block.idempotency_key, fields: payload, threadId, today: todayISODate(),
            });
            setState('done');
            onDone?.(result.reply);
            window.dispatchEvent(new CustomEvent('transaction-updated'));
        } catch (err) {
            setState('idle');
            setError(err.message);
        }
    };

    return (
        <form
            onSubmit={(e) => { e.preventDefault(); confirm(); }}
            className="w-full space-y-2.5 rounded-xl border border-primary/30 bg-card p-3 text-sm"
            aria-label={isTransaction ? 'Confirm the transaction' : 'Confirm the budget'}
        >
            {isTransaction ? (
                <>
                    <label className="block text-xs text-muted-foreground">Title
                        <input value={fields.title} onChange={set('title')} disabled={locked} maxLength={100} required className={inputClass} />
                    </label>
                    <div className="grid grid-cols-2 gap-2">
                        <label className="block text-xs text-muted-foreground">Amount (₹)
                            <input type="number" min="0.01" step="0.01" value={fields.amount} onChange={set('amount')} disabled={locked} required className={inputClass} />
                        </label>
                        <label className="block text-xs text-muted-foreground">Date
                            <input type="date" value={fields.date} onChange={set('date')} disabled={locked} required className={inputClass} />
                        </label>
                        <label className="block text-xs text-muted-foreground">Type
                            <select value={fields.type} onChange={set('type')} disabled={locked} className={inputClass}>
                                <option value="EXPENSE">Expense</option>
                                <option value="INCOME">Income</option>
                            </select>
                        </label>
                        <label className="block text-xs text-muted-foreground">Category
                            <select value={fields.category_id ?? ''} onChange={set('category_id')} disabled={locked} className={inputClass}>
                                <option value="">No category</option>
                                {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                {fields.category_id != null && !categories.some((c) => String(c.id) === String(fields.category_id)) && (
                                    <option value={fields.category_id}>{fields.category_name ?? 'Suggested'}</option>
                                )}
                            </select>
                        </label>
                    </div>
                </>
            ) : (
                <label className="block text-xs text-muted-foreground">Monthly budget (₹)
                    <input type="number" min="0" step="1" value={fields.monthly_budget} onChange={set('monthly_budget')} disabled={locked} required className={inputClass} />
                    {fields.previous_budget ? <span className="mt-1 block">Now {formatCurrency(fields.previous_budget)}</span> : null}
                </label>
            )}
            {error && <p role="alert" className="text-xs text-expense">{error}</p>}
            {state === 'done' ? (
                <p className="flex items-center gap-1.5 text-xs font-semibold text-income"><Check size={14} /> Saved</p>
            ) : state === 'discarded' ? (
                <p className="text-xs text-muted-foreground">Not saved.</p>
            ) : (
                <div className="flex gap-2">
                    <button type="button" disabled={locked} onClick={() => setState('discarded')}
                        className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-border py-2 text-xs font-semibold text-foreground hover:bg-muted disabled:opacity-50">
                        <X size={13} /> Discard
                    </button>
                    <button type="submit" disabled={locked}
                        className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-primary py-2 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50">
                        {state === 'saving' ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Confirm
                    </button>
                </div>
            )}
        </form>
    );
};
