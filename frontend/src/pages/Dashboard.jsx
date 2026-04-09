import React, { useState, useEffect } from 'react';
import { 
    ArrowUpCircle, 
    ArrowDownCircle, 
    Wallet,
    TrendingUp,
    Loader2,
    Lightbulb,
    AlertTriangle,
    Target
} from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip as RTooltip, Cell, PieChart, Pie, Legend } from 'recharts';
import api from '../services/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';

const COLORS = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6'];

const Dashboard = () => {
    const [summary, setSummary] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchSummary();
    }, []);

    const fetchSummary = async () => {
        try {
            const res = await api.get('/transactions/summary/');
            setSummary(res.data);
        } catch (error) {
            console.error('Failed to fetch summary', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center h-[calc(100vh-100px)]">
                <Loader2 className="animate-spin text-primary h-12 w-12" />
            </div>
        );
    }

    if (!summary) return null;

    const { current_month, budget, insights, category_breakdown } = summary;

    const pieData = category_breakdown.map((item, index) => ({
        name: item.category__name || 'Uncategorized',
        value: parseFloat(item.total)
    }));
    
    // For Bar Chart we can just show Income vs Expense for this month and last month
    const barData = [
        { name: 'Last Month', Income: parseFloat(summary.previous_month.income), Expense: parseFloat(summary.previous_month.expense) },
        { name: 'This Month', Income: parseFloat(current_month.income), Expense: parseFloat(current_month.expense) },
    ];

    const budgetPct = budget.limit > 0 ? (current_month.expense / budget.limit) * 100 : 0;
    
    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex flex-col gap-1">
                <h1 className="text-3xl font-bold tracking-tight">Dashboard Overview</h1>
                <p className="text-muted-foreground">Welcome back, here's your financial summary.</p>
            </div>

            {/* AI Insights & Budget Warnings */}
            {insights && (
                <div className="bg-primary/10 border border-primary/20 p-4 rounded-xl flex items-start space-x-3 text-primary">
                    <Lightbulb className="h-5 w-5 mt-0.5 flex-shrink-0" />
                    <div>
                        <p className="font-semibold text-sm">Spending Insights</p>
                        <p className="text-sm">{insights}</p>
                    </div>
                </div>
            )}
            
            {budget.exceeded && (
                <div className="bg-destructive/10 border border-destructive/20 p-4 rounded-xl flex items-start space-x-3 text-destructive">
                    <AlertTriangle className="h-5 w-5 mt-0.5 flex-shrink-0" />
                    <div>
                        <p className="font-semibold text-sm">Budget Exceeded</p>
                        <p className="text-sm">You have exceeded your monthly budget of ₹{parseFloat(budget.limit).toFixed(2)}!</p>
                    </div>
                </div>
            )}

            {/* Top Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium">Total Balance</CardTitle>
                        <Wallet className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">₹{parseFloat(current_month.balance).toFixed(2)}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium">Monthly Income</CardTitle>
                        <ArrowUpCircle className="h-4 w-4 text-emerald-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-emerald-500">₹{parseFloat(current_month.income).toFixed(2)}</div>
                    </CardContent>
                </Card>
                
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium">Monthly Expenses</CardTitle>
                        <ArrowDownCircle className="h-4 w-4 text-destructive" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold text-destructive">₹{parseFloat(current_month.expense).toFixed(2)}</div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between pb-2">
                        <CardTitle className="text-sm font-medium">Monthly Budget</CardTitle>
                        <Target className="h-4 w-4 text-blue-500" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">₹{parseFloat(budget.limit).toFixed(2)}</div>
                        {parseFloat(budget.limit) > 0 && (
                            <div className="w-full bg-secondary h-2 mt-3 rounded-full overflow-hidden">
                                <div 
                                    className={`h-full ${budget.exceeded ? 'bg-destructive' : 'bg-primary'}`} 
                                    style={{ width: `${Math.min(budgetPct, 100)}%` }}
                                ></div>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-7 gap-4">
                <Card className="lg:col-span-4">
                    <CardHeader>
                        <CardTitle className="flex items-center">
                            <TrendingUp className="mr-2 h-5 w-5 text-primary" /> 
                            Income vs Expense
                        </CardTitle>
                        <CardDescription>Comparison with previous month</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[300px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={barData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                                <XAxis dataKey="name" fontSize={12} tickLine={false} axisLine={false} />
                                <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `₹${value}`} />
                                <RTooltip cursor={{fill: 'transparent'}} contentStyle={{borderRadius: '8px', backgroundColor: 'var(--card)', border: '1px solid var(--border)'}} />
                                <Legend />
                                <Bar dataKey="Income" fill="#10b981" radius={[4, 4, 0, 0]} />
                                <Bar dataKey="Expense" fill="#ef4444" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </CardContent>
                </Card>

                <Card className="lg:col-span-3">
                    <CardHeader>
                        <CardTitle>Expenses by Category</CardTitle>
                        <CardDescription>This month's breakdown</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[300px] flex justify-center items-center pb-8">
                        {pieData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={pieData}
                                        cx="50%"
                                        cy="50%"
                                        innerRadius={60}
                                        outerRadius={90}
                                        paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {pieData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                        ))}
                                    </Pie>
                                    <RTooltip 
                                        formatter={(value) => `₹${value}`} 
                                        contentStyle={{borderRadius: '8px', backgroundColor: 'var(--card)', border: '1px solid var(--border)'}} 
                                    />
                                    <Legend verticalAlign="bottom" height={36} />
                                </PieChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                                <p>No expenses this month</p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default Dashboard;
