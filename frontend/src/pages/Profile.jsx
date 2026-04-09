import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { User, Loader2, Save, Mail, Calendar, IndianRupee, Shield, TrendingUp, Target, Wallet } from 'lucide-react';
import api from '../services/api';

const Profile = () => {
    const { user, logout } = useAuth();
    const [budget, setBudget] = useState('');
    const [loading, setLoading] = useState(false);
    const [profileLoading, setProfileLoading] = useState(true);
    const [message, setMessage] = useState(null);
    const [error, setError] = useState(null);
    const [userData, setUserData] = useState(null);
    const [summary, setSummary] = useState(null);

    useEffect(() => {
        const fetchAll = async () => {
            try {
                const [userRes, summaryRes] = await Promise.all([
                    api.get('/auth/me/'),
                    api.get('/transactions/summary/'),
                ]);
                setUserData(userRes.data);
                setSummary(summaryRes.data);
                if (userRes.data.monthly_budget !== null && userRes.data.monthly_budget !== undefined) {
                    setBudget(userRes.data.monthly_budget);
                }
            } catch (err) {
                console.error('Failed to fetch user data', err);
            } finally {
                setProfileLoading(false);
            }
        };
        fetchAll();
    }, []);

    const handleUpdateBudget = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);
        setError(null);
        try {
            await api.patch('/auth/me/', { monthly_budget: budget || 0 });
            setMessage('Budget updated successfully!');
            setTimeout(() => setMessage(null), 3000);
        } catch (err) {
            setError('Failed to update budget.');
        } finally {
            setLoading(false);
        }
    };

    if (profileLoading) {
        return (
            <div className="flex justify-center items-center h-[calc(100vh-100px)]">
                <Loader2 className="animate-spin text-primary h-12 w-12" />
            </div>
        );
    }

    const currentMonth = summary?.current_month;
    const budgetData = summary?.budget;

    return (
        <div className="space-y-6 animate-in fade-in duration-500 max-w-4xl mx-auto pt-2">
            <div className="flex flex-col gap-1">
                <h1 className="text-3xl font-bold tracking-tight">Profile</h1>
                <p className="text-muted-foreground">Manage your account and financial preferences.</p>
            </div>

            {/* Profile Header Card */}
            <Card className="overflow-hidden border-border/50">
                <div className="h-24 bg-gradient-to-r from-primary via-primary/80 to-secondary" />
                <CardContent className="relative pb-6">
                    <div className="flex flex-col sm:flex-row items-start sm:items-end gap-4 -mt-12">
                        <div className="w-20 h-20 rounded-2xl bg-card border-4 border-card shadow-xl flex items-center justify-center">
                            <span className="text-3xl font-extrabold text-primary">
                                {userData?.username?.charAt(0)?.toUpperCase() || 'U'}
                            </span>
                        </div>
                        <div className="flex-1">
                            <h2 className="text-2xl font-bold">{userData?.username || 'User'}</h2>
                            <div className="flex items-center gap-2 mt-1 text-muted-foreground text-sm">
                                <Mail size={14} />
                                <span>{userData?.email || 'No email set'}</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="px-3 py-1.5 bg-emerald-500/15 text-emerald-600 text-xs font-semibold rounded-full flex items-center gap-1.5">
                                <Shield size={12} />
                                Active Account
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <Card className="border-border/50">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">This Month Income</p>
                                <p className="text-2xl font-bold text-emerald-500 mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.income).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-emerald-500/10 rounded-xl flex items-center justify-center">
                                <TrendingUp className="text-emerald-500" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>
                
                <Card className="border-border/50">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">This Month Expense</p>
                                <p className="text-2xl font-bold text-destructive mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-destructive/10 rounded-xl flex items-center justify-center">
                                <Wallet className="text-destructive" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>

                <Card className="border-border/50">
                    <CardContent className="pt-6">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-muted-foreground">Net Balance</p>
                                <p className="text-2xl font-bold text-primary mt-1">
                                    ₹{currentMonth ? parseFloat(currentMonth.balance).toFixed(2) : '0.00'}
                                </p>
                            </div>
                            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
                                <IndianRupee className="text-primary" size={20} />
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Budget Settings */}
            <Card className="border-border/50">
                <CardHeader>
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-blue-500/10 rounded-xl flex items-center justify-center">
                            <Target className="text-blue-500" size={20} />
                        </div>
                        <div>
                            <CardTitle>Monthly Budget</CardTitle>
                            <CardDescription>Set a spending limit to keep your finances on track</CardDescription>
                        </div>
                    </div>
                </CardHeader>
                <form onSubmit={handleUpdateBudget}>
                    <CardContent className="space-y-4">
                        {message && (
                            <div className="p-3 bg-emerald-500/15 text-emerald-600 text-sm rounded-lg border border-emerald-500/30 animate-in fade-in">
                                ✓ {message}
                            </div>
                        )}
                        {error && (
                            <div className="p-3 bg-destructive/15 text-destructive text-sm rounded-lg border border-destructive/30">
                                {error}
                            </div>
                        )}
                        
                        {/* Budget Progress */}
                        {budgetData && parseFloat(budgetData.limit) > 0 && (
                            <div className="p-4 rounded-xl bg-muted/50 space-y-3">
                                <div className="flex justify-between text-sm">
                                    <span className="text-muted-foreground">Spent this month</span>
                                    <span className="font-semibold">
                                        ₹{currentMonth ? parseFloat(currentMonth.expense).toFixed(0) : 0} / ₹{parseFloat(budgetData.limit).toFixed(0)}
                                    </span>
                                </div>
                                <div className="w-full bg-background h-3 rounded-full overflow-hidden">
                                    <div 
                                        className={`h-full rounded-full transition-all duration-500 ${budgetData.exceeded ? 'bg-destructive' : 'bg-primary'}`}
                                        style={{ width: `${Math.min((currentMonth?.expense / budgetData.limit) * 100, 100)}%` }}
                                    />
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {budgetData.exceeded 
                                        ? '⚠️ You have exceeded your budget this month!' 
                                        : `₹${(parseFloat(budgetData.limit) - parseFloat(currentMonth?.expense || 0)).toFixed(0)} remaining`
                                    }
                                </p>
                            </div>
                        )}

                        <div className="space-y-2">
                            <Label htmlFor="budget">Monthly Budget Limit (₹)</Label>
                            <Input
                                id="budget"
                                type="number"
                                step="0.01"
                                placeholder="e.g. 20000.00"
                                value={budget}
                                onChange={(e) => setBudget(e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">
                                You'll see a warning on the dashboard if you exceed this limit. Set to 0 to disable.
                            </p>
                        </div>
                    </CardContent>
                    <CardFooter>
                        <Button type="submit" disabled={loading} className="w-full sm:w-auto">
                            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                            Update Budget
                        </Button>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
};

export default Profile;
