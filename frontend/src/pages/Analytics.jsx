import React, { useState, useEffect } from 'react';
import {
    ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
    Tooltip as RTooltip, PieChart, Pie, Cell, Legend
} from 'recharts';
import { getTransactions } from '../services/api';
import { formatCurrency, formatDate } from '../lib/formatters';
import { SkeletonChart } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import { BarChart3 } from 'lucide-react';

const COLORS = [
    '#107555', '#059669', '#16a34a', '#0d9488',
    '#0284c7', '#f59e0b', '#e11d48', '#8b5cf6',
];

const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-xl bg-card border border-border shadow-xl px-3 py-2.5 text-xs">
            <p className="font-semibold text-foreground mb-1">{label}</p>
            {payload.map((p) => (
                <div key={p.dataKey} className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: p.stroke || p.fill }} />
                    <span className="text-muted-foreground">{p.dataKey}:</span>
                    <span className="font-semibold text-foreground">{formatCurrency(p.value)}</span>
                </div>
            ))}
        </div>
    );
};

const Analytics = () => {
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        getTransactions()
            .then(setTransactions)
            .catch(console.error)
            .finally(() => setLoading(false));
    }, []);

    if (loading) {
        return (
            <div className="space-y-5 page-enter">
                <div>
                    <div className="h-8 w-36 rounded-lg bg-muted/60 animate-pulse mb-1" />
                    <div className="h-4 w-52 rounded-lg bg-muted/40 animate-pulse" />
                </div>
                <SkeletonChart height={320} />
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <SkeletonChart height={280} />
                    <SkeletonChart height={280} />
                </div>
            </div>
        );
    }

    /* ── Daily data for area chart ── */
    const dailyDataMap = {};
    transactions.forEach((t) => {
        const date = new Date(t.date).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
        if (!dailyDataMap[date]) dailyDataMap[date] = { date, Income: 0, Expense: 0 };
        if (t.type === 'INCOME') dailyDataMap[date].Income += parseFloat(t.amount);
        else dailyDataMap[date].Expense += parseFloat(t.amount);
    });
    const dailyData = Object.values(dailyDataMap).reverse().slice(-30); // last 30 data points

    /* ── Category pie ── */
    const categoryMap = {};
    transactions.filter((t) => t.type === 'EXPENSE').forEach((t) => {
        const cat = t.category_name || 'Uncategorized';
        categoryMap[cat] = (categoryMap[cat] || 0) + parseFloat(t.amount);
    });
    const pieData = Object.entries(categoryMap)
        .map(([name, value]) => ({ name, value }))
        .sort((a, b) => b.value - a.value);

    /* ── Summary stats ── */
    const totalIncome = transactions
        .filter((t) => t.type === 'INCOME')
        .reduce((s, t) => s + parseFloat(t.amount), 0);
    const totalExpense = transactions
        .filter((t) => t.type === 'EXPENSE')
        .reduce((s, t) => s + parseFloat(t.amount), 0);

    /* ── Top expenses ── */
    const topExpenses = transactions
        .filter((t) => t.type === 'EXPENSE')
        .sort((a, b) => parseFloat(b.amount) - parseFloat(a.amount))
        .slice(0, 8);

    if (transactions.length === 0) {
        return (
            <div className="page-enter">
                <h1 className="font-display text-3xl font-bold text-foreground mb-1">Reports</h1>
                <p className="text-sm text-muted-foreground mb-8">Deep dive into your expense trends and habits.</p>
                <EmptyState
                    icon={<BarChart3 size={32} />}
                    title="No data to report yet"
                    description="Add some transactions to start seeing your spending trends and analytics."
                />
            </div>
        );
    }

    return (
        <div className="space-y-5 page-enter">
            <div>
                <h1 className="font-display text-3xl font-bold text-foreground">Reports</h1>
                <p className="mt-0.5 text-sm text-muted-foreground">
                    Deep dive into your expense trends and habits.
                </p>
            </div>

            {/* Summary tiles */}
            <div className="grid grid-cols-3 gap-4">
                {[
                    { label: 'Total Income', value: formatCurrency(totalIncome), color: 'text-income' },
                    { label: 'Total Expenses', value: formatCurrency(totalExpense), color: 'text-expense' },
                    { label: 'Net Savings', value: formatCurrency(Math.abs(totalIncome - totalExpense)), color: totalIncome >= totalExpense ? 'text-income' : 'text-expense' },
                ].map((s) => (
                    <div key={s.label} className="rounded-2xl border border-border bg-card px-4 py-3.5 text-center">
                        <p className="text-xs text-muted-foreground mb-1">{s.label}</p>
                        <p className={`text-xl font-bold font-display ${s.color}`}>{s.value}</p>
                    </div>
                ))}
            </div>

            {/* Area chart */}
            <div className="rounded-2xl border border-border bg-card p-5">
                <h3 className="font-semibold text-foreground mb-0.5">Spending Over Time</h3>
                <p className="text-xs text-muted-foreground mb-4">Daily income vs expense (last 30 entries)</p>
                {dailyData.length > 0 ? (
                    <div style={{ height: 300 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={dailyData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="gIncome" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="hsl(var(--income))" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="hsl(var(--income))" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="gExpense" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="hsl(var(--expense))" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="hsl(var(--expense))" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={false} tick={{ fill: 'hsl(var(--muted-foreground))' }} />
                                <YAxis fontSize={11} tickLine={false} axisLine={false} tick={{ fill: 'hsl(var(--muted-foreground))' }} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
                                <RTooltip content={<CustomTooltip />} />
                                <Legend formatter={(v) => <span style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>{v}</span>} />
                                <Area type="monotone" dataKey="Income" stroke="hsl(var(--income))" fill="url(#gIncome)" strokeWidth={2} />
                                <Area type="monotone" dataKey="Expense" stroke="hsl(var(--expense))" fill="url(#gExpense)" strokeWidth={2} />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                ) : (
                    <EmptyState title="No daily data" description="Add transactions with dates to see this chart." />
                )}
            </div>

            {/* Category pie + Top expenses */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Category breakdown */}
                <div className="rounded-2xl border border-border bg-card p-5">
                    <h3 className="font-semibold text-foreground mb-0.5">By Category</h3>
                    <p className="text-xs text-muted-foreground mb-4">Expenses breakdown</p>
                    {pieData.length > 0 ? (
                        <div style={{ height: 260 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={pieData} cx="50%" cy="45%" innerRadius={55} outerRadius={85} paddingAngle={2} dataKey="value">
                                        {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                                    </Pie>
                                    <RTooltip
                                        formatter={(v) => [formatCurrency(v), '']}
                                        contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }}
                                    />
                                    <Legend
                                        formatter={(v) => <span style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>{v}</span>}
                                    />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    ) : (
                        <EmptyState title="No expense categories" description="Assign categories to your expenses to see this chart." />
                    )}
                </div>

                {/* Top expenses */}
                <div className="rounded-2xl border border-border bg-card p-5">
                    <h3 className="font-semibold text-foreground mb-0.5">Top Expenses</h3>
                    <p className="text-xs text-muted-foreground mb-4">Highest single transactions</p>
                    {topExpenses.length > 0 ? (
                        <div className="space-y-1">
                            {topExpenses.map((t, i) => (
                                <div key={t.id} className="flex items-center justify-between rounded-xl px-3 py-2.5 hover:bg-muted/40 transition-colors">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-expense/10 text-expense text-xs font-bold">
                                            {i + 1}
                                        </span>
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium text-foreground truncate">{t.title}</p>
                                            <p className="text-xs text-muted-foreground">{formatDate(t.date, 'short')}</p>
                                        </div>
                                    </div>
                                    <span className="text-sm font-bold text-expense flex-shrink-0 ml-3">
                                        −{formatCurrency(t.amount)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <EmptyState title="No expenses" description="Record some expenses to see top transactions." />
                    )}
                </div>
            </div>
        </div>
    );
};

export default Analytics;
