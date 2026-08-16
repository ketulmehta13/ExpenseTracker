import React, { useState, useEffect, useCallback } from 'react';
import {
    TrendingUp, TrendingDown, Wallet, ArrowUpRight, ArrowDownRight,
    Plus, Calendar, RefreshCw
} from 'lucide-react';
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
    Tooltip as RTooltip, PieChart, Pie, Cell, Legend
} from 'recharts';
import { getTransactions, getProfile, computeSummary } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { formatCurrency, formatDate, getGreeting } from '../lib/formatters';
import { SkeletonDashboard } from '../components/ui/Skeleton';
import { EmptyState } from '../components/ui/EmptyState';
import TransactionModal from '../components/TransactionModal';

/* ── Color palette for category donut chart (Brand #0d3a35 Teal-Green) ── */
const CAT_COLORS = [
    '#0d3a35', '#16574f', '#247a70', '#3b9e92',
    '#0284c7', '#f59e0b', '#dc2626', '#7c3aed',
];

/* ── Date range options ── */
const DATE_RANGES = [
    { id: 'this_month', label: 'This month' },
    { id: 'last_30', label: 'Last 30 days' },
    { id: 'last_3m', label: 'Last 3 months' },
    { id: 'all', label: 'All time' },
];

/* ── Summary card component ── */
const SummaryCard = ({ label, value, subtext, icon: Icon, accentClass, trend, trendValue }) => (
    <div className="relative rounded-2xl border border-border bg-card p-5 overflow-hidden group hover:shadow-md transition-shadow">
        <div className="absolute top-0 right-0 w-24 h-24 rounded-full bg-current opacity-[0.04] -translate-y-6 translate-x-6 group-hover:opacity-[0.07] transition-opacity" />
        <div className="flex items-start justify-between mb-3">
            <p className="text-sm font-medium text-muted-foreground">{label}</p>
            <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${accentClass}`}>
                <Icon size={18} />
            </div>
        </div>
        <p className="text-2xl font-bold text-foreground font-display">{value}</p>
        {subtext && <p className="mt-1 text-xs text-muted-foreground">{subtext}</p>}
        {trendValue !== undefined && (
            <div className={`mt-2 flex items-center gap-1 text-xs font-semibold ${trend === 'up' ? 'text-income' : trend === 'down' ? 'text-expense' : 'text-muted-foreground'}`}>
                {trend === 'up' ? <TrendingUp size={12} /> : trend === 'down' ? <TrendingDown size={12} /> : null}
                {trendValue}
            </div>
        )}
    </div>
);

/* ── Custom Recharts tooltip ── */
const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div className="rounded-xl bg-card border border-border shadow-xl px-3 py-2.5 text-xs">
            <p className="font-semibold text-foreground mb-1">{label}</p>
            {payload.map((p) => (
                <div key={p.dataKey} className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: p.fill || p.color }} />
                    <span className="text-muted-foreground capitalize">{p.dataKey}:</span>
                    <span className="font-semibold text-foreground">{formatCurrency(p.value)}</span>
                </div>
            ))}
        </div>
    );
};

/* ─────────────────────────────────────
   Main Dashboard component
───────────────────────────────────── */
const Dashboard = () => {
    const { user } = useAuth();
    const [allTransactions, setAllTransactions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [profile, setProfile] = useState(null);
    const [dateRange, setDateRange] = useState('this_month');
    const [txModal, setTxModal] = useState({ open: false, type: 'EXPENSE' });

    const fetchData = useCallback(async () => {
        setLoading(true);
        try {
            const [txs, prof] = await Promise.all([
                getTransactions(),
                getProfile(user.id),
            ]);
            setAllTransactions(txs);
            setProfile(prof);
        } catch (err) {
            console.error('Dashboard fetch error', err);
        } finally {
            setLoading(false);
        }
    }, [user]);

    useEffect(() => { fetchData(); }, [fetchData]);

    // Re-fetch when a transaction is added/edited from the sidebar modal
    useEffect(() => {
        const handler = () => fetchData();
        window.addEventListener('transaction-updated', handler);
        return () => window.removeEventListener('transaction-updated', handler);
    }, [fetchData]);

    /* ── Filter transactions by date range ── */
    const filteredTransactions = React.useMemo(() => {
        const now = new Date();
        return allTransactions.filter((t) => {
            const d = new Date(t.date);
            if (dateRange === 'this_month') {
                return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
            }
            if (dateRange === 'last_30') {
                return (now - d) / 86400000 <= 30;
            }
            if (dateRange === 'last_3m') {
                return (now - d) / 86400000 <= 90;
            }
            return true; // all
        });
    }, [allTransactions, dateRange]);

    const summary = React.useMemo(
        () => computeSummary(allTransactions, profile?.monthly_budget),
        [allTransactions, profile]
    );

    /* ── 6-month bar chart data ── */
    const barData = React.useMemo(() => {
        const months = [];
        const now = new Date();
        for (let i = 5; i >= 0; i--) {
            const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
            const label = d.toLocaleDateString('en-IN', { month: 'short' });
            let income = 0, expense = 0;
            allTransactions.forEach((t) => {
                const td = new Date(t.date);
                if (td.getMonth() === d.getMonth() && td.getFullYear() === d.getFullYear()) {
                    if (t.type === 'INCOME') income += parseFloat(t.amount);
                    else expense += parseFloat(t.amount);
                }
            });
            months.push({ name: label, Income: income, Expense: expense });
        }
        return months;
    }, [allTransactions]);

    /* ── Category donut data ── */
    const pieData = React.useMemo(() => {
        const map = {};
        filteredTransactions
            .filter((t) => t.type === 'EXPENSE')
            .forEach((t) => {
                const cat = t.category_name || 'Uncategorized';
                map[cat] = (map[cat] || 0) + parseFloat(t.amount);
            });
        return Object.entries(map)
            .map(([name, value]) => ({ name, value }))
            .sort((a, b) => b.value - a.value);
    }, [filteredTransactions]);

    /* ── Recent activity (last 8) ── */
    const recentActivity = React.useMemo(
        () => allTransactions.slice(0, 8),
        [allTransactions]
    );

    /* ── Summary values ── */
    const curIncome = filteredTransactions
        .filter((t) => t.type === 'INCOME')
        .reduce((s, t) => s + parseFloat(t.amount), 0);
    const curExpense = filteredTransactions
        .filter((t) => t.type === 'EXPENSE')
        .reduce((s, t) => s + parseFloat(t.amount), 0);
    const netBalance = curIncome - curExpense;

    const prevIncome = summary?.previous_month?.income ?? 0;
    const prevExpense = summary?.previous_month?.expense ?? 0;
    const prevNet = prevIncome - prevExpense;
    const netPctChange = prevNet !== 0 ? ((netBalance - prevNet) / Math.abs(prevNet)) * 100 : null;

    const displayName =
        profile?.first_name ||
        user?.user_metadata?.username ||
        user?.email?.split('@')[0] ||
        'there';

    const today = new Date().toLocaleDateString('en-IN', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });

    if (loading) return <SkeletonDashboard />;

    return (
        <div className="space-y-6 page-enter">
            {/* ── Greeting header ── */}
            {/* ── Greeting header ── */}
            <div>
                <h1 className="font-display text-3xl font-bold text-foreground">
                    {getGreeting()}, {displayName}.
                </h1>
                <p className="mt-0.5 text-sm text-muted-foreground">{today}</p>
            </div>

            {/* ── Date range selector ── */}
            <div className="flex items-center gap-2 flex-wrap">
                <Calendar size={15} className="text-muted-foreground" />
                {DATE_RANGES.map((r) => (
                    <button
                        key={r.id}
                        onClick={() => setDateRange(r.id)}
                        className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                            dateRange === r.id
                                ? 'bg-primary text-primary-foreground shadow-sm'
                                : 'bg-muted text-muted-foreground hover:text-foreground'
                        }`}
                    >
                        {r.label}
                    </button>
                ))}
                <button
                    onClick={fetchData}
                    className="ml-auto text-muted-foreground hover:text-foreground transition-colors"
                    title="Refresh"
                >
                    <RefreshCw size={15} />
                </button>
            </div>

            {/* ── 4 summary cards ── */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <SummaryCard
                    label="Income this month"
                    value={formatCurrency(curIncome)}
                    subtext={`${filteredTransactions.filter((t) => t.type === 'INCOME').length} entries`}
                    icon={TrendingUp}
                    accentClass="bg-income/15 text-income"
                    trend={curIncome >= prevIncome ? 'up' : 'down'}
                    trendValue={prevIncome > 0 ? `${curIncome >= prevIncome ? '+' : ''}${(((curIncome - prevIncome) / prevIncome) * 100).toFixed(1)}% vs last month` : null}
                />
                <SummaryCard
                    label="Expenses this month"
                    value={formatCurrency(curExpense)}
                    subtext={`${filteredTransactions.filter((t) => t.type === 'EXPENSE').length} entries`}
                    icon={TrendingDown}
                    accentClass="bg-expense/15 text-expense"
                    trend={curExpense > prevExpense ? 'down' : 'up'}
                    trendValue={prevExpense > 0 ? `${curExpense > prevExpense ? '+' : ''}${(((curExpense - prevExpense) / prevExpense) * 100).toFixed(1)}% vs last month` : null}
                />
                <SummaryCard
                    label="Net balance"
                    value={formatCurrency(Math.abs(netBalance))}
                    subtext={netBalance >= 0 ? 'Positive balance ✓' : 'Spending exceeds income'}
                    icon={Wallet}
                    accentClass={netBalance >= 0 ? 'bg-income/15 text-income' : 'bg-expense/15 text-expense'}
                />
                <SummaryCard
                    label="% change vs last month"
                    value={netPctChange !== null ? `${netPctChange > 0 ? '+' : ''}${netPctChange.toFixed(1)}%` : '—'}
                    subtext={netPctChange === null ? 'No prior data yet' : netPctChange > 0 ? 'Net improved' : 'Net declined'}
                    icon={netPctChange >= 0 ? ArrowUpRight : ArrowDownRight}
                    accentClass={netPctChange === null || netPctChange >= 0 ? 'bg-income/15 text-income' : 'bg-expense/15 text-expense'}
                />
            </div>

            {/* ── Charts row ── */}
            {allTransactions.length === 0 ? (
                <EmptyState
                    icon={<Wallet size={32} />}
                    title="No transactions yet"
                    description="Add your first income or expense from the top-right profile menu to see your financial overview here."
                />
            ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    {/* Income vs Expense bar chart */}
                    <div className="rounded-2xl border border-border bg-card p-5">
                        <h3 className="font-semibold text-foreground mb-0.5">Income vs Expenses</h3>
                        <p className="text-xs text-muted-foreground mb-4">Last 6 months</p>
                        <div style={{ height: 260 }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <BarChart data={barData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                                    <XAxis
                                        dataKey="name"
                                        fontSize={11}
                                        tickLine={false}
                                        axisLine={false}
                                        tick={{ fill: 'hsl(var(--muted-foreground))' }}
                                    />
                                    <YAxis
                                        fontSize={11}
                                        tickLine={false}
                                        axisLine={false}
                                        tick={{ fill: 'hsl(var(--muted-foreground))' }}
                                        tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
                                    />
                                    <RTooltip content={<CustomTooltip />} cursor={{ fill: 'hsl(var(--muted)/0.4)' }} />
                                    <Legend
                                        formatter={(v) => (
                                            <span style={{ color: 'hsl(var(--muted-foreground))', fontSize: 11 }}>{v}</span>
                                        )}
                                    />
                                    <Bar dataKey="Income" fill="hsl(var(--income))" radius={[4, 4, 0, 0]} maxBarSize={28} />
                                    <Bar dataKey="Expense" fill="hsl(var(--expense))" radius={[4, 4, 0, 0]} maxBarSize={28} />
                                </BarChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Recent Activity */}
                    <div className="rounded-2xl border border-border bg-card p-5">
                        <h3 className="font-semibold text-foreground mb-0.5">Recent Activity</h3>
                        <p className="text-xs text-muted-foreground mb-4">Your latest transactions</p>
                        {recentActivity.length === 0 ? (
                            <EmptyState
                                title="No activity yet"
                                description="Your recent transactions will appear here."
                            />
                        ) : (
                            <div className="space-y-1">
                                {recentActivity.map((t) => (
                                    <div
                                        key={t.id}
                                        className="flex items-center justify-between rounded-xl px-3 py-2.5 hover:bg-muted/50 transition-colors"
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <div className={`flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold ${
                                                t.type === 'INCOME' ? 'bg-income/15 text-income' : 'bg-expense/15 text-expense'
                                            }`}>
                                                {(t.category_name || t.title || '?')[0].toUpperCase()}
                                            </div>
                                            <div className="min-w-0">
                                                <p className="text-sm font-medium text-foreground truncate">{t.title}</p>
                                                <p className="text-xs text-muted-foreground">
                                                    {formatDate(t.date, 'short')}
                                                    {t.category_name && ` · ${t.category_name}`}
                                                </p>
                                            </div>
                                        </div>
                                        <span className={`text-sm font-bold flex-shrink-0 ml-3 ${t.type === 'INCOME' ? 'text-income' : 'text-expense'}`}>
                                            {t.type === 'INCOME' ? '+' : '−'}{formatCurrency(t.amount)}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* ── Category donut chart ── */}
            {pieData.length > 0 && (
                <div className="rounded-2xl border border-border bg-card p-5">
                    <h3 className="font-semibold text-foreground mb-0.5">Expense Breakdown</h3>
                    <p className="text-xs text-muted-foreground mb-4">By category — {DATE_RANGES.find(r => r.id === dateRange)?.label}</p>
                    <div className="flex flex-col sm:flex-row items-center gap-6">
                        <div style={{ width: 220, height: 220 }} className="flex-shrink-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={pieData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={90}
                                        paddingAngle={2}
                                        dataKey="value"
                                    >
                                        {pieData.map((_, i) => (
                                            <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <RTooltip
                                        formatter={(v) => [formatCurrency(v), '']}
                                        contentStyle={{
                                            background: 'hsl(var(--card))',
                                            border: '1px solid hsl(var(--border))',
                                            borderRadius: 12,
                                            fontSize: 12,
                                        }}
                                    />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                        {/* Legend */}
                        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-2">
                            {pieData.map((item, i) => (
                                <div key={item.name} className="flex items-center gap-2">
                                    <span
                                        className="h-3 w-3 rounded-full flex-shrink-0"
                                        style={{ background: CAT_COLORS[i % CAT_COLORS.length] }}
                                    />
                                    <span className="text-sm text-muted-foreground truncate">{item.name}</span>
                                    <span className="ml-auto text-sm font-semibold text-foreground flex-shrink-0">
                                        {formatCurrency(item.value)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            {/* Add/Edit modal driven from dashboard buttons */}
            <TransactionModal
                isOpen={txModal.open}
                defaultType={txModal.type}
                onClose={() => setTxModal({ open: false, type: 'EXPENSE' })}
                onSuccess={fetchData}
            />
        </div>
    );
};

export default Dashboard;
