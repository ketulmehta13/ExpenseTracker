import React, { useEffect, useState } from 'react';
import { AlertTriangle, Repeat, TrendingUp } from 'lucide-react';
import { getInsights } from '../services/mlService';
import { formatCurrency, formatCurrencyWhole, formatDate } from '../lib/formatters';
import { todayISODate } from '../lib/dates';
import { Skeleton } from './ui/Skeleton';

/**
 * SpendingInsights: the month-end forecast, subscriptions & bills, and unusual payments,
 * computed by the ML service. Renders nothing when the service is off or unreachable.
 *
 * Props:
 *   refreshKey — any value; when it changes the insights are fetched again
 */

const STATUS = {
    on_track: { label: 'On track', className: 'bg-income/15 text-income' },
    at_risk: { label: 'At risk', className: 'bg-amber-500/15 text-amber-600' },
    over: { label: 'Over budget', className: 'bg-expense/15 text-expense' },
};

const PERIOD_LABEL = {
    weekly: 'Weekly',
    fortnightly: 'Every 2 weeks',
    'every 28 days': 'Every 28 days',
    monthly: 'Monthly',
    quarterly: 'Quarterly',
    yearly: 'Yearly',
};

const chanceOfGoingOver = (probability) => {
    if (probability < 0.01) return 'very unlikely to go over';
    if (probability > 0.99) return 'almost certain to go over';
    return `${Math.round(probability * 100)}% chance of going over`;
};

const Card = ({ icon: Icon, iconClass, title, aside, children }) => (
    <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
                <Icon size={16} className={iconClass} />
                {title}
            </h3>
            {aside}
        </div>
        {children}
    </div>
);

const ForecastCard = ({ forecast }) => {
    const {
        projected_total: projected, low, high, spent_to_date: spent,
        budget, status, probability_over_budget: chanceOver,
    } = forecast;
    // One scale for the bar: whichever is largest of the budget and the top of the range
    const scale = Math.max(budget || 0, high, 1);
    const width = (value) => `${Math.min(100, (value / scale) * 100)}%`;

    return (
        <Card
            icon={TrendingUp}
            iconClass="text-primary"
            title="Month-end forecast"
            aside={status && (
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS[status].className}`}>
                    {STATUS[status].label}
                </span>
            )}
        >
            <p className="text-2xl font-bold text-foreground tabular-nums">{formatCurrencyWhole(projected)}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
                Likely {formatCurrencyWhole(low)} – {formatCurrencyWhole(high)} · {formatCurrencyWhole(spent)} spent so far
            </p>
            {budget ? (
                <div className="mt-4">
                    <div className="relative h-2 rounded-full bg-muted overflow-hidden" aria-hidden="true">
                        <div className="absolute inset-y-0 left-0 bg-primary/30" style={{ width: width(projected) }} />
                        <div className="absolute inset-y-0 left-0 bg-primary" style={{ width: width(spent) }} />
                        <div className="absolute inset-y-0 w-0.5 bg-foreground/60" style={{ left: width(budget) }} />
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">
                        Budget {formatCurrencyWhole(budget)}
                        {status !== 'over' && chanceOver != null && ` · ${chanceOfGoingOver(chanceOver)}`}
                    </p>
                </div>
            ) : (
                <p className="mt-4 text-xs text-muted-foreground">Set a monthly budget in your profile to track it here.</p>
            )}
        </Card>
    );
};

const RecurringCard = ({ payments, total }) => (
    <Card
        icon={Repeat}
        iconClass="text-primary"
        title="Subscriptions & bills"
        aside={<span className="text-xs text-muted-foreground tabular-nums">{formatCurrencyWhole(total)}/mo</span>}
    >
        <ul className="space-y-2.5">
            {payments.slice(0, 5).map((p) => (
                <li key={`${p.title}-${p.last_date}`} className="flex items-center justify-between gap-3 text-sm">
                    <div className="min-w-0">
                        <p className="font-medium text-foreground truncate">{p.title}</p>
                        <p className="text-xs text-muted-foreground">
                            {PERIOD_LABEL[p.period] ?? p.period} · next {formatDate(p.next_date, 'short')}
                        </p>
                    </div>
                    <span className="font-semibold text-foreground tabular-nums flex-shrink-0">{formatCurrency(p.amount)}</span>
                </li>
            ))}
        </ul>
        {payments.length > 5 && <p className="mt-2 text-xs text-muted-foreground">+{payments.length - 5} more</p>}
    </Card>
);

const UnusualCard = ({ payments }) => (
    <Card icon={AlertTriangle} iconClass="text-expense" title="Unusual spending">
        <ul className="space-y-2.5">
            {payments.slice(0, 4).map((p) => (
                <li key={p.transaction_id} className="text-sm">
                    <div className="flex items-center justify-between gap-3">
                        <p className="font-medium text-foreground truncate">{p.title}</p>
                        <span className="font-semibold text-expense tabular-nums flex-shrink-0">{formatCurrency(p.amount)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        {formatDate(p.date, 'short')} · {p.ratio}× your usual top payment{' '}
                        {p.compared_with === 'merchant' ? 'here' : `in ${p.category_name ?? 'this category'}`}{' '}
                        ({formatCurrencyWhole(p.usual_high)})
                    </p>
                </li>
            ))}
        </ul>
    </Card>
);

const SpendingInsights = ({ refreshKey }) => {
    // undefined while the first request runs; null when the service is unavailable
    const [insights, setInsights] = useState(undefined);

    useEffect(() => {
        const controller = new AbortController();
        getInsights(todayISODate(), controller.signal).then((data) => {
            // A failed refresh keeps the last good insights on screen
            if (!controller.signal.aborted) setInsights((previous) => data ?? previous ?? null);
        });
        return () => controller.abort();
    }, [refreshKey]);

    if (insights === undefined) {
        return (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 rounded-2xl" />)}
            </div>
        );
    }
    if (!insights) return null;

    const active = insights.recurring.filter((p) => p.active);
    const cards = [
        insights.forecast && <ForecastCard key="forecast" forecast={insights.forecast} />,
        active.length > 0 && <RecurringCard key="recurring" payments={active} total={insights.recurring_monthly_total} />,
        insights.unusual.length > 0 && <UnusualCard key="unusual" payments={insights.unusual} />,
    ].filter(Boolean);
    if (!cards.length) return null;

    const columns = { 1: '', 2: 'lg:grid-cols-2', 3: 'lg:grid-cols-3' }[cards.length];
    return <div className={`grid grid-cols-1 gap-4 ${columns}`}>{cards}</div>;
};

export default SpendingInsights;
