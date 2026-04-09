import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip as RTooltip, PieChart, Pie, Cell, Legend } from 'recharts';
import api from '../services/api';
import { Loader2 } from 'lucide-react';

const COLORS = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6'];

const Analytics = () => {
    const [transactions, setTransactions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const res = await api.get('/transactions/');
            setTransactions(res.data);
        } catch (error) {
            console.error('Error fetching analytics data', error);
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

    const dailyDataMap = {};
    transactions.forEach(t => {
        const date = new Date(t.date).toLocaleDateString('default', { month: 'short', day: 'numeric' });
        if (!dailyDataMap[date]) dailyDataMap[date] = { date, Income: 0, Expense: 0 };
        if (t.type === 'INCOME') dailyDataMap[date].Income += parseFloat(t.amount);
        else dailyDataMap[date].Expense += parseFloat(t.amount);
    });
    // Transactions from API are newest first usually, so reverse for ascending date in chart
    const dailyData = Object.values(dailyDataMap).reverse();

    const categoryMap = {};
    transactions.filter(t => t.type === 'EXPENSE').forEach(t => {
        const cat = t.category_name || 'Uncategorized';
        categoryMap[cat] = (categoryMap[cat] || 0) + parseFloat(t.amount);
    });
    const pieData = Object.keys(categoryMap).map(key => ({ name: key, value: categoryMap[key] })).sort((a,b) => b.value - a.value);

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            <div className="flex flex-col gap-1">
                <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
                <p className="text-muted-foreground">Deep dive into your expense trends and habits.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card className="col-span-1 lg:col-span-2 shadow-md">
                    <CardHeader>
                        <CardTitle>Spending Over Time</CardTitle>
                        <CardDescription>Daily income vs expense</CardDescription>
                    </CardHeader>
                    <CardContent className="h-[350px]">
                        {dailyData.length > 0 ? (
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={dailyData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="colorIncome" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#10b981" stopOpacity={0.8}/>
                                            <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                                        </linearGradient>
                                        <linearGradient id="colorExpense" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.8}/>
                                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                                        </linearGradient>
                                    </defs>
                                    <XAxis dataKey="date" fontSize={12} tickLine={false} axisLine={false} />
                                    <YAxis fontSize={12} tickLine={false} axisLine={false} tickFormatter={(value) => `₹${value}`} />
                                    <RTooltip contentStyle={{borderRadius: '8px', backgroundColor: 'var(--card)', border: '1px solid var(--border)'}} />
                                    <Legend />
                                    <Area type="monotone" dataKey="Income" stroke="#10b981" fillOpacity={1} fill="url(#colorIncome)" />
                                    <Area type="monotone" dataKey="Expense" stroke="#ef4444" fillOpacity={1} fill="url(#colorExpense)" />
                                </AreaChart>
                            </ResponsiveContainer>
                        ) : (
                            <div className="h-full flex items-center justify-center text-muted-foreground">No data available</div>
                        )}
                    </CardContent>
                </Card>

                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle>All-Time Expense Categories</CardTitle>
                        <CardDescription>Where your money goes</CardDescription>
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
                            <div className="h-full flex items-center justify-center text-muted-foreground">No data available</div>
                        )}
                    </CardContent>
                </Card>
                
                <Card className="shadow-sm">
                    <CardHeader>
                        <CardTitle>Top Expenses</CardTitle>
                        <CardDescription>Your highest transactions</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            {transactions
                                .filter(t => t.type === 'EXPENSE')
                                .sort((a, b) => parseFloat(b.amount) - parseFloat(a.amount))
                                .slice(0, 5)
                                .map((t, i) => (
                                    <div key={i} className="flex items-center justify-between border-b border-border/50 pb-3 last:border-0 last:pb-0">
                                        <div className="flex flex-col">
                                            <span className="font-semibold text-sm">{t.title}</span>
                                            <span className="text-xs text-muted-foreground">{new Date(t.date).toLocaleDateString()} &middot; {t.category_name || 'Uncategorized'}</span>
                                        </div>
                                        <span className="font-bold text-destructive">-₹{parseFloat(t.amount).toFixed(2)}</span>
                                    </div>
                                ))}
                            {transactions.filter(t => t.type === 'EXPENSE').length === 0 && (
                                <div className="text-center text-muted-foreground py-8">No expenses recorded</div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default Analytics;
